"""FRI -- Flood Resilience Index.

Three static indicators:

  * R1 -- Emergency distance     (static, CSV; raw distance inverted so
                                   higher R1_norm = closer = more resilient)
  * R2 -- Shelter count           (static, CSV; more shelters = more resilient)
  * R3 -- Warning coverage        (static, CSV; already ratio in [0,1])

All FRI indicators use **positive-within-FRI** convention: higher R_m_norm =
higher resilience. The outer FROI formula flips this via ``(1 - FRI)``.

Input CSVs:
  ``data/resilience/resilience_static.csv`` -- columns:
      subcatchment_id, avg_emergency_distance_m, shelter_count,
      warning_coverage_ratio
"""

from __future__ import annotations

import csv

import numpy as np

from .base import IndicatorGroup, minmax_standardize


class ResilienceIndicators(IndicatorGroup):
    """R1-R3 static resilience indicators."""

    group_name = "FRI"
    indicator_names = [
        "R1_emergency_distance",
        "R2_shelter_count",
        "R3_warning_coverage",
    ]

    def __init__(
        self,
        subcatchment_names: list[str],
        resilience_csv: str,
    ):
        """
        Args:
            subcatchment_names: Ordered list; defines row index.
            resilience_csv: CSV with columns ``subcatchment_id,
                avg_emergency_distance_m, shelter_count,
                warning_coverage_ratio``.
        """
        self._sc_names = list(subcatchment_names)
        self._normalized = self._load_static(resilience_csv)

    def _load_static(self, path: str) -> np.ndarray:
        """Return standardized (S, 3) in positive-within-FRI convention."""
        by_sc: dict[str, dict[str, float]] = {}
        with open(path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                sc = row["subcatchment_id"].strip()
                by_sc[sc] = {
                    "dist": float(row.get("avg_emergency_distance_m", 0) or 0),
                    "shelters": float(row.get("shelter_count", 0) or 0),
                    "warn": float(row.get("warning_coverage_ratio", 0) or 0),
                }

        S = len(self._sc_names)
        raw_dist = np.zeros(S)
        raw_shelters = np.zeros(S)
        raw_warn = np.zeros(S)
        for i, sc in enumerate(self._sc_names):
            rec = by_sc.get(sc)
            if rec is None:
                continue
            raw_dist[i] = rec["dist"]
            raw_shelters[i] = rec["shelters"]
            raw_warn[i] = rec["warn"]

        r1_norm = minmax_standardize(raw_dist, positive=False)
        r2_norm = minmax_standardize(raw_shelters, positive=True)
        r3_norm = np.clip(raw_warn, 0.0, 1.0)

        return np.column_stack([r1_norm, r2_norm, r3_norm])

    def compute(self) -> np.ndarray:
        """Return cached ``(S, 3)`` standardized FRI indicators."""
        return self._normalized.copy()
