"""qEHVI-SWMM — multi-objective Bayesian optimization for sediment maintenance.

Public API:
  * :class:`InputqEHVISWMM` — Step 1: scenario loading and .inp modification.
  * :class:`KPIEvaluation` — Step 2: SWMM execution and KPI computation.
  * :class:`qEHVISWMM` — Step 3: BO loop (GP + qEHVI + Pareto update).
  * :class:`OutputqEHVISWMM` — Step 4: Pareto extraction and JSON report.

Scenario-level operations (``.inp`` mutation, state extraction) live in the
sibling package :mod:`src.scenario`.
"""

from .input import InputqEHVISWMM
from .kpi_evaluation import KPIEvaluation
from .output import OutputqEHVISWMM
from .qehvi_swmm import qEHVISWMM

__all__ = ["InputqEHVISWMM", "KPIEvaluation", "OutputqEHVISWMM", "qEHVISWMM"]
