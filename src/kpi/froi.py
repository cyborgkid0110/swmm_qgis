"""FROI orchestrator.

:class:`FROIComputer` wires together the four indicator groups and the weight
system (IFAHP + EWM + combined) into a single per-evaluation entry point.

Pipeline per SWMM evaluation:

  1. HazardIndicators        -> (S, 2) H_norm, dynamic
  2. ExposureIndicators      -> (S, 4) E_norm, cached
  3. VulnerabilityIndicators -> (S, 3) V_norm, cached
  4. ResilienceIndicators    -> (S, 3) R_norm, cached (R1-R3 all static)
  5. Per-SC indices:
       FHI_s = H_norm @ rho_H
       FEI_s = E_norm @ rho_E
       FVI_s = FHI_s * (V_norm @ rho_V)    <- dynamic scaling
       FRI_s = R_norm @ rho_R
  6. Region aggregation (simple or area-weighted).
  7. FROI = FHI * FEI * FVI * (1 - FRI).

Weights are computed once at init via IFAHP (subjective) + EWM (objective) +
preference-coefficient combination.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ._config import resolve_config
from .aggregator import (
    UNASSIGNED,
    aggregate_to_region,
    build_conduit_subcatchment_map,
    build_junction_subcatchment_map,
    parse_subcatchment_areas,
)
from .indicators import (
    ExposureIndicators,
    HazardIndicators,
    ResilienceIndicators,
    VulnerabilityIndicators,
)
from .weights import combined_weights, ewm_weights, ifahp_weights
from src.scenario.utils.parser import (
    parse_conduits,
    parse_node_elevations,
    parse_xsections,
)


@dataclass
class FROIResult:
    """Output of :meth:`FROIComputer.evaluate`."""

    fhi: float
    fei: float
    fvi: float
    fri: float
    froi: float

    fhi_per_sc: np.ndarray
    fei_per_sc: np.ndarray
    fvi_per_sc: np.ndarray
    fri_per_sc: np.ndarray

    def as_objective_vector(self, mode: str) -> list[float]:
        """Return the kpi vector BOSWMM will minimize.

        ``mode='single'`` -> ``[FROI]``
        ``mode='multi'``  -> ``[FHI, FEI, FVI, 1 - FRI]``
        """
        if mode == "single":
            return [self.froi]
        if mode == "multi":
            return [self.fhi, self.fei, self.fvi, 1.0 - self.fri]
        raise ValueError(f"Unknown mode: {mode!r}")


class FROIComputer:
    """Compute FROI (and its sub-indices) from SWMM simulation results."""

    def __init__(
        self,
        inp_sections: dict,
        *,
        kpi_config: dict | str | None = None,
    ):
        """
        Args:
            inp_sections: Parsed .inp sections (``parse_inp(path)`` output).
            kpi_config: KPI configuration. Accepts a parsed dict, a path to a
                YAML file, or ``None`` to load the package default
                (``src/kpi/config.yaml``).
        """
        cfg = resolve_config(kpi_config)

        exposure_csv = cfg["data_paths"]["exposure"]
        vulnerability_csv = cfg["data_paths"]["vulnerability"]
        resilience_csv = cfg["data_paths"]["resilience"]
        expert_matrices = load_expert_matrices(cfg["weights"]["expert_matrices"])
        rainfall_depth_mm = cfg["indicators"]["fhi"]["rainfall_depth_mm"]
        aggregation_method = cfg["aggregation"]["method"]

        # --- Spatial mapping ---
        self._sc_names = list(self._parse_sc_order(inp_sections))
        self._areas = parse_subcatchment_areas(inp_sections)
        self._conduit_props = parse_conduits(inp_sections)
        self._xsection_props = parse_xsections(inp_sections)
        self._node_elevations = parse_node_elevations(inp_sections)

        self._j2sc = build_junction_subcatchment_map(inp_sections)
        self._c2sc = build_conduit_subcatchment_map(
            self._j2sc, self._conduit_props
        )

        self._aggregation_method = aggregation_method

        # --- Indicator groups ---
        self._fhi = HazardIndicators(
            self._sc_names,
            self._j2sc,
            self._areas,
            rainfall_depth_mm=rainfall_depth_mm,
        )
        self._fei = ExposureIndicators(self._sc_names, exposure_csv)
        self._fvi = VulnerabilityIndicators(self._sc_names, vulnerability_csv)
        self._fri = ResilienceIndicators(self._sc_names, resilience_csv)

        # --- Weights ---
        self._weights = self._compute_weights(expert_matrices)

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_sc_order(sections: dict) -> list[str]:
        """Ordered list of subcatchment names from ``[SUBCATCHMENTS]``."""
        names: list[str] = []
        for line in sections.get("SUBCATCHMENTS", []):
            stripped = line.strip()
            if not stripped or stripped.startswith(";"):
                continue
            tokens = stripped.split()
            if tokens:
                names.append(tokens[0])
        return names

    def _compute_weights(
        self, expert_matrices: dict[str, list[np.ndarray]]
    ) -> dict[str, np.ndarray]:
        """IFAHP x EWM x combined per group. Returns ``{group: weight_vector}``."""
        out: dict[str, np.ndarray] = {}

        data_for_ewm = {
            "fhi": np.zeros((len(self._sc_names), 2)),
            "fei": self._fei.compute(),
            "fvi": self._fvi.compute(),
            "fri": self._fri.compute(),
        }

        for group, matrices in expert_matrices.items():
            ifahp_res = ifahp_weights(matrices)
            omega = ifahp_res.weights
            theta = ewm_weights(data_for_ewm[group])
            if omega.shape != theta.shape:
                raise ValueError(
                    f"Weight-shape mismatch for group {group!r}: "
                    f"IFAHP {omega.shape} vs EWM {theta.shape}"
                )
            out[group] = combined_weights(omega, theta)

        return out

    # ------------------------------------------------------------------
    # Public: per-evaluation scoring
    # ------------------------------------------------------------------

    def evaluate(
        self,
        node_stats: dict[str, dict],
    ) -> FROIResult:
        """Compute FHI/FEI/FVI/FRI/FROI for one SWMM result set."""
        h_norm, _ = self._fhi.compute(node_stats)
        e_norm = self._fei.compute()
        v_norm = self._fvi.compute()
        r_norm = self._fri.compute()

        fhi_per_sc = h_norm @ self._weights["fhi"]
        fei_per_sc = e_norm @ self._weights["fei"]
        fvi_raw_per_sc = v_norm @ self._weights["fvi"]
        fvi_per_sc = fhi_per_sc * fvi_raw_per_sc
        fri_per_sc = r_norm @ self._weights["fri"]

        fhi = self._aggregate(fhi_per_sc)
        fei = self._aggregate(fei_per_sc)
        fvi = self._aggregate(fvi_per_sc)
        fri = self._aggregate(fri_per_sc)

        froi = fhi * fei * fvi * (1.0 - fri)

        return FROIResult(
            fhi=fhi, fei=fei, fvi=fvi, fri=fri, froi=froi,
            fhi_per_sc=fhi_per_sc,
            fei_per_sc=fei_per_sc,
            fvi_per_sc=fvi_per_sc,
            fri_per_sc=fri_per_sc,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _aggregate(self, per_sc_vec: np.ndarray) -> float:
        """Collapse a (S,) per-SC vector to a region scalar."""
        mapping = {sc: float(per_sc_vec[i]) for i, sc in enumerate(self._sc_names)}
        return aggregate_to_region(
            mapping, areas=self._areas, method=self._aggregation_method
        )

    # ------------------------------------------------------------------
    # Introspection (useful for debugging and reporting)
    # ------------------------------------------------------------------

    @property
    def weights(self) -> dict[str, np.ndarray]:
        return {k: v.copy() for k, v in self._weights.items()}

    @property
    def subcatchment_names(self) -> list[str]:
        return list(self._sc_names)
    
    def set_simulation_time(self, sim_duration_hours):
        self._fhi._set_simulation_time(sim_duration_hours)


# ----------------------------------------------------------------------
# Expert matrix I/O -- load JSON stubs into numpy arrays
# ----------------------------------------------------------------------

def load_expert_matrices(paths: dict[str, str]) -> dict[str, list[np.ndarray]]:
    """Load expert matrices from ``{group: json_path}`` mapping.

    Each JSON file has the schema::

        {
          "group": "FHI",
          "indicators": ["H1", "H2"],
          "experts": [
            {"name": "Expert 1", "matrix": [[[0.5,0.5], [0.6,0.2]],
                                             [[0.2,0.6], [0.5,0.5]]]}
          ]
        }
    """
    out: dict[str, list[np.ndarray]] = {}
    for group, path in paths.items():
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"Expert matrix file not found: {p}")
        with p.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        matrices = [np.array(exp["matrix"], dtype=float) for exp in payload["experts"]]
        if not matrices:
            raise ValueError(f"No expert matrices in {p}")
        out[group] = matrices
    return out
