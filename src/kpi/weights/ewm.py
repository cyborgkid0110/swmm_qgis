"""EWM — Entropy Weight Method.

Implements the 5-step objective-weight procedure from ``weights.md``:

  1. Standardize raw indicator data into ``r_nm ∈ [0, 1]`` via min-max.
     Positive indicators use ``(x − min) / (max − min)``; negative indicators
     use ``(max − x) / (max − min)``.
  2. Proportion: ``p_nm = r_nm / Σ_n r_nm``.
  3. Information entropy: ``e_m = −(1 / ln N) · Σ_n p_nm · ln p_nm``.
  4. Utility / redundancy: ``d_m = 1 − e_m``.
  5. Final weight: ``θ_m = d_m / Σ d_m``.

Input format: a ``(N, M)`` matrix of raw values — N samples × M indicators.
In this project, N = number of subcatchments, M = number of indicators in
the current index group.

The caller is responsible for telling EWM which indicators are "negative"
(higher = lower risk) so that standardization flips them before entropy is
computed. Pass ``directions`` as a length-M sequence of "+1" / "-1" or
booleans.
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np


def _standardize(
    data: np.ndarray, directions: Sequence[int | bool] | None
) -> np.ndarray:
    """Min-max standardize each column to [0, 1]; flip negative indicators."""
    N, M = data.shape
    out = np.zeros_like(data, dtype=float)

    if directions is None:
        directions = [1] * M
    if len(directions) != M:
        raise ValueError(
            f"directions must have length {M}, got {len(directions)}"
        )

    for m in range(M):
        col = data[:, m]
        lo, hi = col.min(), col.max()
        rng = hi - lo
        if rng <= 1e-12:
            # All samples identical — neutral 0.5 per the plan's convention.
            out[:, m] = 0.5
            continue

        positive = bool(directions[m]) if isinstance(directions[m], bool) \
            else directions[m] > 0
        if positive:
            out[:, m] = (col - lo) / rng
        else:
            out[:, m] = (hi - col) / rng

    return out


def ewm_weights(
    data: np.ndarray,
    directions: Sequence[int | bool] | None = None,
) -> np.ndarray:
    """Compute EWM objective weights.

    Args:
        data: Raw indicator matrix, shape ``(N, M)``. N samples × M indicators.
        directions: Per-indicator direction. Element > 0 (or True) means
            "positive" (higher = higher risk / standardize as-is). Element
            ≤ 0 (or False) means "negative" (higher = lower risk / flip
            during standardization). Default: all positive.

    Returns:
        ``np.ndarray`` shape ``(M,)`` with ``Σ θ_m = 1``.

    Notes:
        If an indicator column is constant (min == max), it contributes zero
        distinguishing information — entropy = 1, redundancy = 0. The output
        weight for such a column is 0 and the remaining columns are
        renormalized to sum to 1. If every column is constant, the output is
        uniform.
    """
    X = np.asarray(data, dtype=float)
    if X.ndim != 2:
        raise ValueError(f"data must be 2-D (N, M), got shape {X.shape}")
    N, M = X.shape
    if N < 2:
        # Entropy is undefined with a single sample; fall back to uniform.
        return np.full(M, 1.0 / M)

    R = _standardize(X, directions)

    # Step 2: proportions per indicator column.
    col_sums = R.sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        P = np.where(col_sums > 0, R / np.where(col_sums > 0, col_sums, 1.0), 0.0)

    # Step 3: entropy. Constant columns (sum==0 after flip? only possible if
    # all-zero, but min-max already collapsed those to 0.5 → sum > 0) still
    # might produce p = 0 for some rows; 0·ln 0 = 0.
    ln_N = math.log(N)
    with np.errstate(invalid="ignore", divide="ignore"):
        terms = np.where(P > 0, P * np.log(P), 0.0)
    e = -terms.sum(axis=0) / ln_N

    # Detect constant columns (all P values equal → e = 1 exactly).
    # Mark them as zero-redundancy so they don't contribute to the weights.
    all_equal_mask = np.isclose(R.std(axis=0), 0.0)

    # Step 4: redundancy.
    d = 1.0 - e
    d = np.where(all_equal_mask, 0.0, d)
    d = np.clip(d, 0.0, None)  # floating-point jitter guard

    # Step 5: normalize.
    total = d.sum()
    if total <= 1e-12:
        # All indicators were constant — no data-driven signal; uniform.
        return np.full(M, 1.0 / M)
    return d / total
