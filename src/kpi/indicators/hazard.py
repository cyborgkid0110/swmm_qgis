"""FHI — Flood Hazard Index.

Two dynamic indicators from SWMM node statistics:

  * H1 — Flood duration (mean per subcatchment, reference = simulation duration)
  * H2 — Flood volume   (sum per subcatchment, reference = per-SC rainfall volume)

``HazardIndicators.compute(node_stats, ...)`` returns both a standardized
matrix ``(S, 2)`` for FROI accumulation and the per-subcatchment FHI vector
``(S,)`` that :class:`VulnerabilityIndicators` uses to scale FVI.
"""

from __future__ import annotations

import numpy as np

from .base import IndicatorGroup, reference_standardize


class HazardIndicators(IndicatorGroup):
    """Compute FHI from SWMM node statistics."""

    group_name = "FHI"
    indicator_names = ["H1_flood_duration", "H2_flood_volume"]

    def __init__(
        self,
        subcatchment_names: list[str],
        junction_to_sc: dict[str, str],
        subcatchment_areas: dict[str, float],
        *,
        rainfall_depth_mm: float = 50.0,
        sim_duration_hours: float = 1.0,
    ):
        """
        Args:
            subcatchment_names: Ordered list of SC names. Defines row index.
            junction_to_sc: ``{junction_name: subcatchment_name}`` from
                :func:`src.kpi.aggregator.build_junction_subcatchment_map`.
            subcatchment_areas: ``{subcatchment_name: area_in_hectares}``.
                Used to compute the per-SC rainfall-volume reference for H2.
            rainfall_depth_mm: Total rainfall depth over the simulation, mm.
                Used to derive per-SC reference volume V_ref,s =
                depth · area · 10 (mm · ha → m³).
            sim_duration_hours: Simulation duration. Used as T_ref for H1.
        """
        self._sc_names = list(subcatchment_names)
        self._junction_to_sc = dict(junction_to_sc)
        self._areas = dict(subcatchment_areas)
        self._rainfall_depth_mm = float(rainfall_depth_mm)
        self._sim_duration_hours = max(float(sim_duration_hours), 1e-9)

        # Per-SC V_ref (m³): rainfall_mm · area_ha · 10
        # (1 mm · 1 ha = 10 m³; the 10000 (ha→m²) × 0.001 (mm→m) = 10)
        self._v_ref_per_sc = {
            sc: self._rainfall_depth_mm * self._areas.get(sc, 0.0) * 10.0
            for sc in self._sc_names
        }

        # Precompute inverse: {sc: [junctions_in_sc]} for efficient aggregation
        self._junctions_per_sc: dict[str, list[str]] = {
            sc: [] for sc in self._sc_names
        }
        for j, sc in self._junction_to_sc.items():
            if sc in self._junctions_per_sc:
                self._junctions_per_sc[sc].append(j)

    def compute(
        self,
        node_stats: dict[str, dict],
        sim_duration_hours: float | None = None,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Compute H1, H2 per subcatchment and standardize.

        Args:
            node_stats: ``{junction_name: node.statistics dict}``.
                Must contain ``flooding_duration`` (hours) and
                ``flooding_volume`` (m³ or 10⁶ L — see pyswmm units).
            sim_duration_hours: Overrides the constructor value if provided
                (so the same instance can be reused across simulations with
                different duration).

        Returns:
            ``(normalized, fhi_s_raw)`` where:
              * ``normalized``: shape ``(S, 2)``; columns are
                ``[H1_norm, H2_norm]`` each in [0, 1].
              * ``fhi_s_raw``: shape ``(S, 2)``, same as normalized — caller
                combines with weights to get per-SC FHI_s. Exposed separately
                so VulnerabilityIndicators can read the computed FHI_s.
                (FHI_s itself is computed in FROIComputer after weights
                are applied — this method stops at standardized indicators.)
        """
        t_ref = (
            float(sim_duration_hours)
            if sim_duration_hours is not None
            else self._sim_duration_hours
        )
        t_ref = max(t_ref, 1e-9)

        S = len(self._sc_names)
        h1_raw = np.zeros(S)
        h2_raw = np.zeros(S)

        for i, sc in enumerate(self._sc_names):
            junctions = self._junctions_per_sc.get(sc, [])
            if not junctions:
                continue

            durations = []
            volume_total = 0.0
            for j in junctions:
                stats = node_stats.get(j)
                if stats is None:
                    continue
                durations.append(stats.get("flooding_duration", 0.0))
                volume_total += stats.get("flooding_volume", 0.0)

            if durations:
                h1_raw[i] = float(np.mean(durations))
            h2_raw[i] = volume_total

        h1_norm = reference_standardize(h1_raw, reference=t_ref, positive=True)

        # H2 uses per-SC reference volume, not a scalar.
        h2_norm = np.zeros(S)
        for i, sc in enumerate(self._sc_names):
            v_ref = self._v_ref_per_sc.get(sc, 0.0)
            if v_ref > 1e-9:
                h2_norm[i] = min(1.0, h2_raw[i] / v_ref)
            else:
                h2_norm[i] = 0.0

        normalized = np.column_stack([h1_norm, h2_norm])
        return normalized, normalized.copy()

    def compute_fhi_per_sc(
        self,
        normalized: np.ndarray,
        weights: np.ndarray,
    ) -> np.ndarray:
        """Return ``FHI_s`` vector of shape ``(S,)`` from normalized indicators.

        ``FHI_s = Σ_m ρ_m · H_m,s``.
        """
        return normalized @ weights
