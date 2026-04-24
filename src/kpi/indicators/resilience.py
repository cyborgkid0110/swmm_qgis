"""FRI — Flood Resilience Index.

Four indicators, three static + one dynamic:

  * R1 — Emergency distance     (static, CSV; raw distance → inverted so
                                   higher R1_norm = closer = more resilient)
  * R2 — Shelter count           (static, CSV; more shelters = more resilient)
  * R3 — Warning coverage        (static, CSV; already ratio in [0,1])
  * R4 — Drainage capacity       (dynamic, SWMM; reuses F2 accumulator per SC,
                                   then ``1 − min(1, raw/R4_ref)`` so higher =
                                   less stressed = more resilient)

All FRI indicators use **positive-within-FRI** convention: higher R_m_norm =
higher resilience. The outer FROI formula flips this via ``(1 − FRI)``.

Input CSVs:
  ``data/resilience/resilience_static.csv`` — columns:
      subcatchment_id, avg_emergency_distance_m, shelter_count,
      warning_coverage_ratio
"""

from __future__ import annotations

import csv
import math

import numpy as np

from .base import IndicatorGroup, minmax_standardize


class ResilienceIndicators(IndicatorGroup):
    """R1–R3 static + R4 dynamic from SWMM conduit statistics."""

    group_name = "FRI"
    indicator_names = [
        "R1_emergency_distance",
        "R2_shelter_count",
        "R3_warning_coverage",
        "R4_drainage_capacity",
    ]

    def __init__(
        self,
        subcatchment_names: list[str],
        resilience_csv: str,
        conduit_to_sc: dict[str, str],
        conduit_props: dict,
        xsection_props: dict,
        node_elevations: dict,
        *,
        r4_zeta: float = 0.5,
        r4_gamma: float = 0.5,
    ):
        """
        Args:
            subcatchment_names: Ordered list; defines row index.
            resilience_csv: CSV with columns ``subcatchment_id,
                avg_emergency_distance_m, shelter_count,
                warning_coverage_ratio``.
            conduit_to_sc: ``{conduit_name: subcatchment_name}`` from the
                aggregator.
            conduit_props: ``parse_conduits(inp_sections)`` output.
            xsection_props: ``parse_xsections(inp_sections)`` output.
            node_elevations: ``parse_node_elevations(inp_sections)`` output.
            r4_zeta: Weight on the Q_peak/Q_full ratio in the R4 raw formula.
            r4_gamma: Weight on the surcharge-time fraction in R4.
        """
        self._sc_names = list(subcatchment_names)
        self._conduit_to_sc = dict(conduit_to_sc)
        self._conduit_props = dict(conduit_props)
        self._xsection_props = dict(xsection_props)
        self._node_elevations = dict(node_elevations)
        self._r4_zeta = float(r4_zeta)
        self._r4_gamma = float(r4_gamma)

        # R4_ref is set by the first call to set_r4_reference() (typically
        # after a baseline x=0 SWMM run). Until then R4 is not standardizable.
        self._r4_ref: float | None = None

        # Bucket conduits by subcatchment for efficient aggregation
        self._conduits_per_sc: dict[str, list[str]] = {
            sc: [] for sc in self._sc_names
        }
        for c, sc in self._conduit_to_sc.items():
            if sc in self._conduits_per_sc:
                self._conduits_per_sc[sc].append(c)

        # Precompute Q_full per conduit (Manning) — static, doesn't change
        # with decision variable.
        self._q_full = self._compute_q_full()

        # Load and standardize R1, R2, R3 once.
        r1_norm, r2_norm, r3_norm = self._load_static(resilience_csv)
        self._static_normalized = np.column_stack([r1_norm, r2_norm, r3_norm])

    # ------------------------------------------------------------------
    # Static data
    # ------------------------------------------------------------------

    def _load_static(
        self, path: str
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return standardized (r1, r2, r3) in positive-within-FRI convention."""
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

        # R1: raw distance → invert (closer = more resilient)
        r1_norm = minmax_standardize(raw_dist, positive=False)
        # R2: raw count → positive (more shelters = more resilient)
        r2_norm = minmax_standardize(raw_shelters, positive=True)
        # R3: already a ratio in [0, 1]; clamp for safety.
        r3_norm = np.clip(raw_warn, 0.0, 1.0)

        return r1_norm, r2_norm, r3_norm

    # ------------------------------------------------------------------
    # R4 — Q_full (Manning) — mirrors KPIEvaluation._compute_full_flow_capacities
    # ------------------------------------------------------------------

    def _compute_q_full(self) -> dict[str, float]:
        """Manning full-flow capacity per conduit. Static, computed once."""
        out: dict[str, float] = {}
        for cid, props in self._conduit_props.items():
            xs = self._xsection_props.get(cid, {})
            diameter = xs.get("geom1", 1.0)
            roughness = props.get("roughness", 0.0)
            length = props.get("length", 0.0)

            from_elev = self._node_elevations.get(props["from_node"], 0.0)
            to_elev = self._node_elevations.get(props["to_node"], 0.0)
            in_offset = props.get("in_offset", 0.0)
            out_offset = props.get("out_offset", 0.0)

            elev_up = from_elev + in_offset
            elev_down = to_elev + out_offset
            slope = abs(elev_up - elev_down) / length if length > 0 else 0.001

            area = math.pi * (diameter / 2.0) ** 2
            r_hyd = diameter / 4.0

            if roughness > 0 and r_hyd > 0 and slope > 0:
                q_full = (1.0 / roughness) * area * (r_hyd ** (2.0 / 3.0)) * math.sqrt(slope)
            else:
                q_full = 1.0

            barrels = xs.get("barrels", 1)
            q_full *= barrels
            out[cid] = q_full
        return out

    # ------------------------------------------------------------------
    # R4 — raw accumulator (per SC) from SWMM conduit stats
    # ------------------------------------------------------------------

    def compute_r4_raw(
        self,
        conduit_stats: dict[str, dict],
        sim_duration_hours: float,
    ) -> np.ndarray:
        """Per-SC raw R4 accumulator (higher = more stressed drainage).

        ``R4_s^raw = Σ_c∈SC L_c · [ζ · (Q_peak/Q_full) + γ · (T_surch/T_ref)]``
        """
        t_ref = max(float(sim_duration_hours), 1e-9)
        S = len(self._sc_names)
        raw = np.zeros(S)

        for i, sc in enumerate(self._sc_names):
            accum = 0.0
            for cid in self._conduits_per_sc.get(sc, []):
                cstats = conduit_stats.get(cid)
                props = self._conduit_props.get(cid)
                if cstats is None or props is None:
                    continue

                length = props.get("length", 0.0) / 1000.0  # m → km, matches old F2
                q_full = self._q_full.get(cid, 1.0)
                peak_flow = abs(cstats.get("peak_flow", 0.0))
                t_surch = cstats.get("time_surcharged", 0.0)

                flow_ratio = peak_flow / q_full if q_full > 0 else 0.0
                accum += length * (
                    self._r4_zeta * flow_ratio
                    + self._r4_gamma * (t_surch / t_ref)
                )
            raw[i] = accum

        return raw

    def set_r4_reference(self, baseline_raw: np.ndarray) -> None:
        """Store the R4 reference bound from a baseline (x=0) SWMM run.

        The reference is ``max(baseline_raw)`` across subcatchments — any
        future evaluation produces R4_norm_s = 1 − min(1, raw/ref).
        """
        ref = float(np.max(baseline_raw))
        # Guard against a truly empty baseline (no drainage stress at all).
        self._r4_ref = ref if ref > 1e-9 else 1.0

    @property
    def r4_reference(self) -> float | None:
        return self._r4_ref

    # ------------------------------------------------------------------
    # Full compute — all 4 FRI indicators, per subcatchment
    # ------------------------------------------------------------------

    def compute(
        self,
        conduit_stats: dict[str, dict],
        sim_duration_hours: float,
    ) -> np.ndarray:
        """Return ``(S, 4)`` standardized FRI indicators.

        R4_ref must have been set (either via a prior call to
        :meth:`set_r4_reference` or by passing a baseline run through this
        method first). If ``R4_ref`` is None, R4 column returns all 0.5 as
        an uninformative default.
        """
        static = self._static_normalized  # (S, 3)
        r4_raw = self.compute_r4_raw(conduit_stats, sim_duration_hours)

        if self._r4_ref is None:
            # No reference yet — use this run's max as an on-the-fly fallback
            ref = float(np.max(r4_raw))
            ref = ref if ref > 1e-9 else 1.0
            r4_norm = 1.0 - np.clip(r4_raw / ref, 0.0, 1.0)
        else:
            r4_norm = 1.0 - np.clip(r4_raw / self._r4_ref, 0.0, 1.0)

        return np.column_stack([static, r4_norm])
