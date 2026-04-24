"""FEI — Flood Exposure Index.

Four static indicators loaded once from external CSV data:

  * E1 — Population density (per-SC persons/km², positive direction)
  * E2 — Land use score     (per-SC [0,1] score, positive — already standardized)
  * E3 — Road density       (per-SC km/km², positive)
  * E4 — Facilities level   (per-SC weighted count density, positive)

All four are positive direction — higher exposure = higher FROI.

Input CSV schema (``data/exposure/exposure.csv``, one row per subcatchment):
    subcatchment_id,population_density,land_use_score,road_density,facility_score

A missing value is treated as 0. Subcatchments not present in the CSV are
zeroed.
"""

from __future__ import annotations

import csv

import numpy as np

from .base import IndicatorGroup, minmax_standardize


class ExposureIndicators(IndicatorGroup):
    """Static FEI indicators loaded from CSV."""

    group_name = "FEI"
    indicator_names = [
        "E1_population_density",
        "E2_land_use",
        "E3_road_density",
        "E4_facilities",
    ]

    def __init__(
        self,
        subcatchment_names: list[str],
        exposure_csv: str,
    ):
        """
        Args:
            subcatchment_names: Ordered list; defines row index.
            exposure_csv: Path to a CSV with columns
                ``subcatchment_id, population_density, land_use_score,
                road_density, facility_score``.
        """
        self._sc_names = list(subcatchment_names)
        self._raw = self._load_csv(exposure_csv)
        self._normalized = self._standardize(self._raw)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_csv(self, path: str) -> np.ndarray:
        """Return an (S, 4) matrix of raw values, in subcatchment order."""
        by_sc: dict[str, dict[str, float]] = {}
        with open(path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                sc = row["subcatchment_id"].strip()
                by_sc[sc] = {
                    "pop": float(row.get("population_density", 0) or 0),
                    "lu": float(row.get("land_use_score", 0) or 0),
                    "road": float(row.get("road_density", 0) or 0),
                    "fac": float(row.get("facility_score", 0) or 0),
                }

        S = len(self._sc_names)
        out = np.zeros((S, 4))
        for i, sc in enumerate(self._sc_names):
            rec = by_sc.get(sc)
            if rec is None:
                continue
            out[i, 0] = rec["pop"]
            out[i, 1] = rec["lu"]
            out[i, 2] = rec["road"]
            out[i, 3] = rec["fac"]
        return out

    # ------------------------------------------------------------------
    # Standardization
    # ------------------------------------------------------------------

    def _standardize(self, raw: np.ndarray) -> np.ndarray:
        """Min-max standardize columns 0, 2, 3; column 1 (land use) is pre-[0,1]."""
        out = np.zeros_like(raw)
        out[:, 0] = minmax_standardize(raw[:, 0], positive=True)
        # Land use score is already in [0, 1] by construction; clamp just in case.
        out[:, 1] = np.clip(raw[:, 1], 0.0, 1.0)
        out[:, 2] = minmax_standardize(raw[:, 2], positive=True)
        out[:, 3] = minmax_standardize(raw[:, 3], positive=True)
        return out

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute(self) -> np.ndarray:
        """Return cached ``(S, 4)`` standardized exposure indicators."""
        return self._normalized.copy()

    @property
    def raw(self) -> np.ndarray:
        """Raw (unstandardized) values — useful for EWM weight calculation."""
        return self._raw.copy()
