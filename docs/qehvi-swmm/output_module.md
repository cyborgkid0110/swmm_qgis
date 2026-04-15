# OutputqEHVISWMM — Step 4: Pareto Extraction & JSON Report

**Source:** `qehvi_swmm/output.py`

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
    "solutions": [
        {
            "sed_points": ["C1", "C5", "C9"],
            "kpi": [2.58, 1680.5, 0.0],
            "num_flood": 8,
            "volume_flood": 23661.06
        },
        {
            "sed_points": ["C1", "C3"],
            "kpi": [2.59, 1600.2, 0.13],
            "num_flood": 8,
            "volume_flood": 23700.15
        }
    ]
}
```

| Field | Type | Description |
|---|---|---|
| `sed_points` | `list[str]` | Conduit names where `x[i] = 1` (selected for maintenance) |
| `kpi` | `list[float]` | Objective values `[F1, F2, F3]` for this solution |
| `num_flood` | `int` | Number of junctions where flooding occurred |
| `volume_flood` | `float` | Total flood volume across all junctions (m3) |

Each entry in `solutions` is a **Pareto-optimal** maintenance strategy — no other solution is better in all three objectives simultaneously. The decision-maker can select among these based on preference or budget constraints.

---

## Usage Example

```python
from qehvi_swmm.output import OutputqEHVISWMM
import torch

# After optimization, given train_X and train_Y
train_X = torch.tensor([[1,0,1,0,1], [0,0,0,0,0], [1,1,1,1,1]], dtype=torch.double)
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
