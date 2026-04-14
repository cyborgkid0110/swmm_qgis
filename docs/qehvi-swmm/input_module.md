# InputqEHVISWMM — Step 1: Scenario Loading & .inp Modification

**Source:** `qehvi_swmm/input.py`

---

## Purpose

`InputqEHVISWMM` is the entry point of the qEHVI-SWMM optimization pipeline. It loads a pre-existing EPA SWMM hydraulic model (`.inp` file), configures sedimentation monitoring points, and produces modified `.inp` files for any binary decision vector `x`.

This class handles **Step 1** (Input) and the **Scenario Builder** component used throughout the optimization loop.

---

## Decision Variable

The decision variable `x ∈ {0, 1}^N` is a binary vector where N is the number of sedimentation monitoring points (conduits):

| Value | Meaning | Effect on .inp |
|---|---|---|
| `x[i] = 1` | Conduit i is **maintained** (sediment cleared) | Cross-section stays `CIRCULAR` |
| `x[i] = 0` | Conduit i is **not maintained** | Cross-section becomes `FILLED_CIRCULAR` with `Geom2 = filled_depth` |

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

---

## Methods

### `build_scenario(x, scenario_id=0) -> str`

Build a single modified `.inp` file from a binary decision vector.

```python
path = inp.build_scenario(x=torch.tensor([1, 0, 1, 0, 1], dtype=torch.double), scenario_id=0)
# -> "output_dir/scenario_0000.inp"
```

| Parameter | Type | Description |
|---|---|---|
| `x` | `torch.Tensor` | Binary tensor of shape `(N,)` |
| `scenario_id` | `int` | Used in output filename: `scenario_{id:04d}.inp` |
| **Returns** | `str` | Path to the generated `.inp` file |

### `build_scenarios(X) -> list[str]`

Build modified `.inp` files for a batch of binary vectors.

```python
paths = inp.build_scenarios(X=torch.tensor([[1,0,1,0,1], [0,1,0,1,0]], dtype=torch.double))
# -> ["output_dir/scenario_0000.inp", "output_dir/scenario_0001.inp"]
```

| Parameter | Type | Description |
|---|---|---|
| `X` | `torch.Tensor` | Binary tensor of shape `(n_samples, N)` |
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

The class modifies the `[XSECTIONS]` section of the `.inp` file. For each conduit listed in the sedimentation CSV:

**Original (CIRCULAR):**
```
C1               CIRCULAR     1.5                0          0          0          1
```

**After x[i]=0 (not maintained, filled_depth=0.2):**
```
C1               FILLED_CIRCULAR  1.5              0.2        0          0          1
```

The `FILLED_CIRCULAR` shape in EPA SWMM represents a circular pipe partially filled with sediment:
- `Geom1` = pipe diameter (unchanged)
- `Geom2` = sediment filled depth

Conduits **not** listed in the sedimentation CSV are never modified.

### Two-phase modification design

Scenario modifications are applied in two phases:

1. **One-time** (during `__init__`): Rainfall and discharge modifications are applied to the base sections once, since they are shared across all decision vectors.
2. **Per-sample** (during `build_scenario`): Sedimentation modifications are applied on a deep copy of the base sections for each binary vector `x`.

This avoids redundant rainfall/discharge processing when generating many scenarios.

---

## Usage Example

```python
import torch
from qehvi_swmm import InputqEHVISWMM

# Initialize with base model and sedimentation config
inp = InputqEHVISWMM(
    base_inp_path="models/Site_Drainage_Model.inp",
    sedimentation_csv="data/sedimentation.csv",
    output_dir="output/scenarios",
)

print(f"Monitoring points: {inp.N}")       # e.g. 5
print(f"Conduits: {inp.conduit_names}")    # e.g. ['C1', 'C3', 'C5', 'C7', 'C9']

# Build a single scenario
x = torch.tensor([1, 0, 1, 0, 1], dtype=torch.double)
path = inp.build_scenario(x, scenario_id=0)
# C1: maintained (CIRCULAR), C3: not maintained (FILLED_CIRCULAR),
# C5: maintained, C7: not maintained, C9: maintained

# Build a batch of scenarios
X = torch.tensor([
    [0, 0, 0, 0, 0],  # no maintenance
    [1, 1, 1, 1, 1],  # full maintenance
], dtype=torch.double)
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
