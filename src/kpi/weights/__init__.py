"""Weight computation for flood risk indicators.

Three weighting methods combined per index group (FHI, FEI, FVI, FRI):

  * :mod:`ifahp`    — Intuitionistic Fuzzy AHP (subjective, expert-driven).
  * :mod:`ewm`      — Entropy Weight Method (objective, data-driven).
  * :mod:`combined` — Preference coefficient combination of IFAHP + EWM.

Typical usage::

    omega = ifahp_weights(expert_matrices)        # subjective
    theta = ewm_weights(indicator_matrix)         # objective
    rho   = combined_weights(omega, theta)        # final weights (Σ = 1)
"""

from .combined import combined_weights, preference_coefficients
from .ewm import ewm_weights
from .ifahp import IFAHPResult, ifahp_weights

__all__ = [
    "IFAHPResult",
    "combined_weights",
    "ewm_weights",
    "ifahp_weights",
    "preference_coefficients",
]
