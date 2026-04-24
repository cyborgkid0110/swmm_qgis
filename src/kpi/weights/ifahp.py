"""IFAHP — Intuitionistic Fuzzy Analytic Hierarchy Process.

Implements the 6-step subjective-weight procedure from ``weights.md``:

  1. Construct one intuitionistic fuzzy judgment matrix per expert, ``A^(k)``.
     Each cell is a pair ``(μ_ab, ν_ab)`` with ``μ + ν ≤ 1``.
  2. Compute expert weights ``λ_k`` from each matrix's average membership /
     non-membership / hesitation.
  3. Aggregate the expert matrices into a single group matrix ``R`` using the
     weighted accumulation ``1 − Π(1 − x)^λ``.
  4. Consistency check ``CR = CI / RI``. The intuitionistic matrix is
     collapsed to a crisp proxy via the score function ``S = μ − ν`` and the
     classical Saaty CI is applied; this is the standard way to extend AHP
     consistency to IF matrices.
  5. Extract per-indicator aggregated triplet ``(μ_m, ν_m, π_m)`` by row
     averaging.
  6. Convert to raw weights via the fuzzy-entropy formula and normalize so
     ``Σ ω_m = 1``.

All inputs and outputs are plain Python / numpy for easy testing. No hard
dependency on the rest of the pipeline.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

# Saaty's Random Consistency Index (RI) table, for n = 1..15
# RI[n] for matrix size n. RI[1] = RI[2] = 0 by convention.
_SAATY_RI = [0.0, 0.0, 0.0, 0.58, 0.90, 1.12, 1.24, 1.32,
             1.41, 1.45, 1.49, 1.51, 1.48, 1.56, 1.57, 1.59]


@dataclass
class IFAHPResult:
    """Outputs of the IFAHP algorithm."""

    weights: np.ndarray          # shape (M,), Σ = 1
    expert_weights: np.ndarray   # shape (K,), Σ = 1
    group_matrix_mu: np.ndarray  # shape (M, M) — aggregated μ
    group_matrix_nu: np.ndarray  # shape (M, M) — aggregated ν
    cr: float                    # consistency ratio
    consistent: bool             # CR ≤ 0.10
    indicator_triplets: list[tuple[float, float, float]]  # [(μ_m, ν_m, π_m)]


def _validate_if_matrix(A: np.ndarray) -> None:
    """Check shape (M, M, 2) and μ + ν ≤ 1 + eps."""
    if A.ndim != 3 or A.shape[0] != A.shape[1] or A.shape[2] != 2:
        raise ValueError(
            f"Expert matrix must have shape (M, M, 2), got {A.shape}"
        )
    bad = A[..., 0] + A[..., 1] > 1.0 + 1e-9
    if bad.any():
        raise ValueError(
            "Intuitionistic constraint violated: μ + ν > 1 in at least one cell"
        )
    if (A < 0).any() or (A > 1).any():
        raise ValueError("μ and ν must be in [0, 1]")


def _expert_weights(matrices: list[np.ndarray]) -> np.ndarray:
    """Step 2: compute λ_k from each expert matrix."""
    K = len(matrices)
    raw = np.zeros(K)
    for k, A in enumerate(matrices):
        M = A.shape[0]
        mu_k = A[..., 0].mean()
        nu_k = A[..., 1].mean()
        pi_k = 1.0 - mu_k - nu_k
        denom = mu_k + nu_k
        # Guard against pathological all-zero expert.
        if denom <= 1e-12:
            raw[k] = 0.0
        else:
            raw[k] = mu_k + pi_k * (mu_k / denom)

    total = raw.sum()
    if total <= 1e-12:
        # Fall back to uniform if every expert produced zeros.
        return np.full(K, 1.0 / K)
    return raw / total


def _aggregate_group_matrix(
    matrices: list[np.ndarray], lambdas: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Step 3: aggregate into group matrix R = (μ_ab, ν_ab).

    ``μ_ab = 1 − Π (1 − μ_ab^(k))^λ_k``
    ``ν_ab = 1 − Π (1 − ν_ab^(k))^λ_k``
    """
    M = matrices[0].shape[0]
    mu_prod = np.ones((M, M))
    nu_prod = np.ones((M, M))
    for A, lam in zip(matrices, lambdas):
        # Clamp inside [0, 1) so (1 - x)^λ is well-defined.
        mu_clamped = np.clip(A[..., 0], 0.0, 1.0 - 1e-12)
        nu_clamped = np.clip(A[..., 1], 0.0, 1.0 - 1e-12)
        mu_prod *= (1.0 - mu_clamped) ** lam
        nu_prod *= (1.0 - nu_clamped) ** lam
    return 1.0 - mu_prod, 1.0 - nu_prod


