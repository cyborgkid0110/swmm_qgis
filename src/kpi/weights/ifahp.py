"""IFAHP -- Intuitionistic Fuzzy Analytic Hierarchy Process.

Implements the 6-step subjective-weight procedure from ``weights.md``:

  1. Construct one intuitionistic fuzzy judgment matrix per expert, ``A^(k)``.
     Each cell is a pair ``(mu_ab, nu_ab)`` with ``mu + nu <= 1``.
  2. Compute expert weights ``lambda_k`` from each matrix's average membership
     / non-membership / hesitation.
  3. Aggregate the expert matrices into a single group matrix ``R`` using the
     IFWAA operator: ``mu_ab = 1 - Pi(1 - mu)^lam`` and ``nu_ab = Pi nu^lam``.
  4. Distance-based consistency check: build a perfectly consistent matrix
     R_bar via Algorithm I, then compute d(R_bar, R).  Consistent iff
     d < tau (default 0.10).
  5. Extract per-indicator aggregated triplet ``(mu_m, nu_m, pi_m)`` by row
     averaging.
  6. Convert to raw weights via the fuzzy-entropy formula and normalize so
     ``sum omega_m = 1``.

If the group matrix is **not** consistent, ``ifahp_weights`` falls back to
uniform weights with a warning rather than silently returning weights from
contradictory expert judgments.

All inputs and outputs are plain Python / numpy for easy testing. No hard
dependency on the rest of the pipeline.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass

import numpy as np

_EPS = 1e-12


@dataclass
class IFAHPResult:
    """Outputs of the IFAHP algorithm."""

    weights: np.ndarray          # shape (M,), sum = 1
    expert_weights: np.ndarray   # shape (K,), sum = 1
    group_matrix_mu: np.ndarray  # shape (M, M) -- aggregated mu
    group_matrix_nu: np.ndarray  # shape (M, M) -- aggregated nu
    cr: float                    # d(R_bar, R) distance-based consistency measure
    consistent: bool             # d < 0.10
    indicator_triplets: list[tuple[float, float, float]]  # [(mu_m, nu_m, pi_m)]
    fallback_used: bool          # True if uniform weights returned due to inconsistency


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

    IFWAA operator:
      ``μ_ab = 1 − Π (1 − μ_ab^(k))^λ_k``     (optimistic accumulation)
      ``ν_ab = Π (ν_ab^(k))^λ_k``             (geometric product)

    The asymmetry is intentional and is what guarantees ``μ_ab + ν_ab ≤ 1``
    when each input cell satisfies that bound. Using the optimistic operator
    on both sides (the older code, and a common mistake from secondary
    sources of the algorithm) inflates both ``μ`` and ``ν`` and can produce
    invalid IF pairs.
    """
    M = matrices[0].shape[0]
    mu_prod = np.ones((M, M))
    nu_prod = np.ones((M, M))
    for A, lam in zip(matrices, lambdas):
        # Clamp inside [0, 1) so (1 - x)^λ is well-defined.
        mu_clamped = np.clip(A[..., 0], 0.0, 1.0 - 1e-12)
        nu_clamped = np.clip(A[..., 1], 0.0, 1.0)
        mu_prod *= (1.0 - mu_clamped) ** lam
        # ν uses the geometric mean (IFWAA operator), not the optimistic form.
        # 0^0 = 1 by NumPy convention, which is what we want when λ = 0.
        nu_prod *= nu_clamped ** lam
    mu_ab = 1.0 - mu_prod
    nu_ab = nu_prod
    return mu_ab, nu_ab


