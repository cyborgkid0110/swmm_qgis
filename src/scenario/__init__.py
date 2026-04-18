"""Scenario package — build and inspect SWMM ``.inp`` scenario files.

Public API:
  * ``ScenarioBuilder`` — build modified scenario ``.inp`` files from a
    decision vector.
  * ``ScenarioExtractor`` — read a scenario ``.inp`` and expose its state
    (remaining depths, cleaned/partial/untouched classification).

Low-level ``.inp`` parsing and circular-segment geometry helpers live under
``scenario.utils``.
"""

from .builder import ScenarioBuilder
from .extractor import (
    STATE_CLEANED,
    STATE_PARTIAL,
    STATE_UNTOUCHED,
    ScenarioExtractor,
)

__all__ = [
    "STATE_CLEANED",
    "STATE_PARTIAL",
    "STATE_UNTOUCHED",
    "ScenarioBuilder",
    "ScenarioExtractor",
]
