# BOSWMM — Step 3: Bayesian Optimization Loop

**Source:** `src/boswmm/boswmm.py`
**Config:** `src/boswmm/config.yaml` → `optimization:` and `constraints:` sections
**Sibling:** `src/boswmm/acquisition.py` holds the EI/EHVI strategies

---

## Purpose

`BOSWMM` is the core optimization engine. It runs a Bayesian-optimization loop with SWMM hydraulic simulation as the black-box objective, in either:

- **single-objective mode** — minimize the scalar FROI using `qLogExpectedImprovement`, or
- **multi-objective mode** — minimize `[FHI, FEI, FVI, 1 − FRI]` using `qLogExpectedHypervolumeImprovement`.

The mode is selected via `optimization.mode` in `config.yaml`. Everything that differs between the two modes (GP topology, acquisition function, progress metric) is encapsulated in the `AcquisitionFunction` strategy class (see `acquisition_module.md`).

The class name `qEHVISWMM` is kept as a back-compat alias for legacy imports.

---

## Constructor

```python
BOSWMM(
    input_module: InputqEHVISWMM,
    kpi_evaluator: KPIEvaluation,
    config: dict | None = None,
)
```

| Parameter | Required | Description |
|---|---|---|
| `input_module` | Yes | Initialized `InputqEHVISWMM` (Step 1). Provides decision-variable bounds via `v_max`. |
| `kpi_evaluator` | Yes | Initialized `KPIEvaluation` (Step 2). Its `.mode` must match `config.optimization.mode` — otherwise the constructor raises. |
| `config` | No | Config dict overriding `config.yaml`. Must contain `optimization` and `constraints`. |

---

## Methods

### `run(output_path) -> dict`

Run the full BO loop and emit a JSON report.

```python
result = optimizer.run(output_path="output/report.json")
```

**Returns dict** (keys common to both modes unless noted):

| Key | Type | Description |
|---|---|---|
| `mode` | `str` | `'single'` or `'multi'` |
| `train_X` | `Tensor (n, N)` | All evaluated decision vectors |
| `train_Y` | `Tensor (n, K)` | All KPI vectors; `K=1` single, `K=4` multi |
| `all_results` | `list[dict]` | Every `KPIEvaluation.evaluate()` result |
| `pareto_X` | `Tensor (p, N)` | Pareto set (multi) or best solution (single, `p=1`) |
| `pareto_Y` | `Tensor (p, K)` | KPI vectors matching `pareto_X` |
| `pareto_indices` | `list[int]` | Indices into `train_X`/`train_Y` |
| `report_path` | `str` | Path to the generated JSON report |
| `n_iterations` | `int` | BO iterations completed |
| `progress_history` | `list[float]` | Best-so-far (single) or HV (multi) per iteration |
| `hv_history` | `list[float]` | Alias of `progress_history` (legacy key) |

---

## Optimization Loop

### Step 3.1 — Initial Sampling (both modes)

Scaled Sobol draws in `[0, v_max]^N` are rejected if `Σ x > A`, repeating until `n_init` vectors are accepted (cap: 1000 × `n_init` attempts). If acceptance fails, the method raises with the actual `A`, `Σ v_max`, and attempt count.

Each accepted sample is realized as a scenario `.inp` via `InputqEHVISWMM.build_scenario`, then scored via `KPIEvaluation.evaluate_batch`. The result populates `train_X`, `train_Y`.

### Step 3.2 — BO Iteration (up to `max_iter` times)

The loop body delegates to the injected `AcquisitionFunction`:

```
1. acq.propose_candidate(train_X, train_Y)
   - fit_surrogate(train_X, train_Y)
       single: SingleTaskGP with Normalize+Standardize transforms
       multi : ModelListGP — one SingleTaskGP per objective
   - build_acqf(model, train_Y)
       single: qLogExpectedImprovement with best_f = max(-train_Y)
       multi : qLogExpectedHypervolumeImprovement with NondominatedPartitioning
               + SobolQMCNormalSampler
   - optimize_acqf with inequality_constraints = [(arange(N), -1, -A)]
       → returns q continuous candidates that satisfy Σ x ≤ A

2. clamp to bounds (defensive against L-BFGS-B overshoot) → new_X
3. KPIEvaluation.evaluate_batch(scenarios) → new_Y, new_results
4. Append to dataset
5. progress = acq.progress_metric(train_Y)
       single: best-so-far in negated space (i.e. −min(train_Y))
       multi : Pareto-front hypervolume
6. Early stop if progress has not improved for `patience` iterations
```

