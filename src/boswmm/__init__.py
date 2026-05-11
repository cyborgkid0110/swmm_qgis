"""BO-SWMM — Bayesian optimization for sediment maintenance on SWMM models.

Public API:
  * :class:`Input` — Step 1: scenario loading and .inp modification.
  * :class:`KPIEvaluation` — Step 2: SWMM execution and KPI computation.
  * :class:`BOSWMM` — Step 3: BO loop (GP + acquisition + Pareto update).
    Supports single-objective (EI) and multi-objective (EHVI) modes via
    pluggable :class:`AcquisitionFunction` strategy.
  * :class:`Output` — Step 4: Pareto/best-solution extraction and JSON report.

Scenario-level operations (``.inp`` mutation, state extraction) live in the
sibling package :mod:`src.scenario`. Indicator/weight/FROI computation lives
in :mod:`src.kpi`.
"""

from .boswmm import BOSWMM
from .input import Input
from .kpi_evaluation import KPIEvaluation
from .output import Output

__all__ = ["BOSWMM", "Input", "KPIEvaluation", "Output"]
