# TASK2_optimization.md — Optimization Algorithm & SWMM Engine Integration

## Purpose

Develop a multi-objective Bayesian optimization module (qEHVI) that selects optimal sedimentation maintenance points in a drainage network, using EPA SWMM as the simulation engine to evaluate each candidate solution.

Reference files for algorithm details:
- `docs/optimization/obj_func.md` — KPI definitions and objective function formulation
- `docs/optimization/method.md` — qEHVI algorithm methodology
- `docs/optimization/summary.md` — Algorithm summary and key formulas

---

## Operational Flows

### Flow 1 — Flood Warning & Sedimentation Solution Proposal

```
Step 1: Input qEHVI-SWMM
  Scenario input (rainfall, sedimentation, discharge) + base .inp model
        ↓
  Sobol sampling in [0,1]ᴺ → round to {0,1}ᴺ → scenario builder → modified .inp
        ↓
Step 2: KPI Evaluation
  Run SWMM engine (pyswmm, multiprocessing) → parse .rpt/.out
        ↓
  Compute KPI vector: F₁ (flood), F₂ (drainage), F₃ (sediment)
        ↓
Step 3.1: qEHVI Optimization Algorithm
  Normalize (x, y) → fit GP surrogate (ModelListGP)
        ↓
  Construct qEHVI acquisition function → optimize → select q candidates
        ↓
Step 3.2: Evaluate + Update New Solutions
  Discretize [0,1]ᴺ → {0,1}ᴺ → scenario builder → evaluate via SWMM
        ↓
  Update Pareto front (non-dominated filtering)
        ↓
  Converged? → No: loop back to Step 3.1 │ Yes: proceed to Step 4
        ↓
Step 4: Output qEHVI-SWMM
  Extract Pareto-optimal {x*} ∈ {0,1}ᴺ + KPI vectors
        ↓
  Generate JSON report (sed_points, kpi, num_flood, volume_flood)
```

### Flow 2 — Algorithm Effectiveness Evaluation

```
Input A: Original scenario (pre-maintenance)     Input B: Post-sedimentation scenario (resolved)
                        ↓                                         ↓
              Run SWMM Simulation (parallel execution)
                        ↓                                         ↓
            Analyze Results A                         Analyze Results B
                        ↓                                         ↓
            Evaluate Network A                        Evaluate Network B
                        ↓                                         ↓
                Compare Objective Function Index (A vs B)
```

---

## Sub-Task 1 — Algorithm Flowchart

**Goal:** HTML flowchart covering both operational flows. Output: `docs/optimization/flowchart.html`

**Flow 1 structure (5 steps):**

| Step | Description |
|---|---|
| Step 1 — Input | Scenario input + base .inp + Sobol initial sampling → scenario builder |
| Step 2 — KPI Evaluation | SWMM execution → result parsing → compute F₁, F₂, F₃ |
| Step 3.1 — qEHVI Algorithm | Normalize data → fit GP surrogate → qEHVI acquisition → optimize + select batch |
| Step 3.2 — Evaluate + Update | Discretize → scenario builder → evaluate via SWMM → update Pareto front |
| Convergence Loop | Check max iterations / HV stagnation → loop to Step 3.1 or proceed |
| Step 4 — Output | Extract Pareto set → generate JSON report |

**Flow 2:** Parallel dual-scenario comparison (pre vs. post maintenance) with KPI delta evaluation.

---

## Sub-Task 2 — qEHVI-SWMM Module Implementation

**Goal:** Implement the qEHVI-SWMM optimization pipeline as a self-contained Python module. The implementation uses BoTorch for Bayesian optimization and pyswmm for SWMM simulation, organized into 4 classes corresponding to the flowchart steps.

### Decision Variable Definition

The decision variable **x** is a **binary vector** `x ∈ {0, 1}^N`, where N is the number of sediment monitoring points in the drainage network. Each element `x_i` indicates:
- `x_i = 0` — no maintenance at monitoring point i
- `x_i = 1` — perform sediment maintenance at monitoring point i

**Continuous relaxation:** Since BoTorch's qEHVI uses gradient-based optimization (L-BFGS-B), the binary domain is relaxed to continuous `[0, 1]^N` during acquisition function optimization. Continuous candidates are **rounded to binary** (threshold 0.5) before SWMM evaluation.

### Module Architecture

The module has **4 classes** mapped to the flowchart steps:

```
qehvi_swmm/
├── __init__.py            # Package init
├── input.py               # InputqEHVISWMM     — Step 1: scenario loading + .inp modification
├── kpi_evaluation.py      # KPIEvaluation       — Step 2: SWMM execution + KPI computation
├── qehvi_swmm.py          # qEHVISWMM           — Step 3: BO loop (GP + qEHVI + evaluate + Pareto)
└── output.py              # OutputqEHVISWMM     — Step 4: extract Pareto set + JSON report
```

> **Note:** `KPIEvaluation` is modularized separately because it is reused both during initial evaluation (Step 2) and inside the optimization loop (Step 3.2). Initial Sobol sampling belongs to Step 3 (`qEHVISWMM`), not Step 1.

