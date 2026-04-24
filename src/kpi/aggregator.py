"""Spatial + topological mapping of SWMM elements to subcatchments.

Each subcatchment is a polygon (from ``[POLYGONS]``); each junction has XY
coordinates (from ``[COORDINATES]``). The primary mapping is a
point-in-polygon test. If a junction falls outside every polygon, we fall
back to an **upstream BFS** over the conduit graph from each subcatchment's
outlet node.

Links (conduits) do not have their own coordinates in SWMM — they inherit
the subcatchment of their inlet node (``from_node``).

Region aggregation helpers at the bottom collapse per-subcatchment values
into a single region value (simple or area-weighted average).
"""

from __future__ import annotations

from collections import OrderedDict, deque

from shapely.geometry import Point, Polygon

from src.scenario.utils.parser import parse_conduits

UNASSIGNED = "unassigned"


# ----------------------------------------------------------------------
# .inp section parsers specific to spatial mapping
# ----------------------------------------------------------------------

def parse_polygons(sections: OrderedDict) -> dict[str, Polygon]:
    """Parse ``[POLYGONS]`` into ``{subcatchment_name: shapely.Polygon}``.

    Consecutive rows with the same subcatchment name form one polygon's
    vertex ring. A polygon with fewer than 3 vertices is dropped (invalid).
    """
    vertices: dict[str, list[tuple[float, float]]] = OrderedDict()
    # parse_inp canonicalizes section names to uppercase.
    for line in sections.get("POLYGONS", []):
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue
        tokens = stripped.split()
        if len(tokens) < 3:
            continue
        name = tokens[0]
        try:
            x, y = float(tokens[1]), float(tokens[2])
        except ValueError:
            continue
        vertices.setdefault(name, []).append((x, y))

    polygons: dict[str, Polygon] = {}
    for name, verts in vertices.items():
        if len(verts) < 3:
            continue
        polygons[name] = Polygon(verts)
    return polygons


def parse_coordinates(sections: OrderedDict) -> dict[str, tuple[float, float]]:
    """Parse ``[COORDINATES]`` into ``{node_name: (x, y)}``."""
    coords: dict[str, tuple[float, float]] = {}
    for line in sections.get("COORDINATES", []):
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue
        tokens = stripped.split()
        if len(tokens) < 3:
            continue
        try:
            coords[tokens[0]] = (float(tokens[1]), float(tokens[2]))
        except ValueError:
            continue
    return coords


def parse_subcatchment_outlets(sections: OrderedDict) -> dict[str, str]:
    """Parse ``[SUBCATCHMENTS]`` into ``{subcatchment_name: outlet_node}``."""
    outlets: dict[str, str] = {}
    for line in sections.get("SUBCATCHMENTS", []):
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue
        tokens = stripped.split()
        if len(tokens) < 3:
            continue
        outlets[tokens[0]] = tokens[2]
    return outlets


def parse_subcatchment_areas(sections: OrderedDict) -> dict[str, float]:
    """Parse ``[SUBCATCHMENTS]`` area column (column 4, hectares or acres)."""
    areas: dict[str, float] = {}
    for line in sections.get("SUBCATCHMENTS", []):
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue
        tokens = stripped.split()
        if len(tokens) < 4:
            continue
        try:
            areas[tokens[0]] = float(tokens[3])
        except ValueError:
            continue
    return areas


# ----------------------------------------------------------------------
# Mapping construction
# ----------------------------------------------------------------------

def _build_upstream_adjacency(conduit_props: dict) -> dict[str, list[str]]:
    """``{to_node: [from_node, ...]}`` — reverse of the directed conduit graph."""
    adj: dict[str, list[str]] = {}
    for props in conduit_props.values():
        adj.setdefault(props["to_node"], []).append(props["from_node"])
    return adj


def _upstream_bfs(start: str, adj: dict[str, list[str]]) -> list[str]:
    """Return every node reachable by walking upstream from ``start``."""
    visited: set[str] = set()
    queue: deque[str] = deque([start])
    while queue:
        node = queue.popleft()
        if node in visited:
            continue
        visited.add(node)
        for up in adj.get(node, []):
            if up not in visited:
                queue.append(up)
    return list(visited)


