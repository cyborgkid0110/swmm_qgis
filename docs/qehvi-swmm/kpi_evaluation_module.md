# KPIEvaluation — Step 2: SWMM Simulation & KPI Computation

**Source:** `src/qehvi_swmm/kpi_evaluation.py`
**Config:** `src/qehvi_swmm/config.yaml` (sections `kpi`, `bo`, `constraints`)

---

## Purpose

`KPIEvaluation` runs EPA SWMM simulations on modified `.inp` files and computes three objective function values [F1, F2, F3]. It also extracts summary metrics (`num_flood`, `volume_flood`) needed for the output report.

This class is reused in both **Step 2** (initial evaluation) and **Step 3.2** (evaluation inside the optimization loop).

---

## Constructor

```python
KPIEvaluation(
    inp_sections: OrderedDict,
    sedimentation: dict[str, float],
    config: dict | None = None,
)
```

| Parameter | Required | Description |
|---|---|---|
| `inp_sections` | Yes | Parsed base `.inp` sections from `InputqEHVISWMM._parse_inp()` |
| `sedimentation` | Yes | Dict mapping conduit name to filled_depth (from sedimentation CSV) |
| `config` | No | Config dict overriding `config.yaml`. Structure: `{f1: {alpha, beta}, f2: {zeta, gamma, delta}, f3: {mu, nu}}` |

### Initialization flow

1. Load KPI weight parameters from `config.yaml` (or override dict)
2. Parse `[CONDUITS]` section → conduit lengths, roughness, connectivity
3. Parse `[XSECTIONS]` section → conduit shapes, diameters
4. Parse `[JUNCTIONS]` / `[OUTFALLS]` → node invert elevations
5. Compute Q_full (Manning full-flow capacity) and pipe volumes for each conduit

---

## Methods

### `evaluate(inp_path) -> dict`

Run SWMM simulation on a single `.inp` file and compute KPIs.

```python
result = evaluator.evaluate("temp_data/scenarios/scenario_0000.inp")
# result = {
#     "kpi": [2.6048, 328.06, 0.8012],
#     "num_flood": 8,
#     "volume_flood": 23794.47,
#     "success": True,
# }
```

| Return Key | Type | Description |
|---|---|---|
| `kpi` | `list[float]` | `[F1, F2, F3]` objective values (lower is better) |
| `num_flood` | `int` | Number of junctions where flooding occurred |
| `volume_flood` | `float` | Total flood volume across all junctions (m3) |
| `success` | `bool` | Always `True` (raises `RuntimeError` on failure) |

**Raises `RuntimeError`** if SWMM simulation fails (non-convergence, file error, etc.).

### `evaluate_batch(inp_paths) -> list[dict]`

Evaluate multiple `.inp` files sequentially.

```python
results = evaluator.evaluate_batch(["scenario_0000.inp", "scenario_0001.inp"])
```

---

## KPI Formulas

### F1 — Flood Severity Index

```math
F_1 = \sum_{i=1}^{N} w_i \left[ \alpha \left( \frac{V_i^{\text{flood}}}{V_{\text{ref}}} \right) + \beta \left( \frac{T_i^{\text{flood}}}{T_{\text{ref}}} \right) \right]
```

| Symbol | Source | Description |
|---|---|---|
| `V_i^flood` | `node.statistics["flooding_volume"]` | Flood volume at junction i (m3) |
| `T_i^flood` | `node.statistics["flooding_duration"]` | Flood duration at junction i (hours) |
| `V_ref` | `(wet_weather_inflow + external_inflow) / num_nodes` | Total system inflow per node |
| `T_ref` | `sim.end_time - sim.start_time` | Simulation duration (hours) |
| `w_i` | `1.0` | Uniform node weight (no land-use data) |
| `α, β` | `config.yaml → f1.alpha, f1.beta` | Volume/duration weights (α + β = 1) |

### F2 — Drainage Capacity Index

```math
F_2 = \sum_{j=1}^{M} L_j \left[ \zeta \left( \frac{\bar{Q}_j}{Q_j^{\mathrm{full}}} \right) + \gamma \left( \frac{T_j^{\mathrm{surch}}}{T_{\mathrm{ref}}} \right) \right]
```

| Symbol | Source | Description |
|---|---|---|
| `L_j` | `[CONDUITS]` section | Conduit length (m) |
| `Q_bar_j` | `link.conduit_statistics["peak_flow"]` | Average link flow (m3/s) |
| `T_surch_j` | `link.conduit_statistics["time_surcharged"]` | Surcharge duration (hours) |
| `Q_full_j` | Manning equation | Full-flow capacity (m3/s) |
| `ζ, γ` | `config.yaml → f2.zeta, f2.gamma` | Component weights |

**Q_full calculation (Manning equation for circular pipe):**
```math
Q_j^{\mathrm{full}} = \frac{1}{n_j} A_j R_j^{2/3} S_j^{1/2}
```
where `A = π(D/2)²`, `R = D/4`, `S = |elev_upstream - elev_downstream| / length`, and `n` = Manning roughness from `[CONDUITS]`.

### F3 — Sedimentation Index

```math
F_3 = \sum_{j} \mu \left( \frac{A_j^{\mathrm{sed}}}{A_j^{\mathrm{pipe}}} \right)
```

where the sedimentation cross-sectional area is computed as a **circular segment**:

```math
A_{\mathrm{sed}} = R^2 \arccos\!\left(\frac{R - h}{R}\right) - (R - h)\sqrt{2Rh - h^2}
```

and the full pipe cross-sectional area is:

```math
A_{\mathrm{pipe}} = \pi R^2
```

