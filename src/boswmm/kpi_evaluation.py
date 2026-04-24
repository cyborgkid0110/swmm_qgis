"""Step 2 — KPIEvaluation: run SWMM and compute FROI-based objectives.

This module is now a **thin wrapper** around :class:`src.kpi.froi.FROIComputer`.
It keeps the historical public API (``evaluate(inp_path) -> dict``,
``evaluate_batch``) so the BO loop does not need to know that the
objective function moved to the ``kpi`` package.

The returned ``kpi`` list depends on the optimization mode:
  * ``mode='single'`` → ``[FROI]``    (length 1)
  * ``mode='multi'``  → ``[FHI, FEI, FVI, 1 − FRI]`` (length 4)
"""

from __future__ import annotations

from collections import OrderedDict

from pyswmm import Links, Nodes, Simulation, SystemStats

from src.kpi.froi import FROIComputer


class KPIEvaluation:
    """Run SWMM simulations and compute the FROI objective(s).

    Delegates all index calculations to :class:`FROIComputer`. This class
    owns only the SWMM execution and the mode-dependent kpi packaging.

    Reused both for initial evaluation (Step 2) and inside the optimization
    loop (Step 3.2).
    """

    def __init__(
        self,
        inp_sections: OrderedDict,
        sedimentation: dict[str, float],
        *,
        froi_computer: FROIComputer,
        mode: str = "multi",
    ):
        """
        Args:
            inp_sections: Parsed .inp sections (kept for API compatibility
                with the old signature; the actual parsing is now done
                inside FROIComputer).
            sedimentation: Dict mapping monitored conduit name -> filled_depth.
                Currently unused here — sediment state feeds into scenario
                construction via ScenarioBuilder, not KPI computation.
                Kept in the signature for API compatibility.
            froi_computer: Pre-constructed :class:`FROIComputer`. Typically
                built once at pipeline start and reused across evaluations.
            mode: ``'single'`` or ``'multi'``. Controls the shape of the
                returned ``kpi`` list.
        """
        if mode not in ("single", "multi"):
            raise ValueError(
                f"Unknown mode {mode!r}; expected 'single' or 'multi'"
            )
        self._inp_sections = inp_sections
        self._sedimentation = sedimentation
        self._froi = froi_computer
        self._mode = mode

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def n_objectives(self) -> int:
        return 1 if self._mode == "single" else 4

    def evaluate(self, inp_path: str) -> dict:
        """Run SWMM on a single .inp file and compute the kpi."""
        import os

        if not os.path.isfile(inp_path):
            raise FileNotFoundError(f".inp file not found: {inp_path}")

        node_stats, conduit_stats, sim_duration_hrs = self._run_swmm(inp_path)

        froi_result = self._froi.evaluate(
            node_stats, conduit_stats, sim_duration_hrs
        )

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
