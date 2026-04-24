# InputqEHVISWMM — Step 1: Scenario Loading & .inp Modification

**Source:** `src/boswmm/input.py`

---

## Purpose

`InputqEHVISWMM` is the entry point of the BO-SWMM optimization pipeline. It loads a pre-existing EPA SWMM hydraulic model (`.inp` file), configures sedimentation monitoring points, and produces modified `.inp` files for any continuous maintenance-volume decision vector `x`.

Internally, `InputqEHVISWMM` is a thin facade over `src.scenario.ScenarioBuilder`, which owns all `.inp` mutation logic. Callers that need richer access to the builder can obtain it via `inp.scenario_builder`.

---

## Decision Variable

The decision variable `x ∈ R^N` is a continuous vector with `x[i] ∈ [0, v_max[i]]`, where `x[i]` is the volume of sediment (m³) removed at monitoring point `i`:

| Value | Meaning | Effect on .inp |
|---|---|---|
| `x[i] = 0` | No maintenance | `FILLED_CIRCULAR` with `Geom2 = filled_depth` (original) |
| `0 < x[i] < v_max[i]` | Partial maintenance | `FILLED_CIRCULAR` with `Geom2 = h'`, where `h'` is inverted from `V_remaining = v_max[i] − x[i]` via bisection on `A_seg(h) · L = V_remaining` |
| `x[i] = v_max[i]` | Fully cleaned | Cross-section reverts to `CIRCULAR` (no sediment) |

The per-conduit upper bound `v_max[i] = A_seg(filled_depth_i, R_i) · L_i` is the current sediment volume (circular-segment area × conduit length). `A_seg(h, R) = R² acos((R−h)/R) − (R−h)√(2Rh−h²)`.

The mapping between vector index `i` and physical conduit name is defined by the order in the sedimentation CSV file, accessible via `inp.conduit_names`.

---

## Constructor

```python
InputqEHVISWMM(
    base_inp_path: str,
    sedimentation_csv: str,
    rainfall_csv: str | None = None,
    discharge_csv: str | None = None,
    output_dir: str | None = None,
)
```

| Parameter | Required | Description |
|---|---|---|
| `base_inp_path` | Yes | Path to the base SWMM `.inp` file |
| `sedimentation_csv` | Yes | CSV with columns `conduit,filled_depth` — defines the N monitoring points |
| `rainfall_csv` | No | CSV to replace `[RAINGAGES]` + `[TIMESERIES]` sections |
| `discharge_csv` | No | CSV to add/replace `[INFLOWS]` section |
| `output_dir` | No | Directory for generated `.inp` files (defaults to a temp directory) |

### Initialization flow

1. Parse base `.inp` into an ordered section dict (preserves all formatting)
2. Load sedimentation CSV → define `conduit_names` and `filled_depths`
3. Validate that all sedimentation conduits exist in `[XSECTIONS]`
4. Apply rainfall modifications if `rainfall_csv` provided (one-time)
5. Apply discharge modifications if `discharge_csv` provided (one-time)

---

## Properties

| Property | Type | Description |
|---|---|---|
| `N` | `int` | Number of sedimentation monitoring points (dimension of `x`) |
| `conduit_names` | `list[str]` | Ordered conduit names — index `i` maps to `x[i]` |
| `output_dir` | `str` | Directory where generated `.inp` files are saved |
| `v_max` | `torch.Tensor` | Per-conduit maximum maintenance volume (m³), shape `(N,)`. Upper bound for `x[i]`. |
| `v_max_sum` | `float` | Sum of `v_max` across all monitoring points (m³) — reference for picking the budget `A` |

---

## Methods

### `build_scenario(x, scenario_id=0) -> str`

Build a single modified `.inp` file from a continuous maintenance-volume vector.

```python
path = inp.build_scenario(x=torch.tensor([0.0, 0.5, 2.3, 0.0, 1.1], dtype=torch.double), scenario_id=0)
# -> "output_dir/scenario_0000.inp"
```

| Parameter | Type | Description |
|---|---|---|
| `x` | `torch.Tensor` | Tensor of shape `(N,)`; each `x[i] ∈ [0, v_max[i]]` (m³) |
| `scenario_id` | `int` | Used in output filename: `scenario_{id:04d}.inp` |
| **Returns** | `str` | Path to the generated `.inp` file |

### `build_scenarios(X) -> list[str]`

Build modified `.inp` files for a batch of maintenance-volume vectors.

```python
paths = inp.build_scenarios(X=torch.tensor([[0.0,0.5,2.3,0.0,1.1], [1.0,0.0,0.0,0.8,0.2]], dtype=torch.double))
# -> ["output_dir/scenario_0000.inp", "output_dir/scenario_0001.inp"]
```

| Parameter | Type | Description |
|---|---|---|
| `X` | `torch.Tensor` | Tensor of shape `(n_samples, N)` |
| **Returns** | `list[str]` | List of paths to generated `.inp` files |

---

## Input File Formats

### Sedimentation CSV (required)

Defines which conduits are sedimentation monitoring points and their filled depth when not maintained. All conduits are assumed to have `CIRCULAR` cross-section in the base model.

```csv
conduit,filled_depth
C1,0.2
C3,0.4
C5,0.3
```

