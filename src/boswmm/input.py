"""Step 1 — Input.

Thin facade that keeps the public API stable while delegating scenario
construction to :class:`src.scenario.ScenarioBuilder`. Use this when you want
the BO-SWMM pipeline's Step 1 entry point; the underlying builder is
available via ``inp.scenario_builder`` if callers need richer access.
"""

from collections import OrderedDict

import torch

from src.scenario import ScenarioBuilder


class Input:
    """Step 1 of the BO-SWMM pipeline — load base model + produce scenarios.

    Decision variable ``x ∈ R^N`` with ``x[i] ∈ [0, v_max[i]]``:
        x[i] = 0           -> no maintenance at conduit i
        0 < x[i] < v_max   -> partial maintenance (FILLED_CIRCULAR with h')
        x[i] = v_max[i]    -> fully cleaned (CIRCULAR)
    """

    def __init__(
        self,
        base_inp_path: str,
        sedimentation_csv: str,
        rainfall_csv: str | None = None,
        discharge_csv: str | None = None,
        output_dir: str | None = None,
    ):
        self._builder = ScenarioBuilder(
            base_inp_path=base_inp_path,
            sedimentation_csv=sedimentation_csv,
            rainfall_csv=rainfall_csv,
            discharge_csv=discharge_csv,
            output_dir=output_dir,
        )

    # ------------------------------------------------------------------
    # Public properties (delegate to builder)
    # ------------------------------------------------------------------

    @property
    def scenario_builder(self) -> ScenarioBuilder:
        """Underlying :class:`ScenarioBuilder` — exposed for advanced callers."""
        return self._builder

    @property
    def N(self) -> int:
        return self._builder.N

    @property
    def conduit_names(self) -> list[str]:
        return self._builder.conduit_names

    @property
    def filled_depths(self) -> dict[str, float]:
        return self._builder.filled_depths

    @property
    def base_sections(self) -> OrderedDict:
        return self._builder.base_sections

    @property
    def output_dir(self) -> str:
        return self._builder.output_dir

    @property
    def v_max(self) -> torch.Tensor:
        return self._builder.v_max

    @property
    def v_max_sum(self) -> float:
        return self._builder.v_max_sum

    # ------------------------------------------------------------------
    # Public methods (delegate to builder)
    # ------------------------------------------------------------------

    def build_scenario(self, x: torch.Tensor, scenario_id: int = 0) -> str:
        return self._builder.build_scenario(x, scenario_id=scenario_id)

    def build_scenarios(self, X: torch.Tensor) -> list[str]:
        return self._builder.build_scenarios(X)