| Symbol | Source | Description |
|---|---|---|
| `R` | `[XSECTIONS]` Geom1 / 2 | Pipe radius (m) — from base `.inp` |
| `h` | **Scenario** `[XSECTIONS]` Geom2 | Remaining sediment depth (m) after any partial maintenance |
| `A_sed` | Circular segment formula | Cross-sectional area of remaining sediment |
| `A_pipe` | `π R²` | Full pipe cross-sectional area |
| `μ` | `config.yaml → f3.mu` | Sedimentation weight |

**F3 only counts conduits with `FILLED_CIRCULAR` shape** in the scenario `.inp`. Conduits written back to `CIRCULAR` by the scenario builder (fully cleaned, `x[i] = v_max[i]`) contribute 0.

**Important:** `h` is read from the **scenario `[XSECTIONS]` Geom2**, not from the sedimentation CSV. `KPIEvaluation` delegates this lookup to `src.scenario.ScenarioExtractor.remaining_depth(conduit)` so that scenario-state semantics live in one place. Under partial maintenance (`0 < x[i] < v_max[i]`), the scenario builder writes `h' < filled_depth` back, and F3 reflects that reduced depth.

> **Note:** The `ν` parameter is reserved in `config.yaml` for future maintenance cost terms but is currently unused.

---

## Configuration File

**Path:** `src/qehvi_swmm/config.yaml`. KPI weights live under the `kpi:` section (sibling to `bo:` and `constraints:`).

```yaml
kpi:
  f1:
    alpha: 0.5    # weight for flood volume component
    beta: 0.5     # weight for flood duration component
  f2:
    zeta: 0.5     # weight for average flow / capacity ratio
    gamma: 0.5    # weight for surcharge duration
    delta: 0.0    # reserved for future use
  f3:
    mu: 0.5       # weight for sedimentation extent
    nu: 0.5       # reserved for future maintenance cost term
```

Override at runtime by passing a `config` dict (same three-section shape) to the constructor:

```python
custom_config = {
    "kpi": {"f1": {"alpha": 0.7, "beta": 0.3}, "f2": {...}, "f3": {...}},
    "bo": {...},
    "constraints": {...},
}
evaluator = KPIEvaluation(sections, sedimentation, config=custom_config)
```

---

## Data Sources

### From pyswmm (after simulation)

| Data | pyswmm API | Used in |
|---|---|---|
| Flood volume per node | `node.statistics["flooding_volume"]` | F1, `volume_flood` |
| Flood duration per node | `node.statistics["flooding_duration"]` | F1 |
| Peak flow per conduit | `link.conduit_statistics["peak_flow"]` | F2 |
| Surcharge duration per conduit | `link.conduit_statistics["time_surcharged"]` | F2 |
| Total wet weather inflow | `SystemStats.routing_stats["wet_weather_inflow"]` | F1 (V_ref) |
| Simulation time range | `sim.start_time`, `sim.end_time` | F1, F2 (T_ref) |

### From .inp file (parsed statically)

| Data | .inp Section | Used in |
|---|---|---|
| Conduit length, roughness | `[CONDUITS]` | F2 (L_j, Manning n) |
| Conduit shape, diameter | `[XSECTIONS]` | F2 (Q_full), F3 (C_cap) |
| Node elevations | `[JUNCTIONS]`, `[OUTFALLS]` | F2 (pipe slope for Q_full) |

### From scenario `.inp` (per-evaluation)

| Data | Source | Used in |
|---|---|---|
| Remaining sediment depth per conduit | Scenario `[XSECTIONS]` Geom2 (written by `InputqEHVISWMM`) | F3 (h in `A_seg`) |
| Scenario shape (FILLED_CIRCULAR vs CIRCULAR) | Scenario `[XSECTIONS]` | F3 (zero-contribution gate for fully cleaned conduits) |

### From sedimentation CSV (via InputqEHVISWMM)

| Data | Used in |
|---|---|
| `filled_depth` per conduit | Only to enumerate the monitoring-conduit set for F3 and to define `v_max` in `InputqEHVISWMM`; **not** used as `h` in F3 |

---

## Usage Example

```python
from src.qehvi_swmm.input import InputqEHVISWMM
from src.qehvi_swmm.kpi_evaluation import KPIEvaluation

# Parse base model and setup sedimentation
sections = InputqEHVISWMM._parse_inp("models/Site_Drainage_Model.inp")
sedimentation = {"C1": 0.2, "C3": 0.4, "C5": 0.3}

# Create evaluator (uses default config.yaml weights)
evaluator = KPIEvaluation(
    inp_sections=sections,
    sedimentation=sedimentation,
)

# Evaluate a scenario
result = evaluator.evaluate("output/scenario_0000.inp")
print(f"F1={result['kpi'][0]:.4f}, F2={result['kpi'][1]:.4f}, F3={result['kpi'][2]:.4f}")
print(f"Flooded junctions: {result['num_flood']}, Total flood: {result['volume_flood']:.2f} m3")

# Batch evaluation
results = evaluator.evaluate_batch(["scenario_0.inp", "scenario_1.inp", "scenario_2.inp"])
```

---

## Error Handling

If the SWMM simulation fails for any reason, `evaluate()` raises a `RuntimeError` with details about the failure. The caller (typically `qEHVISWMM` in Step 3) is responsible for deciding how to handle this — e.g., retry, skip, or abort.

---

## Dependencies

- `pyswmm` — `Simulation`, `Nodes`, `Links`, `SystemStats`
- `pyyaml` — config file loading
- `math` — Manning equation
- Reuses `InputqEHVISWMM._parse_inp()` for parsing scenario `.inp` files
