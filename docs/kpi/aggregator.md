# `src/kpi/aggregator.py` — Spatial Mapping & Region Aggregation

This module owns two concerns:

1. **Map SWMM elements to subcatchments.** Point-in-polygon test against `[POLYGONS]` for junctions, with an upstream-BFS fallback on the conduit graph for junctions that fall outside every polygon. Links inherit the subcatchment of their inlet node (`FromNode`).
2. **Aggregate per-subcatchment values to the region.** Simple arithmetic mean or area-weighted mean, with the `UNASSIGNED` bucket excluded.

---

## `.inp` parsers

```python
parse_polygons(sections)          -> dict[str, shapely.Polygon]
parse_coordinates(sections)       -> dict[str, tuple[float, float]]
parse_subcatchment_outlets(secs)  -> dict[str, str]   # {sc_name: outlet_node}
parse_subcatchment_areas(secs)    -> dict[str, float] # from [SUBCATCHMENTS] col 4
```

These complement the lower-level parsers in `src/scenario/utils/parser.py` (`parse_conduits`, `parse_xsections`, `parse_node_elevations`). They read section names canonically uppercased by `parse_inp`, so both `[POLYGONS]` and `[Polygons]` in the source file resolve to the same dict key.

---

## Mapping construction

```python
from src.kpi.aggregator import (
    build_junction_subcatchment_map,
    build_conduit_subcatchment_map,
    invert_map,
    UNASSIGNED,
)

j2sc = build_junction_subcatchment_map(inp_sections)
# {node_name: subcatchment_name}  — UNASSIGNED if unreachable

c2sc = build_conduit_subcatchment_map(j2sc, conduit_props)
# {conduit_name: subcatchment_name}  — uses each conduit's from_node

by_sc = invert_map(j2sc)
# {subcatchment_name: [node_names]}  — useful for iteration
```

### Algorithm

```
1. Parse [POLYGONS] + [COORDINATES].
2. For each node in [COORDINATES]:
       point = Point(x, y)
       for each subcatchment polygon:
           if polygon.covers(point):  # includes boundary
               assign node to that subcatchment
               break
3. For any node still unassigned:
       build upstream adjacency from [CONDUITS] (ToNode -> [FromNodes])
       for each subcatchment outlet:
           BFS upstream from the outlet
           claim any unassigned node reached along the way
4. Any node still unreachable becomes UNASSIGNED.
```

### Edge cases

| Situation | Handling |
|---|---|
| Junction exactly on a polygon boundary | `Polygon.covers` is used (includes boundary) for numerical robustness. |
| Junction inside multiple polygons | First match wins (polygon iteration order). |
| Junction outside all polygons | Upstream-BFS fallback claims reachable nodes. |
| Junction still unreachable after BFS | Assigned to `UNASSIGNED`; a warning is printed. |
| `[POLYGONS]` section absent | Fall back entirely to upstream-BFS (warning). |

---

## Region aggregation

```python
from src.kpi.aggregator import aggregate_to_region

# Simple mean (drops UNASSIGNED)
region = aggregate_to_region(per_sc_values, method="simple")

# Area-weighted mean (uses [SUBCATCHMENTS] Area column)
region = aggregate_to_region(per_sc_values, areas=areas, method="area_weighted")
```

`per_sc_values: dict[str, float]` — one value per subcatchment. `areas` may contain extra entries (missing ones are treated as area 0). If `area_weighted` is requested but areas are empty/zero, it falls back to a simple mean.

---

## Why a dedicated module?

Putting all mapping logic in one place keeps the indicator classes clean: `HazardIndicators` accepts `{junction_name: sc_name}` as input, `ResilienceIndicators` accepts `{conduit_name: sc_name}` — neither class knows about polygons, BFS, or outfalls. The aggregator can be unit-tested with a synthetic `.inp` without any SWMM run.
