"""Circular-segment area and its volume-to-depth inverse.

Shared by both scenario construction (depth -> volume for v_max) and KPI
evaluation (depth -> area for F3). Centralizing avoids drift between the two.
"""

import math


def circular_segment_area(h: float, r: float) -> float:
    """Cross-section area of sediment at depth ``h`` in a circular pipe of radius ``r``.

    Formula (standard circular segment):
        A(h, R) = R^2 * acos((R - h) / R) - (R - h) * sqrt(2 R h - h^2)

    Returns 0 for non-positive inputs. Arguments are clamped numerically so
    that values near the pipe crown (h ≈ 2R) do not produce NaN.
    """
    if h <= 0.0 or r <= 0.0:
        return 0.0
    arg = (r - h) / r
    if arg > 1.0:
        arg = 1.0
    elif arg < -1.0:
        arg = -1.0
    term = 2.0 * r * h - h * h
    if term < 0.0:
        term = 0.0
    return r * r * math.acos(arg) - (r - h) * math.sqrt(term)


def invert_circular_segment_volume(
    v_remaining: float,
    r: float,
    length: float,
    diameter: float,
    tol: float = 1e-6,
    max_iter: int = 80,
) -> float:
    """Return depth ``h ∈ [0, diameter]`` such that ``A(h, r) * length = v_remaining``.

    ``A`` is strictly monotonic in ``h`` on ``[0, diameter]``, so bisection
    converges in ~log2(diameter/tol) iterations with no scipy dependency.
    """
    if length <= 0.0 or r <= 0.0 or diameter <= 0.0:
        return 0.0
    v_max = circular_segment_area(diameter, r) * length
    if v_remaining >= v_max:
        return diameter
    if v_remaining <= 0.0:
        return 0.0

    lo, hi = 0.0, diameter
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        v_mid = circular_segment_area(mid, r) * length
        if abs(v_mid - v_remaining) < tol:
            return mid
        if v_mid < v_remaining:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    return 0.5 * (lo + hi)
