# qEHVISWMM — Step 3: Bayesian Optimization Loop

**Source:** `qehvi_swmm/qehvi_swmm.py`
**Config:** `qehvi_swmm/config.yaml` → `optimization` section

---

## Purpose

`qEHVISWMM` is the core optimization engine. It runs a multi-objective Bayesian optimization loop using BoTorch's `qLogExpectedHypervolumeImprovement` (qLogEHVI) acquisition function, with SWMM hydraulic simulation as the black-box objective.

The class orchestrates Steps 1-4 of the flowchart: initial sampling → SWMM evaluation → GP surrogate fitting → qEHVI acquisition → discretization → evaluation → Pareto update → convergence check → output.

---

## Constructor

```python
qEHVISWMM(
    input_module: InputqEHVISWMM,
    kpi_evaluator: KPIEvaluation,
    config: dict | None = None,
)
```

| Parameter | Required | Description |
|---|---|---|
| `input_module` | Yes | Initialized `InputqEHVISWMM` instance (Step 1) |
| `kpi_evaluator` | Yes | Initialized `KPIEvaluation` instance (Step 2) |
| `config` | No | Config dict overriding `config.yaml`. Must contain `optimization` key. |

---

## Methods

### `run(output_path) -> dict`

Run the full qEHVI optimization loop and generate the output report.

```python
result = optimizer.run(output_path="output/report.json")
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `output_path` | `str` | `"output/report.json"` | Path for the JSON report file |

**Returns dict:**

| Key | Type | Description |
|---|---|---|
| `train_X` | `Tensor (n, N)` | All evaluated decision vectors |
| `train_Y` | `Tensor (n, 3)` | All KPI vectors `[F1, F2, F3]` |
| `all_results` | `list[dict]` | All `KPIEvaluation.evaluate()` result dicts |
| `pareto_X` | `Tensor (p, N)` | Pareto-optimal decision vectors |
| `pareto_Y` | `Tensor (p, 3)` | Pareto-optimal KPI vectors |
| `pareto_indices` | `list[int]` | Indices into `train_X`/`train_Y` |
| `report_path` | `str` | Path to the generated JSON report |
| `n_iterations` | `int` | Number of BO iterations completed |
| `hv_history` | `list[float]` | Hypervolume at each iteration |

---

## Optimization Loop

The loop follows the exact BoTorch pattern from the reference script `test.py`:

### Step 3.1 — Initial Sampling

```
Sobol sequence in [0,1]^N → round to {0,1}^N → n_init binary vectors
    → InputqEHVISWMM.build_scenario() → KPIEvaluation.evaluate_batch()
    → train_X, train_Y
```

### Step 3.2 — BO Iteration (repeated up to max_iter times)

```
1. Fit GP surrogate
   - Negate Y (minimization → maximization for BoTorch)
   - ModelListGP: one SingleTaskGP per objective with Standardize(m=1)
   - Fit via SumMarginalLogLikelihood

2. Compute reference point
   - ref_point = max(-Y) + ref_point_offset  (worst negated objective + offset)

3. Build acquisition function
   - NondominatedPartitioning on negated Y
   - qLogExpectedHypervolumeImprovement with SobolQMCNormalSampler

4. Optimize acquisition
   - optimize_acqf in [0,1]^N bounds
   - Returns q continuous candidates

5. Discretize + evaluate
   - torch.round(candidate) → binary {0,1}^N
   - build_scenario() → evaluate_batch() → new KPI vectors

6. Update dataset
   - Append new_X, new_Y to training data

7. Check convergence
   - Compute hypervolume of current Pareto front
   - If HV stagnates for `patience` iterations → early stop
