# OutputqEHVISWMM — Step 4: Pareto Extraction & JSON Report

**Source:** `src/qehvi_swmm/output.py`

---

## Purpose

`OutputqEHVISWMM` extracts the Pareto-optimal solutions from the optimization results and generates the final JSON report. It provides static utility methods used by `qEHVISWMM` at the end of the optimization loop.

---

## Methods

### `extract_pareto(train_X, train_Y) -> (pareto_X, pareto_Y, indices)`

Find non-dominated rank-1 solutions under **minimization**.

Uses BoTorch's `is_non_dominated()` on negated Y (since the function assumes maximization).

```python
pareto_X, pareto_Y, indices = OutputqEHVISWMM.extract_pareto(train_X, train_Y)
```

| Parameter | Type | Description |
|---|---|---|
| `train_X` | `Tensor (n, N)` | All evaluated decision vectors |
| `train_Y` | `Tensor (n, 3)` | All KPI vectors `[F1, F2, F3]` (original, non-negated) |

| Return | Type | Description |
|---|---|---|
| `pareto_X` | `Tensor (p, N)` | Pareto-optimal decision vectors |
| `pareto_Y` | `Tensor (p, 3)` | Pareto-optimal KPI vectors |
| `indices` | `list[int]` | Indices into the original `train_X`/`train_Y` |

**Pareto dominance (minimization):** Solution `y` dominates `y'` if `y[k] <= y'[k]` for all objectives and `y[k] < y'[k]` for at least one.

### `generate_report(pareto_X, pareto_results, conduit_names, output_path) -> str`

Write the JSON report file containing all Pareto-optimal solutions.

```python
path = OutputqEHVISWMM.generate_report(
    pareto_X=pareto_X,
    pareto_results=pareto_results,
    conduit_names=["C1", "C3", "C5", "C7", "C9"],
    output_path="output/report.json",
)
```

| Parameter | Type | Description |
|---|---|---|
| `pareto_X` | `Tensor (p, N)` | Pareto decision vectors |
| `pareto_results` | `list[dict]` | `KPIEvaluation.evaluate()` result dicts for Pareto solutions |
| `conduit_names` | `list[str]` | Ordered conduit names from `InputqEHVISWMM` |
| `output_path` | `str` | Path to write the JSON file |

**Returns:** Path to the generated JSON file.

---

## JSON Report Format

```json
{
    "conduit_names": ["C1", "C2", "C3", "C4", "C5"],
    "solutions": [
        {
            "x": [0.0, 0.0, 2.13, 0.0, 1.40],
            "total_volume_m3": 3.53,
            "kpi": [2.58, 1680.5, 0.08],
            "num_flood": 8,
            "volume_flood": 23661.06
        },
        {
            "x": [1.05, 0.0, 0.0, 0.82, 0.20],
            "total_volume_m3": 2.07,
            "kpi": [2.59, 1600.2, 0.13],
            "num_flood": 8,
            "volume_flood": 23700.15
        }
    ]
}
```

| Field | Type | Description |
|---|---|---|
| `conduit_names` | `list[str]` (root-level) | Ordered monitoring-conduit names. Same index space as every `x` vector — stored once at the root, not per solution. |
| `x` | `list[float]` | Full dense maintenance-volume vector (m³), length `N`. `x[j]` is the volume removed at `conduit_names[j]`. Exact optimizer values — zeros are not filtered. |
| `total_volume_m3` | `float` | `sum(x)`; respects the `maintenance_budget` constraint within L-BFGS-B tolerance |
| `kpi` | `list[float]` | Objective values `[F1, F2, F3]` for this solution |
| `num_flood` | `int` | Number of junctions where flooding occurred |
| `volume_flood` | `float` | Total flood volume across all junctions (m³) |

Each entry in `solutions` is a **Pareto-optimal** maintenance strategy — no other solution is better in all three objectives simultaneously. The decision-maker can select among these based on preference or budget constraints.

---

### `visualize(train_Y, hv_history, report_path, output_dir) -> str`