def build_junction_subcatchment_map(
    inp_sections: OrderedDict,
    *,
    warn: bool = True,
) -> dict[str, str]:
    """Return ``{node_name: subcatchment_name}`` using spatial-first mapping.

    Algorithm:
      1. Point-in-polygon test for every node in ``[COORDINATES]`` against
         every polygon in ``[POLYGONS]``. First match wins.
      2. For any node that fell outside all polygons, run upstream BFS from
         each subcatchment outlet and claim reachable nodes.
      3. Nodes still unreached are marked ``UNASSIGNED``.
    """
    polygons = parse_polygons(inp_sections)
    coords = parse_coordinates(inp_sections)
    conduit_props = parse_conduits(inp_sections)
    outlets = parse_subcatchment_outlets(inp_sections)

    junction_map: dict[str, str] = {}

    # Step 1: point-in-polygon
    if polygons:
        for node, (x, y) in coords.items():
            point = Point(x, y)
            for sc_name, poly in polygons.items():
                # covers() = contains() ∪ boundary, more robust near edges
                if poly.covers(point):
                    junction_map[node] = sc_name
                    break
    elif warn:
        print(
            "[aggregator] Warning: [POLYGONS] section missing — "
            "falling back to upstream-BFS for all nodes."
        )

    # Step 2: upstream-BFS fallback for unassigned nodes
    unassigned = [n for n in coords if n not in junction_map]
    if unassigned and outlets:
        upstream_adj = _build_upstream_adjacency(conduit_props)
        for sc_name, outlet in outlets.items():
            for node in _upstream_bfs(outlet, upstream_adj):
                if node in unassigned and node not in junction_map:
                    junction_map[node] = sc_name

    # Step 3: mark anything still unreached
    still_unassigned = [n for n in coords if n not in junction_map]
    for node in still_unassigned:
        junction_map[node] = UNASSIGNED

    if warn and still_unassigned:
        print(
            f"[aggregator] Warning: {len(still_unassigned)} node(s) could "
            f"not be assigned to any subcatchment (out-of-polygon and not "
            f"reachable from any outlet)."
        )

    return junction_map


def build_conduit_subcatchment_map(
    junction_map: dict[str, str],
    conduit_props: dict,
) -> dict[str, str]:
    """Link inherits the subcatchment of its inlet node (``from_node``)."""
    return {
        cname: junction_map.get(props["from_node"], UNASSIGNED)
        for cname, props in conduit_props.items()
    }


def invert_map(
    element_map: dict[str, str],
) -> dict[str, list[str]]:
    """Turn ``{element: subcatchment}`` into ``{subcatchment: [elements]}``."""
    out: dict[str, list[str]] = {}
    for element, sc in element_map.items():
        out.setdefault(sc, []).append(element)
    return out


# ----------------------------------------------------------------------
# Region aggregation
# ----------------------------------------------------------------------

def aggregate_to_region(
    per_sc: dict[str, float],
    areas: dict[str, float] | None = None,
    method: str = "simple",
) -> float:
    """Collapse ``{sc_name: value}`` into a single region scalar.

    Args:
        per_sc: Per-subcatchment values. ``UNASSIGNED`` key (if present) is
            excluded.
        areas: Per-subcatchment areas (hectares or acres — unit just has to
            match across SCs). Required for ``method='area_weighted'``.
        method: ``'simple'`` (arithmetic mean) or ``'area_weighted'``.

    Returns:
        Float in whatever units the inputs used.
    """
    values = {k: v for k, v in per_sc.items() if k != UNASSIGNED}
    if not values:
        return 0.0

    if method == "simple":
        return sum(values.values()) / len(values)

    if method == "area_weighted":
        if areas is None:
            raise ValueError("area_weighted aggregation requires 'areas'")
        total_area = 0.0
        total_weighted = 0.0
        for sc, v in values.items():
            a = areas.get(sc, 0.0)
            total_area += a
            total_weighted += a * v
        if total_area <= 0:
            # Fall back to simple mean if areas missing
            return sum(values.values()) / len(values)
        return total_weighted / total_area

    raise ValueError(f"Unknown aggregation method: {method!r}")
