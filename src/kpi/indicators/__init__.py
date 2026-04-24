"""Indicator groups for FROI (FHI, FEI, FVI, FRI).

Each group exposes a class that knows how to:
  * load its static data (for FEI/FVI/FRI static components) at init, and
  * produce a per-subcatchment matrix of standardized indicator values
    on demand (from SWMM results for the dynamic FHI/R4 parts).

The shared base class :class:`IndicatorGroup` provides standardization
primitives so each group stays focused on its own data sources.
"""

from .base import IndicatorGroup, minmax_standardize, reference_standardize
from .exposure import ExposureIndicators
from .hazard import HazardIndicators
from .resilience import ResilienceIndicators
from .vulnerability import VulnerabilityIndicators

__all__ = [
    "ExposureIndicators",
    "HazardIndicators",
    "IndicatorGroup",
    "ResilienceIndicators",
    "VulnerabilityIndicators",
    "minmax_standardize",
    "reference_standardize",
]
