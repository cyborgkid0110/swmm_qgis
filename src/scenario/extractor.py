"""ScenarioExtractor — read scenario ``.inp`` files and derive scenario state.

Given a path to a scenario ``.inp`` (typically produced by ``ScenarioBuilder``),
this class exposes parsed sections plus higher-level scenario-state
information: which monitored conduits are fully cleaned vs partially cleaned
vs untouched, and what sediment depth remains in each.

ScenarioExtractor is independent of ScenarioBuilder — it never writes
scenarios, and depends only on ``scenario.utils`` parsers.

Keep this focused on scenario *state* only; objective/KPI computation lives
in ``KPIEvaluation``.
"""

from collections import OrderedDict

from .utils.parser import parse_inp, parse_xsections


# Sentinel states for each monitored conduit
STATE_UNTOUCHED = "untouched"          # shape is FILLED_CIRCULAR with full filled_depth
STATE_PARTIAL = "partial"              # shape is FILLED_CIRCULAR with reduced depth
STATE_CLEANED = "cleaned"              # shape is CIRCULAR (fully maintained)


class ScenarioExtractor:
    """Read and summarize the state of a scenario ``.inp`` file."""

    def __init__(self, inp_path: str):
        self._inp_path = inp_path
        self._sections = parse_inp(inp_path)
        self._xsections = parse_xsections(self._sections)

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def inp_path(self) -> str:
        return self._inp_path

    @property
    def sections(self) -> OrderedDict:
        return self._sections

    @property
    def xsections(self) -> dict:
        return self._xsections

    # ------------------------------------------------------------------
    # Scenario-state queries
    # ------------------------------------------------------------------

    def remaining_depth(self, conduit_name: str) -> float:
        """Remaining sediment depth (m) in ``conduit_name`` after maintenance.

        Returns ``0.0`` if the conduit is ``CIRCULAR`` (fully cleaned) or
        absent from ``[XSECTIONS]``.
        """
        xs = self._xsections.get(conduit_name, {})
        if xs.get("shape") != "FILLED_CIRCULAR":
            return 0.0
        return float(xs.get("geom2", 0.0))

    def remaining_depths(self, conduit_names: list[str]) -> dict[str, float]:
        """Batch query: ``{name: remaining_depth}`` for each requested conduit."""
        return {name: self.remaining_depth(name) for name in conduit_names}

    def state_of(
        self, conduit_name: str, filled_depth: float, tol: float = 1e-9
    ) -> str:
        """Classify a monitored conduit as cleaned / partial / untouched.

        ``filled_depth`` is the original sediment depth (from the sedimentation
        CSV). ``tol`` guards against floating-point jitter around the
        boundaries.
        """
        xs = self._xsections.get(conduit_name, {})
        shape = xs.get("shape")
        if shape == "CIRCULAR":
            return STATE_CLEANED
        if shape != "FILLED_CIRCULAR":
            # Unknown / missing -> treat as untouched
            return STATE_UNTOUCHED
        h = float(xs.get("geom2", 0.0))
        if h >= filled_depth - tol:
            return STATE_UNTOUCHED
        return STATE_PARTIAL

    def states(
        self, filled_depths: dict[str, float], tol: float = 1e-9
    ) -> dict[str, str]:
        """Classify every monitored conduit in one call."""
        return {
            name: self.state_of(name, depth, tol=tol)
            for name, depth in filled_depths.items()
        }
