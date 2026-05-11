# Output — Step 4: Solution Extraction, JSON Report, Visualization

**Source:** `src/boswmm/output.py`

---

## Purpose

`Output` owns everything downstream of the BO loop:

1. Filter non-dominated solutions from `train_Y` (multi-mode) or pick the argmin (single-mode).
2. Write a mode-aware JSON report.
3. Render a results figure — pairwise projections + HV convergence (multi) or FROI histogram + convergence (single).

Invoked once at the end of `BOSWMM.run(...)`.

---

## Methods

### `extract_pareto(train_X, train_Y) -> (pareto_X, pareto_Y, indices)`

Non-dominated rank-1 filtering under **minimization**. Uses BoTorch's `is_non_dominated()` on negated `Y`.

### `generate_report(pareto_X, pareto_results, conduit_names, output_path, mode="multi") -> str`

Write the JSON report. `mode` controls labeling and whether `solutions` is a Pareto set (multi) or a single best entry (single).

### `visualize(train_Y, progress_history, report_path, output_dir) -> str`

Dispatches on the `mode` recorded in the JSON report. Private helpers `_visualize_single` and `_visualize_multi` handle the actual plotting.

---

## JSON Report Format

```json
{
    "mode": "multi",
    "objective_labels": ["FHI", "FEI", "FVI", "1-FRI"],
    "conduit_names": ["C1", "C3", "C5", "C7", "C9"],
    "solutions": [
        {
            "x": [20.76, 35.36, 46.50, 0.0, 16.80],
            "total_volume_m3": 119.42,
            "kpi": [0.301, 0.501, 0.149, 0.381],
            "froi": 0.00857,
            "fhi": 0.301,
            "fei": 0.501,
            "fvi": 0.149,
            "fri": 0.619,
            "num_flood": 8,
            "volume_flood": 23803.9
        }
    ]
}
```

| Field | Description |
|---|---|
| `mode` | `"single"` or `"multi"` |
| `objective_labels` | `["FROI"]` (single) or `["FHI", "FEI", "FVI", "1-FRI"]` (multi) |
| `conduit_names` (root) | Ordered monitoring-conduit names; shared index space for every `x` |
| `solutions[].x` | Dense maintenance-volume vector (m³), length N. Exact optimizer values. |
| `solutions[].total_volume_m3` | `sum(x)`; respects `maintenance_budget` within L-BFGS-B tolerance |
| `solutions[].kpi` | Objective vector. Length matches `objective_labels`. |
| `solutions[].froi, fhi, fei, fvi, fri` | Sub-index values — always present regardless of mode |
| `solutions[].num_flood, volume_flood` | Aggregate SWMM outputs for quick inspection |

In `multi` mode, `solutions` contains the full Pareto set — no two entries dominate each other. In `single` mode, `solutions` has exactly one element: the argmin of `train_Y`.

---

## Visualization

### Multi-mode figure (`_visualize_multi`)

- **Top panels:** C(M, 2) = 6 pairwise 2D scatter plots (for the 4 objectives `FHI, FEI, FVI, 1-FRI`). Blue = all evaluated, green = Pareto front.
- **Bottom strip:** Hypervolume convergence curve (red line, one point per BO iteration).

### Single-mode figure (`_visualize_single`)

- **Left panel:** Histogram of evaluated FROI values with the best-FROI line marked in red.
- **Right panel:** Best-so-far convergence curve (red line, one point per BO iteration).

Both are saved to `{output_dir}/optimization_results.png`.

---

## Usage Example

```python
from src.boswmm import BOSWMM, Output

# ... run BO ...
result = optimizer.run(output_path="output/report.json")

# Produce the figure
fig_path = Output.visualize(
    train_Y=result["train_Y"],
    progress_history=result["progress_history"],
    report_path=result["report_path"],
    output_dir="result/optimization",
)
print(f"Figure: {fig_path}")
```

---

## Dependencies

- `torch`
- `botorch.utils.multi_objective.pareto.is_non_dominated`
- `json`, `os`, `itertools`
- `matplotlib` — figure rendering
- `numpy`
