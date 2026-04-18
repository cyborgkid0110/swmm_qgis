"""Step 2 — KPIEvaluation: run SWMM simulation, compute KPI objectives [F1, F2, F3].

Scenario-state information (remaining sediment depth per monitored conduit) is
obtained via :class:`src.scenario.ScenarioExtractor`; this class is focused on
KPI formulas only.
"""

import math
from collections import OrderedDict

from pyswmm import Links, Nodes, Simulation, SystemStats

from src.scenario import ScenarioExtractor
from src.scenario.utils.geometry import circular_segment_area
from src.scenario.utils.parser import (
    parse_conduits,
    parse_node_elevations,
    parse_xsections,
)

from ._config import resolve_config


class KPIEvaluation:
    """Run SWMM simulations and compute KPI objectives.

    KPIs:
        F1 — Flood Severity Index (lower is better)
        F2 — Drainage Capacity Index (lower is better; stored negated)
        F3 — Sedimentation–Maintenance Index (lower is better)

    Reused both for initial evaluation (Step 2) and inside the optimization
    loop (Step 3.2).
    """

    def __init__(
        self,
        inp_sections: OrderedDict,
        sedimentation: dict[str, float],
        config: dict | None = None,
    ):
        """
        Args:
            inp_sections: Parsed .inp sections (from ScenarioBuilder.base_sections
                or src.scenario.utils.parser.parse_inp).
            sedimentation: Dict mapping monitored conduit name -> filled_depth.
            config: Optional config dict overriding the default ``config.yaml``.
                Expected shape: ``{kpi: {f1, f2, f3}, bo: {...}, constraints: {...}}``.
        """
        cfg = resolve_config(config)
        kpi_cfg = cfg["kpi"]
        self._alpha = kpi_cfg["f1"]["alpha"]
        self._beta = kpi_cfg["f1"]["beta"]
        self._zeta = kpi_cfg["f2"]["zeta"]
        self._gamma = kpi_cfg["f2"]["gamma"]
        self._delta = kpi_cfg["f2"]["delta"]
        self._mu = kpi_cfg["f3"]["mu"]
        self._nu = kpi_cfg["f3"]["nu"]

        self._sedimentation = sedimentation

        self._conduit_props = parse_conduits(inp_sections)
        self._xsection_props = parse_xsections(inp_sections)
        self._node_elevations = parse_node_elevations(inp_sections)

        self._compute_full_flow_capacities()

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def evaluate(self, inp_path: str) -> dict:
        """Run SWMM on a single .inp file and compute KPIs."""
        import os

        if not os.path.isfile(inp_path):
            raise FileNotFoundError(f".inp file not found: {inp_path}")

        node_stats, conduit_stats, sys_routing, sim_duration_hrs = self._run_swmm(
            inp_path
        )

        # Read scenario state via ScenarioExtractor
        extractor = ScenarioExtractor(inp_path)

        f1 = self._compute_f1(node_stats, sys_routing, sim_duration_hrs)
        f2 = self._compute_f2(conduit_stats, sim_duration_hrs)
        f3 = self._compute_f3(extractor)

        num_flood = sum(1 for s in node_stats.values() if s["flooding_volume"] > 0)
        volume_flood = sum(s["flooding_volume"] for s in node_stats.values())

        return {
            "kpi": [f1, f2, f3],
            "num_flood": num_flood,
            "volume_flood": volume_flood,
            "success": True,
        }

    def evaluate_batch(self, inp_paths: list[str]) -> list[dict]:
        """Evaluate multiple .inp files sequentially."""
        return [self.evaluate(p) for p in inp_paths]

    # ------------------------------------------------------------------
    # SWMM simulation
    # ------------------------------------------------------------------

    @staticmethod
    def _run_swmm(inp_path: str) -> tuple[dict, dict, dict, float]:
        node_stats: dict = {}
        conduit_stats: dict = {}

        try:
            with Simulation(inp_path) as sim:
                for _ in sim:
                    pass

                nodes = Nodes(sim)
                for node in nodes:
                    if node.is_junction():
                        node_stats[node.nodeid] = dict(node.statistics)

                links = Links(sim)
                for link in links:
                    if link.is_conduit():
                        conduit_stats[link.linkid] = dict(link.conduit_statistics)

                sys_stats = SystemStats(sim)
                routing_stats = dict(sys_stats.routing_stats)

                duration = sim.end_time - sim.start_time
                sim_duration_hrs = duration.total_seconds() / 3600.0

        except Exception as e:
            raise RuntimeError(f"SWMM simulation failed on {inp_path}: {e}") from e

        return node_stats, conduit_stats, routing_stats, sim_duration_hrs

    # ------------------------------------------------------------------
    # F1 — Flood Severity Index
    # ------------------------------------------------------------------

    def _compute_f1(
        self,
        node_stats: dict,
        routing_stats: dict,
        sim_duration_hrs: float,
    ) -> float:
        num_nodes = len(node_stats)
        if num_nodes == 0:
            return 0.0

        total_inflow = (
            routing_stats.get("wet_weather_inflow", 0.0)
            + routing_stats.get("external_inflow", 0.0)
        )
        v_ref = total_inflow / num_nodes if total_inflow > 0 else 1.0
        t_ref = sim_duration_hrs if sim_duration_hrs > 0 else 1.0

        f1 = 0.0
        for stats in node_stats.values():
            v_flood = stats.get("flooding_volume", 0.0)
            t_flood = stats.get("flooding_duration", 0.0)
            f1 += self._alpha * (v_flood / v_ref) + self._beta * (t_flood / t_ref)

        return f1

    # ------------------------------------------------------------------
    # F2 — Drainage Capacity Index
    # ------------------------------------------------------------------

    def _compute_f2(self, conduit_stats: dict, sim_duration_hrs: float) -> float:
        t_ref = sim_duration_hrs if sim_duration_hrs > 0 else 1.0

        f2 = 0.0
        for cid, cstats in conduit_stats.items():
            props = self._conduit_props.get(cid)
            if props is None:
                continue

            length = props["length"] / 1000
            q_full = props.get("q_full", 1.0)

            peak_flow = abs(cstats.get("peak_flow", 0.0))
            t_surch = cstats.get("time_surcharged", 0.0)

            flow_ratio = peak_flow / q_full if q_full > 0 else 0.0

            f2l = length * (
                self._zeta * flow_ratio + self._gamma * (t_surch / t_ref)
            )
            f2 -= f2l

        return f2

    # ------------------------------------------------------------------
    # F3 — Sedimentation-Maintenance Index
    # ------------------------------------------------------------------

    def _compute_f3(self, extractor: ScenarioExtractor) -> float:
        """F3 = Σ μ · (A_seg(h_remaining) / A_pipe) over monitored conduits.

        ``h_remaining`` is read from the scenario's ``[XSECTIONS]`` Geom2 via
        ``ScenarioExtractor``, which reflects maintenance already applied.
        Fully cleaned conduits (scenario shape ``CIRCULAR``) contribute 0.
        """
        f3 = 0.0
        for cid in self._sedimentation:
            h = extractor.remaining_depth(cid)
            if h <= 0.0:
                continue

            props = self._conduit_props.get(cid)
            if props is None:
                continue

            length = props["length"]
            diameter = self._xsection_props.get(cid, {}).get("geom1", 1.0)
            r = diameter / 2.0

            if r <= 0 or length <= 0:
                continue

            h_eff = min(h, diameter)
            a_seg = circular_segment_area(h_eff, r)
            a_pipe = math.pi * r * r
            f3 += self._mu * (a_seg / a_pipe)

        return f3

    # ------------------------------------------------------------------
    # Full-flow capacity (Manning equation)
    # ------------------------------------------------------------------

    def _compute_full_flow_capacities(self) -> None:
        """Compute Q_full and pipe_volume for each conduit using Manning."""
        for cid, props in self._conduit_props.items():
            xs = self._xsection_props.get(cid, {})
            shape = xs.get("shape", "CIRCULAR")
            diameter = xs.get("geom1", 1.0)
            roughness = props["roughness"]
            length = props["length"]

            from_elev = self._node_elevations.get(props["from_node"], 0.0)
            to_elev = self._node_elevations.get(props["to_node"], 0.0)
            in_offset = props.get("in_offset", 0.0)
            out_offset = props.get("out_offset", 0.0)

            elev_up = from_elev + in_offset
            elev_down = to_elev + out_offset
            slope = abs(elev_up - elev_down) / length if length > 0 else 0.001

            if shape in ("CIRCULAR", "FILLED_CIRCULAR"):
                area = math.pi * (diameter / 2.0) ** 2
                r_hyd = diameter / 4.0
            else:
                area = math.pi * (diameter / 2.0) ** 2
                r_hyd = diameter / 4.0

            if roughness > 0 and r_hyd > 0 and slope > 0:
                q_full = (1.0 / roughness) * area * (r_hyd ** (2.0 / 3.0)) * math.sqrt(slope)
            else:
                q_full = 1.0

            barrels = xs.get("barrels", 1)
            q_full *= barrels
            pipe_volume = area * length * barrels

            props["q_full"] = q_full
            props["pipe_volume"] = pipe_volume
