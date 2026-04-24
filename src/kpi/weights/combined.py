"""Combined weights — preference-coefficient fusion of IFAHP and EWM.

Given subjective weights ``ω_m`` (from IFAHP) and objective weights ``θ_m``
(from EWM), the combined weights ``ρ_m`` are produced in two steps:

  * Preference coefficient: ``ε_m = θ_m^2 / (ω_m^2 + θ_m^2)``
  * Combined + renormalized:
    ``ρ_m = √((ε_m ω_m)^2 + ((1 − ε_m) θ_m)^2) / Σ_i √(…)``

Per ``weights.md``, this preserves expert judgment when data variance is
low and leans on data when variance is high.
"""

from __future__ import annotations

import numpy as np


def preference_coefficients(
    omega: np.ndarray, theta: np.ndarray
) -> np.ndarray:
    """Return ``ε_m = θ_m^2 / (ω_m^2 + θ_m^2)`` elementwise.

    When both ``ω_m`` and ``θ_m`` are zero, ``ε_m`` falls back to 0.5 (no
    preference signal).
    """
    omega = np.asarray(omega, dtype=float)
    theta = np.asarray(theta, dtype=float)
    if omega.shape != theta.shape:
        raise ValueError(
            f"omega and theta must match shape: got {omega.shape} vs {theta.shape}"
        )

    num = theta ** 2
    denom = omega ** 2 + theta ** 2
    return np.where(denom > 1e-12, num / np.where(denom > 0, denom, 1.0), 0.5)


def combined_weights(
    omega: np.ndarray, theta: np.ndarray
) -> np.ndarray:
    """Return the normalized combined weights ``ρ_m`` (Σ = 1).

    Args:
        omega: IFAHP subjective weights, shape ``(M,)``, sum ≈ 1.
        theta: EWM objective weights, shape ``(M,)``, sum ≈ 1.

    Returns:
        ``np.ndarray`` shape ``(M,)``, Σ = 1.
    """
    omega = np.asarray(omega, dtype=float)
    theta = np.asarray(theta, dtype=float)
    if omega.shape != theta.shape:
        raise ValueError(
            f"omega and theta must match shape: got {omega.shape} vs {theta.shape}"
        )

    eps = preference_coefficients(omega, theta)
    raw = np.sqrt((eps * omega) ** 2 + ((1.0 - eps) * theta) ** 2)
    total = raw.sum()
    if total <= 1e-12:
        # Degenerate case — both inputs were zero vectors. Uniform fallback.
        M = len(raw)
        return np.full(M, 1.0 / M)
    return raw / total