### Step 3.3 — Output

- **multi** mode: `Output.extract_pareto(train_X, train_Y)` filters non-dominated rows; the Pareto set is written to JSON.
- **single** mode: `argmin(train_Y)` picks the single best solution; the report contains one entry.

Scenario `.inp` / `.rpt` / `.out` files are deleted after each iteration to keep disk use bounded.

---

## Minimization Handling

KPIs are minimized (lower = better flood outcome). BoTorch maximizes internally, so each `AcquisitionFunction` strategy negates `train_Y` before fitting the GP and computing the acquisition. The returned `train_Y`, `pareto_Y`, and JSON report all store the **original** (non-negated) KPI values.

---

## Configuration

```yaml
optimization:
  mode: "multi"               # "single" (FROI, EI) or "multi" ([FHI, FEI, FVI, 1-FRI], EHVI)
  n_init: 16
  max_iter: 50
  batch_size: 3
  num_restarts: 20
  raw_samples: 512
  mc_samples: 256
  patience: 5
  seed: 0
  ref_point_offset: -0.1      # EHVI only; unused in single mode

constraints:
  maintenance_budget: 128.0   # A (m^3)

kpi:
  config_path: "src/kpi/config.yaml"
```

| Parameter | Section | Description |
|---|---|---|
| `mode` | `optimization` | `"single"` (EI) or `"multi"` (EHVI). BOSWMM raises if it disagrees with `kpi_evaluator.mode`. |
| `n_init` | `optimization` | Initial Sobol samples after budget rejection. `2(N+1)` is a common rule. |
| `max_iter` | `optimization` | Maximum BO iterations. |
| `batch_size` | `optimization` | `q` — candidates per iteration. |
| `num_restarts` | `optimization` | Multi-start L-BFGS-B restarts for `optimize_acqf`. |
| `raw_samples` | `optimization` | Random starting points used to pick the `num_restarts` best. |
| `mc_samples` | `optimization` | MC samples for the Sobol QMC sampler. |
| `patience` | `optimization` | Early-stop threshold on the progress metric; `-1` disables. |
| `seed` | `optimization` | Sobol reproducibility seed. |
| `ref_point_offset` | `optimization` | EHVI reference-point margin (negated-space offset). |
| `maintenance_budget` | `constraints` | Sum-constraint budget `A` (m³). Compare with `Σ v_max` logged at init. |

---

## Convergence Criteria

| Mode | Metric tracked | Stop rule |
|---|---|---|
| `single` | `-min(train_Y)` (best-so-far in negated space) | No improvement for `patience` iterations |
| `multi` | Pareto-front hypervolume (negated space, with `ref_point_offset`) | No improvement for `patience` iterations |

Set `patience: -1` to disable early stopping and always run `max_iter`.

---

## Usage Example

```python
from src.boswmm import BOSWMM, InputqEHVISWMM, KPIEvaluation

BASE_INP = "models/Site_Drainage_Model.inp"

# Step 1: scenario input
inp = InputqEHVISWMM(
    base_inp_path=BASE_INP,
    sedimentation_csv="data/sedimentation.csv",
    output_dir="output/scenarios",
)

# Step 2: KPI evaluator (loads configs + builds FROIComputer internally)
evaluator = KPIEvaluation(base_inp_path=BASE_INP)

# Step 3: BO
optimizer = BOSWMM(input_module=inp, kpi_evaluator=evaluator)
result = optimizer.run(output_path="output/report.json")

print(f"Mode={result['mode']}, iterations={result['n_iterations']}, "
      f"solutions={result['pareto_X'].shape[0]}")
```

---

## Dependencies

- `torch` — tensors, `SobolEngine`
- `botorch` — `SingleTaskGP`, `ModelListGP`, acquisitions, `optimize_acqf`, `NondominatedPartitioning`, `Hypervolume`, `is_non_dominated`
- `gpytorch` — `ExactMarginalLogLikelihood`, `SumMarginalLogLikelihood`
- `pyyaml` — config loading
- Reuses: `InputqEHVISWMM`, `KPIEvaluation`, `Output` (aliased from `OutputqEHVISWMM`), `AcquisitionFunction`
