# KPIEvaluation — Step 2: SWMM Simulation + FROI Packaging

**Source:** `src/boswmm/kpi_evaluation.py`
**Delegates to:** `src/kpi/froi.py::FROIComputer`

---

## Purpose

`KPIEvaluation` is the single entry point for SWMM-based KPI evaluation. It:

1. Parse the base `.inp` and construct a `FROIComputer` internally.
2. Run a baseline SWMM simulation to calibrate `sim_duration_hours`.
3. Run `pyswmm.Simulation` on scenario `.inp` files during evaluation.
4. Collect junction and conduit statistics.
5. Hand them to the internal `FROIComputer`.
6. Package the result as the `kpi` vector BOSWMM minimizes, using the current mode (`single` → `[FROI]`, `multi` → `[FHI, FEI, FVI, 1 − FRI]`).

This class is reused in both **Step 2** (initial evaluation) and **Step 3.2** (evaluation inside the BO loop).

All objective-function math — indicators, weights, FHI_s × FVI scaling, FROI assembly — lives in `src/kpi/` and is exercised via `FROIComputer.evaluate(...)`. See `docs/optimization/obj_func.md` for the mathematical spec and `docs/kpi/` for the package-level docs.

---

## Constructor

```python
KPIEvaluation(
    base_inp_path: str,
    *,
    kpi_config: dict | str | None = None,
    bo_config: dict | str | None = None,
    mode: str | None = None,
)
```

| Parameter | Required | Description |
|---|---|---|
| `base_inp_path` | Yes | Path to the base `.inp` model file. Used to parse sections for `FROIComputer` and to run a baseline SWMM simulation for `sim_duration_hours`. |
| `kpi_config` | No (kw) | KPI configuration. A parsed dict, a path to a YAML file, or `None` to load the KPI package default (`src/kpi/config.yaml`). |
| `bo_config` | No (kw) | BO-SWMM configuration. A parsed dict, a path to a YAML file, or `None` to load the BO-SWMM package default (`src/boswmm/config.yaml`). Used only to resolve `mode` when not provided explicitly. |
| `mode` | No (kw) | `'single'` or `'multi'`. If `None`, read from `bo_config["optimization"]["mode"]`. |

Raises `ValueError` if `mode` is not one of `'single'` / `'multi'`.

---

## Methods

### `evaluate(inp_path) -> dict`

Run SWMM on a single scenario and return a result dict.

```python
result = evaluator.evaluate("output/scenarios/scenario_0000.inp")
```

**Return keys:**

| Key | Type | Description |
|---|---|---|
| `kpi` | `list[float]` | The objective vector. `[FROI]` in single mode; `[FHI, FEI, FVI, 1 − FRI]` in multi mode. Always minimized. |
| `froi` | `float` | Scalar FROI (`FHI · FEI · FVI · (1 − FRI)`) — always populated. |
| `fhi, fei, fvi, fri` | `float` | Individual sub-index values. |
| `num_flood` | `int` | Number of junctions where flooding occurred (`flooding_volume > 0`). |
| `volume_flood` | `float` | Total flood volume summed across all junctions (m³). |
| `success` | `bool` | Always `True`. SWMM failures raise `RuntimeError` instead. |

Raises `FileNotFoundError` if `inp_path` is missing, and `RuntimeError` if the SWMM simulation itself fails.

### `evaluate_batch(inp_paths) -> list[dict]`

Evaluate multiple scenarios sequentially.

### Properties

- `mode` — `'single'` or `'multi'`.
- `n_objectives` — `1` (single) or `4` (multi).
- `froi_computer` — The internal `FROIComputer` instance (for advanced use).

### `_run_swmm(inp_path)` (static)

Runs a SWMM simulation and returns `(node_stats, conduit_stats, duration_hours)`. Exposed as a static helper so callers can use the same extraction logic without instantiating `KPIEvaluation`.

---

## SWMM Statistics Collected

From `pyswmm.Nodes(sim)` (junctions only):
- `flooding_volume` (m³)
- `flooding_duration` (hours)
- `max_depth` (m)
- `surcharge_duration` (hours)
- plus a handful of other fields documented in `PLAN_indicators.md` §0.4

From `pyswmm.Links(sim)` (conduits only):
- `peak_flow` (m³/s)
- `time_surcharged` (fraction)
- plus `peak_velocity`, `time_normal_flow`, etc.

The `SystemStats.routing_stats` bundle is also inspected to ensure the engine completed normally, but its values are not currently propagated to the KPI.

---

## Usage Example

```python
from src.boswmm import KPIEvaluation

# All defaults — loads KPI and BO configs, builds FROIComputer, runs baseline SWMM:
evaluator = KPIEvaluation(base_inp_path="models/Site_Drainage_Model.inp")

# With custom configs:
evaluator = KPIEvaluation(
    base_inp_path="models/Site_Drainage_Model.inp",
    kpi_config="custom/kpi_config.yaml",
    bo_config="custom/bo_config.yaml",
)

# Or override mode explicitly:
evaluator = KPIEvaluation(
    base_inp_path="models/Site_Drainage_Model.inp",
    mode="single",
)

# Evaluate.
r = evaluator.evaluate("output/scenarios/scenario_0000.inp")
print(f"kpi = {r['kpi']}")
print(f"FROI = {r['froi']:.6f}  (FHI={r['fhi']:.3f}, FEI={r['fei']:.3f}, "
      f"FVI={r['fvi']:.3f}, FRI={r['fri']:.3f})")
print(f"{r['num_flood']} flooded junctions, total vol = {r['volume_flood']:.1f} m^3")
```

---

## Error Handling

SWMM simulation errors surface as `RuntimeError` with the offending `inp_path` embedded in the message. `BOSWMM` does not retry failed evaluations — a raised exception aborts the current BO iteration. For long-running studies, wrap scenario evaluation in your own retry logic around `evaluator.evaluate(...)`.

---

## Dependencies

- `pyswmm` — `Simulation`, `Nodes`, `Links`, `SystemStats`
- `src.kpi.froi.FROIComputer` — the actual objective-function calculator