```

### Step 3.3 — Output

```
Extract Pareto set → generate JSON report via OutputqEHVISWMM
```

---

## Minimization Handling

All three KPIs (F1, F2, F3) are **minimized** (lower is better). BoTorch's qEHVI **maximizes** by default. The standard solution:

1. **Negate Y** before GP fitting: the GP models `-F1, -F2, -F3`
2. **Reference point** computed on negated Y: `ref = max(-Y) + offset`
3. **Pareto extraction** uses `is_non_dominated(-Y)` to find minimization-Pareto solutions

This is transparent — the returned `train_Y` and `pareto_Y` contain the **original** (non-negated) KPI values.

---

## Configuration

All optimization hyperparameters are in `config.yaml` under the `optimization:` section:

```yaml
optimization:
  n_init: 16          # number of initial Sobol samples
  max_iter: 50        # maximum BO iterations
  batch_size: 3       # q candidates per iteration (parallel SWMM evals)
  num_restarts: 20    # restarts for optimize_acqf
  raw_samples: 512    # raw samples for optimize_acqf
  mc_samples: 256     # MC samples for qEHVI sampler
  patience: 5         # early stop if HV stagnates for this many iterations
  seed: 0             # random seed for Sobol sequence
  ref_point_offset: 0.1  # offset added to worst objective for reference point
```

| Parameter | Description | Tuning guidance |
|---|---|---|
| `n_init` | Initial exploration budget | `2*(N+1)` is a common rule of thumb |
| `max_iter` | Upper bound on BO iterations | Depends on SWMM runtime budget |
| `batch_size` | Candidates per iteration (`q`) | Higher = more parallelism but less sample efficiency |
| `num_restarts` | Multi-start L-BFGS-B restarts | More = better acquisition optimization, slower |
| `raw_samples` | Random starting points for restarts | More = better coverage of acquisition landscape |
| `mc_samples` | MC samples for qEHVI estimator | 128-512 typical; higher = lower variance |
| `patience` | Early stopping patience | Lower = faster convergence detection, risk of premature stop |
| `seed` | Reproducibility seed | Fixed for deterministic Sobol sequence |
| `ref_point_offset` | Reference point margin | Small positive value; too large wastes HV computation |

---

## Convergence Criterion

The loop tracks the **dominated hypervolume** of the current Pareto front at each iteration:

```math
\mathrm{HV}(\mathcal{P}, r) = \lambda_M\left(\bigcup_{y \in \mathcal{P}} [r, y]\right)
```

If HV does not improve for `patience` consecutive iterations, the loop terminates early.

---

## Usage Example

```python
from qehvi_swmm import InputqEHVISWMM, KPIEvaluation, qEHVISWMM

# Step 1: Setup input
inp = InputqEHVISWMM(
    base_inp_path="models/Site_Drainage_Model.inp",
    sedimentation_csv="data/sedimentation.csv",
    output_dir="output/scenarios",
)

# Step 2: Setup evaluator
sections = InputqEHVISWMM._parse_inp("models/Site_Drainage_Model.inp")
sedimentation = dict(zip(inp.conduit_names, [0.2, 0.4, 0.3, 0.15, 0.25]))
evaluator = KPIEvaluation(inp_sections=sections, sedimentation=sedimentation)

# Step 3+4: Run optimization
optimizer = qEHVISWMM(input_module=inp, kpi_evaluator=evaluator)
result = optimizer.run(output_path="output/report.json")

# Access results
print(f"Iterations: {result['n_iterations']}")
print(f"Total evaluations: {result['train_X'].shape[0]}")
print(f"Pareto solutions: {result['pareto_X'].shape[0]}")
print(f"Report: {result['report_path']}")
```

---

## Dependencies

- `torch` — tensors, `SobolEngine`
- `botorch` — `SingleTaskGP`, `ModelListGP`, `qLogExpectedHypervolumeImprovement`, `optimize_acqf`, `NondominatedPartitioning`, `Hypervolume`
- `gpytorch` — `SumMarginalLogLikelihood`
- `pyyaml` — config loading
- Reuses: `InputqEHVISWMM`, `KPIEvaluation`, `OutputqEHVISWMM`