### Class Responsibilities

#### `InputqEHVISWMM` — Step 1: Input Data

| Responsibility | Detail |
|---|---|
| Load base hydraulic model | Parse base `.inp` file into section-based representation |
| Apply scenario modifications | Optionally replace rainfall ([RAINGAGES]+[TIMESERIES]) and discharge ([INFLOWS]) from CSV |
| Configure sedimentation | Load sedimentation CSV (conduit, filled_depth); define N monitoring points |
| Build modified .inp | For any binary vector `x ∈ {0,1}^N`, produce a modified `.inp` with FILLED_CIRCULAR for non-maintained conduits |

#### `KPIEvaluation` — Step 2: KPI Evaluation

| Responsibility | Detail |
|---|---|
| Run SWMM simulation | Execute `.inp` via pyswmm or subprocess, with multiprocessing support |
| Parse simulation results | Extract flood volume, flow rate, sedimentation level from `.rpt`/`.out` |
| Compute KPI vector | Calculate F₁ (flood severity), F₂ (drainage capacity), F₃ (sedimentation–maintenance) |
| Handle simulation failures | Return penalized KPI vector if SWMM fails (non-convergence, file errors) |

#### `qEHVISWMM` — Step 3: Optimization Loop

| Responsibility | Detail |
|---|---|
| **Step 3.1 — qEHVI algorithm** | Normalize observed (x, y) data; fit GP surrogate (`ModelListGP`); construct qEHVI acquisition function; optimize via L-BFGS-B; select q candidate batch |
| **Step 3.2 — Evaluate + Update** | Discretize candidates `[0,1]^N → {0,1}^N`; call `KPIEvaluation` for SWMM evaluation; update Pareto front (non-dominated filtering); add results to observation dataset |
| **Convergence check** | Stop if max iterations reached or no HV improvement over consecutive iterations; otherwise loop to Step 3.1 |

#### `OutputqEHVISWMM` — Step 4: Output Data

| Responsibility | Detail |
|---|---|
| Extract Pareto set | Filter non-dominated rank-1 solutions from final observation data |
| Generate JSON report | Export results in the specified format (see below) |

### Design Requirements

| Item | Specification |
|---|---|
| Decision variables | Binary `x ∈ {0, 1}^N` — N sediment monitoring points; relaxed to `[0, 1]^N` for GP |
| Objective vector | F₁ (flood severity), F₂ (drainage capacity), F₃ (sedimentation–maintenance) |
| Surrogate model | BoTorch `ModelListGP` (one GP per objective) |
| Acquisition function | BoTorch `qExpectedHypervolumeImprovement` (qEHVI) |
| Batch size `q` | Configurable; default `q=4` for parallel SWMM evaluation |
| Stopping criteria | Maximum iterations or HV stagnation over consecutive iterations |
| Discretization | Round continuous candidates to binary at threshold 0.5 before SWMM evaluation |
| Output | Pareto-optimal binary vectors `{x*}` with KPI vectors and SWMM summary metrics |

### Output Specification

The optimization produces a **JSON report** containing all Pareto-optimal solutions:

```json
{
    "solutions": [
        {
            "sed_points": [2, 5, 11, 23],
            "kpi": [0.12, 0.85, 0.34],
            "num_flood": 3,
            "volume_flood": 125.7
        }
    ]
}
```

| Field | Description |
|---|---|
| `sed_points` | List of sedimentation monitoring point indices selected for maintenance (where `x_i = 1`) |
| `kpi` | Array of objective function values `[F₁, F₂, F₃]` for this solution |
| `num_flood` | Number of junctions where flooding occurs (from SWMM summary report) |
| `volume_flood` | Total flood volume at junctions in the network (from SWMM summary report) |

### Key Implementation Notes
- Uses BoTorch's built-in `qExpectedHypervolumeImprovement` — internal algorithm details (MC sampling, box decomposition, inclusion-exclusion) are abstracted by the library.
- `KPIEvaluation` is reused in both Step 2 (initial evaluation) and Step 3.2 (loop evaluation) — must be independently callable.
- SWMM calls wrapped with error handling; failed simulations return penalized KPI vectors.
- Log all evaluations to a results CSV for reproducibility.

---

## Remaining Tasks

- [x] Build HTML algorithm flowchart (Sub-Task 1) → `docs/optimization/flowchart.html`
- [x] Define decision variable (binary x), output JSON format, and flowchart revision
- [x] Implement `InputqEHVISWMM` class (Step 1: scenario loading + .inp modification)
- [x] Implement `KPIEvaluation` class (Step 2: SWMM execution + KPI computation)
- [x] Implement `qEHVISWMM` class (Step 3: BO loop with qEHVI + Pareto update)
- [x] Implement `OutputqEHVISWMM` class (Step 4: Pareto extraction + JSON report)
- [ ] Validate end-to-end loop on `sample_region.inp`
- [ ] Benchmark qEHVI convergence on sample region (hypervolume vs. iterations)
- [ ] Compare pre/post maintenance KPI vectors (Flow 2 validation)
