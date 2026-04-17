"""Step 2 — KPIEvaluation: run SWMM simulation, compute KPI objectives [F1, F2, F3]."""

import math
import os
from collections import OrderedDict

import yaml
from pyswmm import Links, Nodes, Simulation, SystemStats

from .input import InputqEHVISWMM

# Load default config from config.yaml next to this file
_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")
with open(_CONFIG_PATH, "r", encoding="utf-8") as _f:
    _DEFAULT_CONFIG = yaml.safe_load(_f)


class KPIEvaluation:
    """Run SWMM simulations and compute KPI objectives.

    KPIs:
        F1 — Flood Severity Index (lower is better)
        F2 — Drainage Capacity Index (lower is better)
        F3 — Sedimentation–Maintenance Index (lower is better)

    This class is reused both for initial evaluation (Step 2) and
    inside the optimization loop (Step 3.2).
    """

    def __init__(
        self,
        inp_sections: OrderedDict,
        sedimentation: dict[str, float],
        config: dict | None = None,
    ):
        """
        Args:
            inp_sections: Parsed .inp sections from InputqEHVISWMM._parse_inp().
            sedimentation: Dict mapping conduit_name -> filled_depth.
            config: Optional config dict overriding defaults from config.yaml.
                    Expected structure: {f1: {alpha, beta}, f2: {zeta, gamma, delta}, f3: {mu, nu}}
        """
        cfg = config or _DEFAULT_CONFIG
        self._alpha = cfg["f1"]["alpha"]
        self._beta = cfg["f1"]["beta"]
        self._zeta = cfg["f2"]["zeta"]
        self._gamma = cfg["f2"]["gamma"]
        self._delta = cfg["f2"]["delta"]
        self._mu = cfg["f3"]["mu"]
        self._nu = cfg["f3"]["nu"]

        self._sedimentation = sedimentation

        # Parse static properties from .inp sections
        self._conduit_props = self._parse_conduits(inp_sections)
        self._xsection_props = self._parse_xsections(inp_sections)
        self._node_elevations = self._parse_node_elevations(inp_sections)

        # Pre-compute Q_full and pipe volumes for each conduit
        self._compute_full_flow_capacities()

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def evaluate(self, inp_path: str) -> dict:
        """Run SWMM on a single .inp file and compute KPIs.

        Args:
            inp_path: Path to the .inp file to simulate.

        Returns:
            Dict with keys:
                kpi: [F1, F2, F3] as list of floats
                num_flood: number of junctions with flooding
                volume_flood: total flood volume (m3) across all junctions
                success: True

        Raises:
            RuntimeError: If SWMM simulation fails.
        """
        if not os.path.isfile(inp_path):
            raise FileNotFoundError(f".inp file not found: {inp_path}")

        # Run simulation
        node_stats, conduit_stats, sys_routing, sim_duration_hrs = self._run_swmm(
            inp_path
        )

        # Parse scenario-specific XSECTIONS to determine actual sedimentation state
        scenario_sections = InputqEHVISWMM._parse_inp(inp_path)
        scenario_xs = self._parse_xsections(scenario_sections)

        # Compute KPIs
        f1 = self._compute_f1(node_stats, sys_routing, sim_duration_hrs)
        f2 = self._compute_f2(conduit_stats, sim_duration_hrs)
        f3 = self._compute_f3(scenario_xs)

        # Extract summary metrics
        num_flood = sum(
            1 for s in node_stats.values() if s["flooding_volume"] > 0
        )
        volume_flood = sum(s["flooding_volume"] for s in node_stats.values())

        return {
            "kpi": [f1, f2, f3],
            "num_flood": num_flood,
            "volume_flood": volume_flood,
            "success": True,
        }

    def evaluate_batch(self, inp_paths: list[str]) -> list[dict]:
        """Evaluate multiple .inp files sequentially.

        Args:
            inp_paths: List of .inp file paths.

        Returns:
            List of result dicts (same format as evaluate()).
        """
        return [self.evaluate(p) for p in inp_paths]

    # ------------------------------------------------------------------
    # SWMM simulation
    # ------------------------------------------------------------------

    @staticmethod
    def _run_swmm(
        inp_path: str,
    ) -> tuple[dict, dict, dict, float]:
        """Run SWMM simulation and extract statistics.

        Returns:
            (node_stats, conduit_stats, routing_stats, sim_duration_hours)

        Raises:
            RuntimeError: If simulation encounters errors.
        """
        node_stats = {}
        conduit_stats = {}

        try:
            with Simulation(inp_path) as sim:
                for step in sim:
                    pass

                # Collect node statistics (junctions only)
                nodes = Nodes(sim)
                for node in nodes:
                    if node.is_junction():
                        node_stats[node.nodeid] = dict(node.statistics)

                # Collect conduit statistics
                links = Links(sim)
                for link in links:
                    if link.is_conduit():
                        conduit_stats[link.linkid] = dict(link.conduit_statistics)

                # System routing stats
                sys_stats = SystemStats(sim)
                routing_stats = dict(sys_stats.routing_stats)

                # Simulation duration
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
        """F1 = Σ w_i * [ α * V_flood/V_ref + β * T_flood/T_ref ]

        w_i = 1.0 (uniform weight)
        V_ref = total system inflow / number of nodes
        T_ref = simulation duration
        """
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

    def _compute_f2(
        self,
        conduit_stats: dict,
        sim_duration_hrs: float,
    ) -> float:
        """F2 = Σ L_j * [ ζ * (avg_flow/Q_full) + γ * (T_surch/T_ref) ]"""
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
                self._zeta * flow_ratio
                + self._gamma * (t_surch / t_ref)
            )
            f2 -= f2l

        return f2

    # ------------------------------------------------------------------
    # F3 — Sedimentation-Maintenance Index
    # ------------------------------------------------------------------

    def _compute_f3(self, scenario_xs: dict) -> float:
        """F3 = Σ μ * (V_sed_j / V_pipe_j)

        Sedimentation volume is computed as the area of a circular segment:
            A_seg = R² * arccos((R - h) / R) - (R - h) * sqrt(2Rh - h²)
        where R = diameter/2 and h = filled_depth.

        V_sed = A_seg * L_j
        V_pipe = π * R² * L_j

        Only counts conduits that are FILLED_CIRCULAR in the scenario
        (i.e., conduits NOT maintained). Maintained conduits contribute 0.

        Args:
            scenario_xs: Parsed XSECTIONS from the scenario .inp file.
        """
        f3 = 0.0
        for cid, filled_depth in self._sedimentation.items():
            xs = scenario_xs.get(cid, {})
            if xs.get("shape") != "FILLED_CIRCULAR":
                continue

            props = self._conduit_props.get(cid)
            if props is None:
                continue

            length = props["length"]
            diameter = self._xsection_props.get(cid, {}).get("geom1", 1.0)
            r = diameter / 2.0
            h = filled_depth

            if r <= 0 or h <= 0 or length <= 0:
                continue

            # Clamp h to diameter
            h = min(h, diameter)

            # Circular segment area: A = R² arccos((R-h)/R) - (R-h) sqrt(2Rh - h²)
            a_seg = r**2 * math.acos((r - h) / r) - (r - h) * math.sqrt(2 * r * h - h**2)
            a_pipe = math.pi * r**2

            f3 += self._mu * (a_seg / a_pipe)

        return f3

    # ------------------------------------------------------------------
    # .inp static property parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_conduits(sections: OrderedDict) -> dict:
        """Parse [CONDUITS] section for length, roughness, connectivity.

        Returns dict: {conduit_name: {length, roughness, from_node, to_node}}
        """
        props = {}
        for line in sections.get("CONDUITS", []):
            stripped = line.strip()
            if not stripped or stripped.startswith(";"):
                continue
            tokens = stripped.split()
            if len(tokens) < 5:
                continue
            name = tokens[0]
            props[name] = {
                "from_node": tokens[1],
                "to_node": tokens[2],
                "length": float(tokens[3]),
                "roughness": float(tokens[4]),
                "in_offset": float(tokens[5]) if len(tokens) > 5 and tokens[5] != '*' else 0.0,
                "out_offset": float(tokens[6]) if len(tokens) > 6 and tokens[6] != '*' else 0.0,
            }
        return props

    @staticmethod
    def _parse_xsections(sections: OrderedDict) -> dict:
        """Parse [XSECTIONS] for shape and geometry.

        Returns dict: {link_name: {shape, geom1, geom2, geom3, geom4, barrels}}
        """
        props = {}
        for line in sections.get("XSECTIONS", []):
            stripped = line.strip()
            if not stripped or stripped.startswith(";"):
                continue
            tokens = stripped.split()
            if len(tokens) < 3:
                continue
            name = tokens[0]
            props[name] = {
                "shape": tokens[1],
                "geom1": float(tokens[2]) if len(tokens) > 2 else 0.0,
                "geom2": float(tokens[3]) if len(tokens) > 3 else 0.0,
                "geom3": float(tokens[4]) if len(tokens) > 4 else 0.0,
                "geom4": float(tokens[5]) if len(tokens) > 5 else 0.0,
                "barrels": int(float(tokens[6])) if len(tokens) > 6 else 1,
            }
        return props

    @staticmethod
    def _parse_node_elevations(sections: OrderedDict) -> dict:
        """Parse [JUNCTIONS] and [OUTFALLS] for invert elevations.

        Returns dict: {node_name: elevation}
        """
        elevations = {}
        # Junctions: Name Elevation MaxDepth InitDepth SurDepth Aponded
        for line in sections.get("JUNCTIONS", []):
            stripped = line.strip()
            if not stripped or stripped.startswith(";"):
                continue
            tokens = stripped.split()
            if len(tokens) >= 2:
                elevations[tokens[0]] = float(tokens[1])
        # Outfalls: Name Elevation Type ...
        for line in sections.get("OUTFALLS", []):
            stripped = line.strip()
            if not stripped or stripped.startswith(";"):
                continue
            tokens = stripped.split()
            if len(tokens) >= 2:
                elevations[tokens[0]] = float(tokens[1])
        return elevations

    # ------------------------------------------------------------------
    # Full-flow capacity (Manning equation)
    # ------------------------------------------------------------------

    def _compute_full_flow_capacities(self) -> None:
        """Compute Q_full and pipe_volume for each conduit using Manning equation.

        Q_full = (1/n) * A * R^(2/3) * S^(1/2)   [for CIRCULAR pipes]
        where A = π(D/2)², R = D/4, S = |Δelev| / L
        """
        for cid, props in self._conduit_props.items():
            xs = self._xsection_props.get(cid, {})
            shape = xs.get("shape", "CIRCULAR")
            diameter = xs.get("geom1", 1.0)
            roughness = props["roughness"]
            length = props["length"]

            # Compute slope from node elevations + offsets
            from_elev = self._node_elevations.get(props["from_node"], 0.0)
            to_elev = self._node_elevations.get(props["to_node"], 0.0)
            in_offset = props.get("in_offset", 0.0)
            out_offset = props.get("out_offset", 0.0)

            elev_up = from_elev + in_offset
            elev_down = to_elev + out_offset
            slope = abs(elev_up - elev_down) / length if length > 0 else 0.001

            # Compute full-flow for circular / filled_circular
            if shape in ("CIRCULAR", "FILLED_CIRCULAR"):
                area = math.pi * (diameter / 2.0) ** 2
                r_hyd = diameter / 4.0
            else:
                # Fallback: treat as circular with geom1 as diameter
                area = math.pi * (diameter / 2.0) ** 2
                r_hyd = diameter / 4.0

            if roughness > 0 and r_hyd > 0 and slope > 0:
                q_full = (1.0 / roughness) * area * (r_hyd ** (2.0 / 3.0)) * math.sqrt(slope)
            else:
                q_full = 1.0  # fallback to avoid division by zero

            barrels = xs.get("barrels", 1)
            q_full *= barrels

            pipe_volume = area * length * barrels

            props["q_full"] = q_full
            props["pipe_volume"] = pipe_volume
