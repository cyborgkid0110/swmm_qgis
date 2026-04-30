"""Step 2 — KPIEvaluation: run SWMM and compute FROI-based objectives.

This module is a **thin wrapper** around :class:`src.kpi.froi.FROIComputer`.
It keeps the public API (``evaluate(inp_path) -> dict``, ``evaluate_batch``)
so the BO loop does not need to know that the objective function lives in the
``kpi`` package.

The returned ``kpi`` list depends on the optimization mode:
  * ``mode='single'`` → ``[FROI]``    (length 1)
  * ``mode='multi'``  → ``[FHI, FEI, FVI, 1 − FRI]`` (length 4)
"""

from __future__ import annotations

from pyswmm import Links, Nodes, Simulation, SystemStats

from src.kpi.froi import FROIComputer
from src.scenario.utils.parser import parse_inp

from ._config import resolve_config as resolve_bo_config


class KPIEvaluation:
    """Run SWMM simulations and compute the FROI objective(s).

    Delegates all index calculations to :class:`FROIComputer`, which is
    constructed internally from the provided configs.  This class owns
    the SWMM execution, baseline sim-time calibration, and mode-dependent
    KPI packaging.

    Reused both for initial evaluation (Step 2) and inside the optimization
    loop (Step 3.2).
    """

    def __init__(
        self,
        base_inp_path: str,
        *,
        kpi_config: dict | str | None = None,
        bo_config: dict | str | None = None,
        mode: str | None = None,
    ):
        """
        Args:
            base_inp_path: Path to the base ``.inp`` model file. Used to
                parse sections for :class:`FROIComputer` and to run a
                baseline SWMM simulation for ``sim_duration_hours``.
            kpi_config: KPI configuration. Accepts a parsed dict, a path
                to a YAML file, or ``None`` to load the KPI package
                default (``src/kpi/config.yaml``).
            bo_config: BO-SWMM configuration. Accepts a parsed dict, a
                path to a YAML file, or ``None`` to load the BO-SWMM
                package default (``src/boswmm/config.yaml``). Used only
                to resolve ``mode`` when it is not provided explicitly.
            mode: ``'single'`` or ``'multi'``. If ``None``, read from
                ``bo_config["optimization"]["mode"]``.
        """
        if mode is None:
            bo_cfg = resolve_bo_config(bo_config)
            mode = bo_cfg["optimization"]["mode"]

        if mode not in ("single", "multi"):
            raise ValueError(
                f"Unknown mode {mode!r}; expected 'single' or 'multi'"
            )

        self._mode = mode

        sections = parse_inp(base_inp_path)
        self._froi = FROIComputer(sections, kpi_config=kpi_config)

        _, _, sim_duration_hours = self._run_swmm(base_inp_path)
        self._froi.set_simulation_time(sim_duration_hours)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def n_objectives(self) -> int:
        return 1 if self._mode == "single" else 4

    @property
    def froi_computer(self) -> FROIComputer:
        return self._froi

    def evaluate(self, inp_path: str) -> dict:
        """Run SWMM on a single .inp file and compute the kpi."""
        import os

        if not os.path.isfile(inp_path):
            raise FileNotFoundError(f".inp file not found: {inp_path}")

        node_stats, _ , _ = self._run_swmm(inp_path)
        froi_result = self._froi.evaluate(node_stats)

        num_flood = sum(1 for s in node_stats.values() if s["flooding_volume"] > 0)
        volume_flood = sum(s["flooding_volume"] for s in node_stats.values())

        return {
            "kpi": froi_result.as_objective_vector(self._mode),
            "froi": froi_result.froi,
            "fhi": froi_result.fhi,
            "fei": froi_result.fei,
            "fvi": froi_result.fvi,
            "fri": froi_result.fri,
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
    def _run_swmm(inp_path: str) -> tuple[dict, dict, float]:
        """Run SWMM and return (node_stats, conduit_stats, duration_hrs)."""
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

                # Expose routing stats for future KPI expansion
                _ = SystemStats(sim).routing_stats

                duration = sim.end_time - sim.start_time
                sim_duration_hrs = duration.total_seconds() / 3600.0

        except Exception as e:
            raise RuntimeError(f"SWMM simulation failed on {inp_path}: {e}") from e

        return node_stats, conduit_stats, sim_duration_hrs