| Column | Type | Description |
|---|---|---|
| `conduit` | string | Conduit name matching `[XSECTIONS]` in the base `.inp` |
| `filled_depth` | float | Sediment depth (m) — used as `Geom2` in `FILLED_CIRCULAR` |

### Rainfall CSV (optional)

Replaces `[RAINGAGES]` and `[TIMESERIES]` sections in the base model.

```csv
Name,Format,Interval,SCF,DataSource,SeriesName,Date,Time,Value
RG1,INTENSITY,0:05,1.0,TIMESERIES,Storm1,,0:00,0.5
RG1,INTENSITY,0:05,1.0,TIMESERIES,Storm1,,0:05,1.2
RG1,INTENSITY,0:05,1.0,TIMESERIES,Storm1,,0:10,3.8
```

| Column | Default | Description |
|---|---|---|
| `Name` | — | Rain gage name |
| `Format` | `INTENSITY` | Recording format (`INTENSITY` or `VOLUME`) |
| `Interval` | `1:00` | Recording interval |
| `SCF` | `1.0` | Snowfall correction factor |
| `DataSource` | `TIMESERIES` | Data source type |
| `SeriesName` | = Name | Name of the linked timeseries |
| `Date` | — | Date for timeseries entry (optional) |
| `Time` | — | Time for timeseries entry |
| `Value` | — | Rainfall value |

### Discharge CSV (optional)

Adds or replaces the `[INFLOWS]` section.

```csv
Node,Constituent,TimeSeries,Type,Mfactor,Sfactor,Baseline,Pattern
J1,FLOW,Inflow1,FLOW,1.0,1.0,0,
```

| Column | Default | Description |
|---|---|---|
| `Node` | — | Junction node name |
| `Constituent` | `FLOW` | Inflow constituent |
| `TimeSeries` | — | Name of inflow timeseries |
| `Type` | `FLOW` | Inflow type |
| `Mfactor` | `1.0` | Multiplier factor |
| `Sfactor` | `1.0` | Scale factor |
| `Baseline` | `0` | Baseline value |
| `Pattern` | — | Pattern name (optional) |

---

## .inp Modification Details

### How sedimentation is applied

The class modifies the `[XSECTIONS]` section of the `.inp` file. For each conduit listed in the sedimentation CSV, one of three branches is taken based on `x[i]` and `V_remaining = v_max[i] − x[i]`:

**Original (CIRCULAR, D=1.5):**
```
C1               CIRCULAR         1.5              0          0          0          1
```

**After x[i]=0 (no maintenance, filled_depth=0.2):**
```
C1               FILLED_CIRCULAR  1.5              0.200000   0          0          1
```

**After 0 < x[i] < v_max[i] (partial maintenance): h' inverted from V_remaining:**
```
C1               FILLED_CIRCULAR  1.5              0.074321   0          0          1
```

**After x[i] = v_max[i] (fully cleaned):**
```
C1               CIRCULAR         1.5              0          0          0          1
```

The `FILLED_CIRCULAR` shape in EPA SWMM represents a circular pipe partially filled with sediment:
- `Geom1` = pipe diameter (unchanged)
- `Geom2` = remaining sediment depth (after any partial maintenance)

The remaining depth `h'` is found via bisection on `A_seg(h) · L = V_remaining` over `h ∈ [0, D]`. `A_seg` is strictly monotonic in `h`, so bisection converges in ~20 iterations with no scipy dependency.

Conduits **not** listed in the sedimentation CSV are never modified.

### Two-phase modification design

Scenario modifications are applied in two phases:

1. **One-time** (during `__init__`): Parse `[CONDUITS]` / `[XSECTIONS]` to compute `v_max`; apply rainfall and discharge modifications to the base sections if provided (shared across all decision vectors).
2. **Per-sample** (during `build_scenario`): Sedimentation modifications are applied on a deep copy of the base sections for each maintenance-volume vector `x`.

This avoids redundant rainfall/discharge processing and geometry parsing when generating many scenarios.

---

## Usage Example

```python
import torch
from src.boswmm import InputqEHVISWMM

# Initialize with base model and sedimentation config
inp = InputqEHVISWMM(
    base_inp_path="models/Site_Drainage_Model.inp",
    sedimentation_csv="data/sedimentation.csv",
    output_dir="output/scenarios",
)

print(f"Monitoring points: {inp.N}")       # e.g. 5
print(f"Conduits: {inp.conduit_names}")    # e.g. ['C1', 'C3', 'C5', 'C7', 'C9']
print(f"v_max (m^3): {inp.v_max.tolist()}")
print(f"Σ v_max: {inp.v_max_sum:.2f} m^3")

# Build a single scenario — partial maintenance at C3 and C9
x = torch.tensor([0.0, 0.0, 2.1, 0.0, 1.5], dtype=torch.double)
path = inp.build_scenario(x, scenario_id=0)

# Build a batch of scenarios
X = torch.stack([
    torch.zeros(inp.N, dtype=torch.double),                  # no maintenance
    inp.v_max,                                                # fully clean all
], dim=0)
paths = inp.build_scenarios(X)

# Validate with pyswmm
from pyswmm import Simulation
with Simulation(paths[0]) as sim:
    for _ in sim:
        pass
```

---

## Dependencies

- `torch` — tensor interface for decision vectors
- `csv`, `copy`, `os`, `re`, `tempfile` — Python standard library

No dependency on QGIS, BoTorch, or the existing conversion module (`src/conversion/`).