def _perfectly_consistent_matrix(
    mu: np.ndarray, nu: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Algorithm I: build R_bar from the group matrix R.

    For k > i + 1 (non-adjacent pairs), mu_bar and nu_bar are derived from
    the geometric mean of transitive chains through intermediate indicators::

        mu_bar_ik = g / (g + h)
        where g = (prod_{t=i+1}^{k-1} mu_it * mu_tk)^{1/(k-i-1)}
              h = (prod_{t=i+1}^{k-1} (1-mu_it)*(1-mu_tk))^{1/(k-i-1)}

    Same formula applies independently to nu.
    For k = i + 1, R_bar_ik = R_ik (adjacent entries are kept).
    For k < i (lower triangle), swap: mu_bar_ik = nu_bar_ki, nu_bar_ik = mu_bar_ki.
    For k = i (diagonal), keep the original.
    """
    M = mu.shape[0]
    mu_bar = mu.copy()
    nu_bar = nu.copy()

    for i in range(M):
        for k in range(i + 2, M):
            n_steps = k - i - 1
            mu_num_prod = 1.0
            mu_den_prod = 1.0
            nu_num_prod = 1.0
            nu_den_prod = 1.0
            for t in range(i + 1, k):
                mu_num_prod *= max(mu[i, t] * mu[t, k], _EPS)
                mu_den_prod *= max((1.0 - mu[i, t]) * (1.0 - mu[t, k]), _EPS)
                nu_num_prod *= max(nu[i, t] * nu[t, k], _EPS)
                nu_den_prod *= max((1.0 - nu[i, t]) * (1.0 - nu[t, k]), _EPS)

            mu_g = mu_num_prod ** (1.0 / n_steps)
            mu_h = mu_den_prod ** (1.0 / n_steps)
            nu_g = nu_num_prod ** (1.0 / n_steps)
            nu_h = nu_den_prod ** (1.0 / n_steps)

            mu_bar[i, k] = mu_g / (mu_g + mu_h) if (mu_g + mu_h) > _EPS else 0.5
            nu_bar[i, k] = nu_g / (nu_g + nu_h) if (nu_g + nu_h) > _EPS else 0.5

    for i in range(M):
        for k in range(i):
            mu_bar[i, k] = nu_bar[k, i]
            nu_bar[i, k] = mu_bar[k, i]

    return mu_bar, nu_bar


def _consistency_distance(mu: np.ndarray, nu: np.ndarray) -> float:
    """Step 4: distance d(R_bar, R) as consistency measure.

    d = 1/(2(n-1)(n-2)) * sum_{i,k} (|mu_bar-mu| + |nu_bar-nu| + |pi_bar-pi|)

    Returns 0.0 for M <= 2 (always consistent).
    """
    M = mu.shape[0]
    if M <= 2:
        return 0.0

    mu_bar, nu_bar = _perfectly_consistent_matrix(mu, nu)
    pi = np.clip(1.0 - mu - nu, 0.0, 1.0)
    pi_bar = np.clip(1.0 - mu_bar - nu_bar, 0.0, 1.0)

    total = float(
        np.abs(mu_bar - mu).sum()
        + np.abs(nu_bar - nu).sum()
        + np.abs(pi_bar - pi).sum()
    )
    return total / (2.0 * (M - 1) * (M - 2))


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
        # With the corrected Step 3 aggregation, μ + ν ≤ 1 always holds, so
        # π is non-negative by construction. Clamp for floating-point safety.
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
            axis holds ``(mu, nu)`` with ``mu + nu <= 1``.
        consistency_threshold: Upper bound on d(R_bar, R) for the group matrix
            to be considered consistent (default 0.10). When d >= threshold,
            the function falls back to uniform weights and emits a
            ``UserWarning``.

    Returns:
        :class:`IFAHPResult` with normalized weights and intermediate data.
        ``cr`` holds d(R_bar, R) (the distance-based consistency measure).
        ``fallback_used = True`` indicates ``weights`` is the uniform vector
        because the consistency check failed.

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
    cr = _consistency_distance(mu_group, nu_group)
    consistent = cr < consistency_threshold

    triplets = _row_triplets(mu_group, nu_group)
    raw = np.array(
        [_fuzzy_entropy_weight(mu, nu, pi, M) for (mu, nu, pi) in triplets]
    )

    fallback_used = False
    if not consistent:
        warnings.warn(
            f"IFAHP consistency check failed (d={cr:.4f} >= "
            f"{consistency_threshold:.2f}). Falling back to uniform weights "
            f"of {1.0 / M:.4f} for {M} indicators. Re-elicit expert "
            f"judgments to improve transitivity.",
            UserWarning,
            stacklevel=2,
        )
        weights = np.full(M, 1.0 / M)
        fallback_used = True
    else:
        total = raw.sum()
        if total <= 1e-12:
            # Every indicator has zero information content — uniform fallback.
            weights = np.full(M, 1.0 / M)
            fallback_used = True
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
        fallback_used=fallback_used,
    )
