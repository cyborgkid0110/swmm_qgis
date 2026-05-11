# Scenario Package — Shared `.inp` Construction & Extraction

**Source:** `src/scenario/`

---

## Purpose

The `src.scenario` package is the single home for every operation that reads or writes SWMM `.inp` scenario files. The BO-SWMM pipeline classes (`Input`, `KPIEvaluation`) delegate to this package so that scenario semantics are not duplicated across Step 1 and Step 2.

Two public classes, intentionally independent of each other:

| Class | Responsibility |
|---|---|
| `ScenarioBuilder` | Build modified scenario `.inp` files from a continuous maintenance-volume vector. Applies sedimentation, rainfall, and discharge edits. Computes `v_max` (per-conduit sediment volume upper bound). |
| `ScenarioExtractor` | Read a scenario `.inp` and expose its state: parsed sections, xsections, per-conduit remaining sediment depth, and cleaned/partial/untouched classification. |

`ScenarioBuilder` never reads scenario outputs; `ScenarioExtractor` never writes `.inp` files. Low-level parsing and circular-segment geometry helpers live under `src.scenario.utils`.

---

## Layout

```
src/scenario/
├── __init__.py            # re-exports ScenarioBuilder, ScenarioExtractor, state constants
├── builder.py             # ScenarioBuilder (v_max, apply sedimentation/rainfall/discharge)
├── extractor.py           # ScenarioExtractor (remaining depth, cleaned/partial/untouched)
└── utils/
    ├── __init__.py
    ├── parser.py          # parse_inp / write_inp / parse_conduits / parse_xsections / parse_node_elevations
    └── geometry.py        # circular_segment_area + invert_circular_segment_volume (bisection)
```

The geometry module is the **single source of truth** for the circular-segment formula — both `v_max` computation (in the builder) and F3 KPI evaluation (in `KPIEvaluation`) read from it.

---

## `ScenarioBuilder`

```python
from src.scenario import ScenarioBuilder

builder = ScenarioBuilder(
    base_inp_path="models/Site_Drainage_Model.inp",
    sedimentation_csv="temp_data/sed.csv",
    rainfall_csv=None,       # optional
    discharge_csv=None,      # optional
    output_dir="temp_data/scenarios",
)

builder.N              # number of monitoring points
builder.conduit_names  # ordered monitoring-conduit names
builder.v_max          # Tensor[N], m^3
builder.v_max_sum      # float, m^3
builder.filled_depths  # {conduit: original filled depth (m)}
builder.base_sections  # OrderedDict — parsed base .inp

# Write one scenario for maintenance vector x (values in m^3, x[i] ∈ [0, v_max[i]])
path = builder.build_scenario(x, scenario_id=0)

# Batch variant
paths = builder.build_scenarios(X)   # X shape (n_samples, N)
```

For each monitored conduit, `_apply_sedimentation` takes one of three branches based on `x_i` and `V_remaining = v_max_i − x_i`:

| Branch | Condition | Written XSECTIONS |
|---|---|---|
| No maintenance | `x_i ≤ 0` | `FILLED_CIRCULAR`, `Geom2 = filled_depth_i` |
| Fully cleaned | `V_remaining ≤ 0` | `CIRCULAR`, `Geom2 = 0` |
| Partial | otherwise | `FILLED_CIRCULAR`, `Geom2 = h'` inverted from `V_remaining` via bisection |

---

## `ScenarioExtractor`

```python
from src.scenario import (
    ScenarioExtractor,
    STATE_CLEANED,
    STATE_PARTIAL,
    STATE_UNTOUCHED,
)

ex = ScenarioExtractor("temp_data/scenarios/scenario_0000.inp")

ex.sections                          # full parsed OrderedDict
ex.xsections                         # {conduit: {shape, geom1, geom2, ...}}
ex.remaining_depth("C3")             # float (m) — 0.0 if cleaned
ex.remaining_depths(["C1", "C3"])    # dict form

# Classify every monitored conduit
states = ex.states(builder.filled_depths)
# -> {"C1": STATE_UNTOUCHED, "C3": STATE_PARTIAL, "C5": STATE_CLEANED, ...}
```

State constants use string sentinels so they serialize cleanly into logs and reports.

---

## Geometry helpers

```python
from src.scenario.utils import (
    circular_segment_area,
    invert_circular_segment_volume,
)

# Area of the circular segment of depth h in a pipe of radius r
a = circular_segment_area(h=0.3, r=0.75)

# Invert: for a conduit with (r, length, diameter), find h such that
# circular_segment_area(h, r) * length == v_remaining
h = invert_circular_segment_volume(v_remaining=2.1, r=0.75, length=30.0, diameter=1.5)
```

Both implementations clamp numerically near the pipe crown (h ≈ 2R) to avoid NaN. The inverse uses bisection on a strictly monotonic function, converging in ~20 iterations with no scipy dependency.

---

## Design constraint

`ScenarioBuilder` and `ScenarioExtractor` **must remain independent** of each other — no cross-imports. If a new feature requires shared state, route it through `src.scenario.utils` instead. This keeps Step 1 (build) and Step 2 (evaluate) decoupled and prevents accidental recursion through `KPIEvaluation`.
