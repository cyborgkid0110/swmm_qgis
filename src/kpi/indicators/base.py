"""Shared base class and standardization helpers for indicator groups."""

from __future__ import annotations

from abc import ABC

import numpy as np


def minmax_standardize(
    values: np.ndarray,
    positive: bool = True,
) -> np.ndarray:
    """Min-max standardize a 1-D array of per-subcatchment values to [0, 1].

    ``positive=True``: ``(x − min) / (max − min)``  — higher input → higher output
    ``positive=False``: ``(max − x) / (max − min)`` — higher input → lower output

    If all values are equal (or only one sample), returns 0.5 everywhere.
    """
    x = np.asarray(values, dtype=float)
    lo, hi = x.min(), x.max()
    rng = hi - lo
    if rng <= 1e-12:
        return np.full_like(x, 0.5)
    if positive:
        return (x - lo) / rng
    return (hi - x) / rng


def reference_standardize(
    values: np.ndarray,
    reference: float,
    positive: bool = True,
    clamp: bool = True,
) -> np.ndarray:
    """Standardize against a fixed reference maximum.

    ``positive=True``: ``x / reference``
    ``positive=False``: ``1 − (x / reference)``

    Clamped to [0, 1] if ``clamp=True``.
    """
    x = np.asarray(values, dtype=float)
    if reference <= 1e-12:
        return np.full_like(x, 0.5)
    ratio = x / reference
    out = ratio if positive else 1.0 - ratio
    if clamp:
        out = np.clip(out, 0.0, 1.0)
    return out


class IndicatorGroup(ABC):
    """Base class for one of the four index groups (FHI, FEI, FVI, FRI).

    Subclasses provide:
      * ``indicator_names`` — list of indicator IDs in a fixed order
      * ``compute(...)`` — returns a (S, M) array: S subcatchments × M indicators

    This base class does not define ``compute`` abstractly because signatures
    vary (hazard needs SWMM stats; exposure needs nothing; etc.). Each
    concrete group documents its own signature.
    """

    group_name: str = ""
    indicator_names: list[str] = []

    @property
    def num_indicators(self) -> int:
        return len(self.indicator_names)
