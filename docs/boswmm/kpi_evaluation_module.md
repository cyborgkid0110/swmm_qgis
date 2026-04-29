# KPIEvaluation — Step 2: SWMM Simulation + FROI Packaging

**Source:** `src/boswmm/kpi_evaluation.py`
**Delegates to:** `src/kpi/froi.py::FROIComputer`

---

## Purpose

`KPIEvaluation` is a thin wrapper around the SWMM engine. Its responsibilities are narrow:

1. Run `pyswmm.Simulation` on a scenario `.inp`.
2. Collect junction and conduit statistics.
3. Hand them to a pre-constructed `FROIComputer`.
4. Package the result as the `kpi` vector BOSWMM minimizes, using the current mode (`single` → `[FROI]`, `multi` → `[FHI, FEI, FVI, 1 − FRI]`).

This class is reused in both **Step 2** (initial evaluation) and **Step 3.2** (evaluation inside the BO loop).

All objective-function math — indicators, weights, FHI_s × FVI scaling, FROI assembly — lives in `src/kpi/` and is exercised via `FROIComputer.evaluate(...)`. See `docs/optimization/obj_func.md` for the mathematical spec and `docs/kpi/` for the package-level docs.

---

## Constructor

```python
KPIEvaluation(
    inp_sections: OrderedDict,
    sedimentation: dict[str, float],
    *,
    froi_computer: FROIComputer,
    mode: str = "multi",
)
```

| Parameter | Required | Description |
|---|---|---|
| `inp_sections` | Yes | Parsed `.inp` sections. Retained for API compatibility; the actual parsing is now done inside `FROIComputer`. |
| `sedimentation` | Yes | `{conduit_name: filled_depth}`. Unused for KPI computation — it feeds scenario construction elsewhere. Kept in the signature for compatibility with legacy callers. |
| `froi_computer` | Yes (kw) | Pre-constructed `FROIComputer`. Normally built once at pipeline start and reused. |
| `mode` | No (kw) | `'single'` or `'multi'`. Controls the shape of `kpi` (length 1 vs length 4). Default `'multi'`. |

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
from collections import OrderedDict
from src.boswmm import KPIEvaluation
from src.kpi._config import load_default_config as load_kpi_cfg
from src.kpi.froi import FROIComputer, load_expert_matrices
from src.scenario.utils.parser import parse_inp

kpi_cfg = load_kpi_cfg()
sections = parse_inp("models/Site_Drainage_Model.inp")

# Build the FROI computer once.
froi = FROIComputer(
    sections,
    exposure_csv=kpi_cfg["data_paths"]["exposure"],
    vulnerability_csv=kpi_cfg["data_paths"]["vulnerability"],
    resilience_csv=kpi_cfg["data_paths"]["resilience"],
    expert_matrices=load_expert_matrices(kpi_cfg["weights"]["expert_matrices"]),
    rainfall_depth_mm=kpi_cfg["indicators"]["fhi"]["rainfall_depth_mm"],
    sim_duration_hours=6.0,
    aggregation_method=kpi_cfg["aggregation"]["method"],
)

# Create the evaluator (in multi-objective mode).
evaluator = KPIEvaluation(
    inp_sections=sections,
    sedimentation={"C1": 0.2, "C3": 0.4, "C5": 0.3, "C7": 0.15, "C9": 0.25},
    froi_computer=froi,
    mode="multi",
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