def _consistency_ratio(mu: np.ndarray, nu: np.ndarray) -> float:
    """Step 4: CR = CI / RI using the score-function crisp proxy.

    Score S_ab = μ_ab − ν_ab maps [−1, 1]; transform to a positive-reciprocal
    matrix via exp(S · scale) so that Saaty's eigenvalue-based CI applies.
    The specific mapping is the standard IFAHP consistency conversion.
    """
    M = mu.shape[0]
    if M <= 2:
        return 0.0  # RI undefined; 2×2 is always consistent.

    score = mu - nu
    # Map score ∈ [-1, 1] → multiplicative preference ratio in [1/9, 9].
    # This is the conventional Saaty scale mapping used in IFAHP consistency.
    crisp = np.exp(score * math.log(9.0))

    eig = np.linalg.eigvals(crisp)
    lam_max = float(np.real(eig).max())
    ci = (lam_max - M) / (M - 1)

    ri = _SAATY_RI[M] if M < len(_SAATY_RI) else _SAATY_RI[-1]
    if ri <= 0:
        return 0.0
    return float(ci / ri)


def _row_triplets(
    mu: np.ndarray, nu: np.ndarray
) -> list[tuple[float, float, float]]:
    """Step 5: per-indicator (μ_m, ν_m, π_m) by row averaging."""
    M = mu.shape[0]
    out = []
    for m in range(M):
        mu_m = float(mu[m, :].mean())
        nu_m = float(nu[m, :].mean())
        pi_m = 1.0 - mu_m - nu_m
        # Floating-point jitter can push π slightly negative; clamp.
        pi_m = max(0.0, min(1.0, pi_m))
        out.append((mu_m, nu_m, pi_m))
    return out


def _fuzzy_entropy_weight(mu: float, nu: float, pi: float, M: int) -> float:
    """Step 6 numerator: fuzzy-entropy raw weight ω̂_m.

    ω̂_m = −1 / (M · ln 2) · [μ ln μ + ν ln ν + (1 − π) ln(1 − π) − π ln 2]

    Each ``x ln x`` term is 0 when x = 0 (standard convention).
    """
    def xlogx(x: float) -> float:
        if x <= 0.0:
            return 0.0
        return x * math.log(x)

    term = xlogx(mu) + xlogx(nu) + xlogx(1.0 - pi) - pi * math.log(2.0)
    return -term / (M * math.log(2.0))


def ifahp_weights(
    expert_matrices: list[np.ndarray],
    consistency_threshold: float = 0.10,
) -> IFAHPResult:
    """Compute IFAHP subjective weights from K expert judgment matrices.

    Args:
        expert_matrices: List of K arrays, each shape ``(M, M, 2)``. The last
            axis holds ``(μ, ν)`` with ``μ + ν ≤ 1``.
        consistency_threshold: Upper bound on CR for the group matrix to be
            considered consistent (default 0.10 per Saaty).

    Returns:
        :class:`IFAHPResult` with normalized weights and intermediate data.

    Raises:
        ValueError: empty input, mismatched sizes, or invalid IF constraints.
    """
    if not expert_matrices:
        raise ValueError("Need at least one expert matrix")

    arrays = [np.asarray(A, dtype=float) for A in expert_matrices]
    M = arrays[0].shape[0]
    for A in arrays:
        _validate_if_matrix(A)
        if A.shape[0] != M:
            raise ValueError("All expert matrices must share the same size M")

    lambdas = _expert_weights(arrays)
    mu_group, nu_group = _aggregate_group_matrix(arrays, lambdas)
    cr = _consistency_ratio(mu_group, nu_group)
    consistent = cr <= consistency_threshold

    triplets = _row_triplets(mu_group, nu_group)
    raw = np.array(
        [_fuzzy_entropy_weight(mu, nu, pi, M) for (mu, nu, pi) in triplets]
    )
    total = raw.sum()
    if total <= 1e-12:
        # Every indicator has zero information content — fall back to uniform.
        weights = np.full(M, 1.0 / M)
    else:
        weights = raw / total

    return IFAHPResult(
        weights=weights,
        expert_weights=lambdas,
        group_matrix_mu=mu_group,
        group_matrix_nu=nu_group,
        cr=cr,
        consistent=consistent,
        indicator_triplets=triplets,
    )