Generate a 4-panel optimization result figure:

| Panel | Content |
|---|---|
| Top-left | 3D scatter — all evaluated (blue) + Pareto front (green), view 1 |
| Top-right | 3D scatter — same data, rotated view 2 |
| Bottom-left | Hypervolume convergence line chart (red) |
| Bottom-right | Table of 3 notable Pareto solutions (best F1, F2, F3). The "Solution" cell formats the dense `x` vector as `"name=volume"` pairs for positive entries only. |

```python
fig_path = OutputqEHVISWMM.visualize(
    train_Y=result["train_Y"],
    hv_history=result["hv_history"],
    report_path="temp_data/report.json",
    output_dir="result/optimization",
)
```

| Parameter | Type | Description |
|---|---|---|
| `train_Y` | `Tensor (n, 3)` | All evaluated KPI vectors |
| `hv_history` | `list[float]` | Hypervolume at each BO iteration |
| `report_path` | `str` | Path to the Pareto report JSON file |
| `output_dir` | `str` | Directory to save the figure (default: `result/optimization`) |

**Returns:** Path to the saved PNG file (`{output_dir}/optimization_results.png`).

### `visualize_pareto(train_Y, report_path, output_dir) -> str`

Generate a 5-panel Pareto front focused figure:

| Panel | Content |
|---|---|
| Top-left | 3D scatter — all evaluated (blue) + Pareto front (green), view 1 |
| Top-right | 3D scatter — same data, rotated view 2 |
| Bottom-left | 2D projection: F1 vs F2 |
| Bottom-center | 2D projection: F1 vs F3 |
| Bottom-right | 2D projection: F2 vs F3 |

```python
fig_path = OutputqEHVISWMM.visualize_pareto(
    train_Y=result["train_Y"],
    report_path="temp_data/report.json",
    output_dir="result/optimization",
)
```

| Parameter | Type | Description |
|---|---|---|
| `train_Y` | `Tensor (n, 3)` | All evaluated KPI vectors |
| `report_path` | `str` | Path to the Pareto report JSON file |
| `output_dir` | `str` | Directory to save the figure (default: `result/optimization`) |

**Returns:** Path to the saved PNG file (`{output_dir}/pareto_front.png`).

---

## Usage Example

```python
from src.qehvi_swmm.output import OutputqEHVISWMM
import torch

# After optimization, given train_X (continuous volumes, m^3) and train_Y (KPIs)
train_X = torch.tensor([[0.0, 0.0, 2.13, 0.0, 1.40],
                        [0.0, 0.0, 0.0, 0.0, 0.0],
                        [1.05, 0.0, 0.0, 0.82, 0.20]], dtype=torch.double)
train_Y = torch.tensor([[2.58, 1680, 0.13], [2.60, 1566, 0.80], [2.58, 1694, 0.0]], dtype=torch.double)

# Extract Pareto front
pareto_X, pareto_Y, indices = OutputqEHVISWMM.extract_pareto(train_X, train_Y)
print(f"Pareto solutions: {pareto_X.shape[0]}")
print(f"Indices: {indices}")

# Generate report
all_results = [
    {"kpi": [2.58, 1680, 0.13], "num_flood": 8, "volume_flood": 23671.0},
    {"kpi": [2.60, 1566, 0.80], "num_flood": 8, "volume_flood": 23794.0},
    {"kpi": [2.58, 1694, 0.0],  "num_flood": 8, "volume_flood": 23661.0},
]
pareto_results = [all_results[i] for i in indices]

path = OutputqEHVISWMM.generate_report(
    pareto_X=pareto_X,
    pareto_results=pareto_results,
    conduit_names=["C1", "C3", "C5", "C7", "C9"],
    output_path="output/report.json",
)
```

---

## Dependencies

- `torch` — tensor operations
- `botorch.utils.multi_objective.pareto.is_non_dominated` — Pareto filtering
- `json` — report serialization
- `matplotlib` — visualization (3D scatter, line chart, table)
- `numpy` — array operations for visualization
