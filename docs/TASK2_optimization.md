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
  Compute v_max per conduit; sampling in [0, v_max]ᴺ with Σ x ≤ A
  (Sobol + rejection) → scenario builder → modified .inp
        ↓
Step 2: KPI Evaluation
  Run SWMM engine (pyswmm, multiprocessing) → parse .rpt/.out
        ↓
  Compute KPI vector: F₁ (flood), F₂ (drainage), F₃ (sediment — from
  SCENARIO remaining depth, not CSV)
        ↓
Step 3.1: qEHVI Optimization Algorithm
  GP surrogate ModelListGP with Normalize(bounds) + Standardize
        ↓
  Construct qEHVI acquisition function → optimize with
  inequality_constraints (Σ x ≤ A) → select q continuous candidates
        ↓
Step 3.2: Evaluate + Update New Solutions
  (No discretization) continuous x → clamp to bounds →
  scenario builder → evaluate via SWMM
        ↓
  Update Pareto front (non-dominated filtering)
        ↓
  Converged? → No: loop back to Step 3.1 │ Yes: proceed to Step 4
        ↓
Step 4: Output qEHVI-SWMM
  Extract Pareto-optimal {x*} ∈ [0, v_max]ᴺ + KPI vectors
        ↓
  Generate JSON report (conduit_names, x, total_volume_m3, kpi,
  num_flood, volume_flood)
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
| Step 1 — Input | Scenario input + base .inp → compute v_max → Sobol + rejection (Σ x ≤ A) → scenario builder |
| Step 2 — KPI Evaluation | SWMM execution → result parsing → compute F₁, F₂, F₃ (F₃ uses scenario remaining depth) |
| Step 3.1 — qEHVI Algorithm | Fit GP (Normalize + Standardize) → qEHVI acquisition with inequality constraint → optimize + select batch |
| Step 3.2 — Evaluate + Update | Clamp continuous candidates → scenario builder → evaluate via SWMM → update Pareto front |
| Convergence Loop | Check max iterations / HV stagnation → loop to Step 3.1 or proceed |
| Step 4 — Output | Extract Pareto set → generate JSON report |

**Flow 2:** Parallel dual-scenario comparison (pre vs. post maintenance) with KPI delta evaluation.

---

## Sub-Task 2 — qEHVI-SWMM Module Implementation

**Goal:** Implement the qEHVI-SWMM optimization pipeline as a self-contained Python module. The implementation uses BoTorch for Bayesian optimization and pyswmm for SWMM simulation, organized into 4 classes corresponding to the flowchart steps.

### Decision Variable Definition

The decision variable **x** is a **continuous maintenance-volume vector** `x ∈ R^N` with `x_i ∈ [0, v_max_i]`. N is the number of sediment monitoring points. `x_i` is the volume (m³) of sediment to remove at monitoring point `i`:
- `x_i = 0` — no maintenance at monitoring point `i`
- `0 < x_i < v_max_i` — partial maintenance (remove `x_i` m³, leaving `v_max_i − x_i` m³ in place)
- `x_i = v_max_i` — fully clean monitoring point `i`

**Per-conduit upper bound.** `v_max_i = A_seg(filled_depth_i, R_i) · L_i` is the current sediment volume at conduit `i`, computed from the circular-segment area formula (same geometry used in the F3 KPI) multiplied by conduit length.

**Budget constraint.** `Σ x_i ≤ A`, where `A` is configured under `constraints.maintenance_budget` in the `config.yaml`. The constraint is enforced inside `optimize_acqf` via BoTorch's `inequality_constraints` parameter `[(arange(N), -ones(N), -A)]` (which encodes `Σ(-1)·x ≥ -A`). Initial samples are drawn by Sobol-in-bounds with rejection on the same constraint.

### Module Architecture

The module has **4 pipeline classes** (`src/qehvi_swmm/`) that delegate all scenario `.inp` work to a sibling package (`src/scenario/`) with two more classes:

```
src/
├── scenario/                  # scenario .inp construction + extraction (shared)
│   ├── __init__.py
│   ├── builder.py             # ScenarioBuilder    — writes scenario .inp, computes v_max
│   ├── extractor.py           # ScenarioExtractor  — reads scenario state (remaining depths)
│   └── utils/
│       ├── parser.py          # parse_inp / write_inp / parse_conduits / parse_xsections
│       └── geometry.py        # circular_segment_area + invert_circular_segment_volume
└── qehvi_swmm/                # Bayesian-optimization pipeline (Steps 1–4)
    ├── __init__.py
    ├── _config.yaml           # Default config of qEHVI-SWMM
    ├── _config.py             # config loader
    ├── input.py               # InputqEHVISWMM    — Step 1 facade over ScenarioBuilder
    ├── kpi_evaluation.py      # KPIEvaluation     — Step 2: SWMM execution + KPI computation
    ├── qehvi_swmm.py          # qEHVISWMM         — Step 3: BO loop (GP + qEHVI + Pareto)
    └── output.py              # OutputqEHVISWMM   — Step 4: Pareto extraction + JSON report
```

`ScenarioBuilder` and `ScenarioExtractor` are mutually independent — see `docs/qehvi-swmm/scenario_module.md` for details.

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
| **Step 3.1 — qEHVI algorithm** | Fit GP surrogate (`ModelListGP` with per-model `Normalize(d=N, bounds)` + `Standardize`); construct qEHVI acquisition function; optimize via L-BFGS-B with `inequality_constraints=[(arange(N), -ones(N), -A)]`; select q candidate batch |
| **Step 3.2 — Evaluate + Update** | Clamp continuous candidates to bounds; call `KPIEvaluation` for SWMM evaluation (no discretization); update Pareto front (non-dominated filtering); add results to observation dataset |
| **Convergence check** | Stop if max iterations reached or no HV improvement over consecutive iterations; otherwise loop to Step 3.1 |

#### `OutputqEHVISWMM` — Step 4: Output Data

| Responsibility | Detail |
|---|---|
| Extract Pareto set | Filter non-dominated rank-1 solutions from final observation data |
| Generate JSON report | Export results in the specified format (see below) |

### Design Requirements

| Item | Specification |
|---|---|
| Decision variables | Continuous `x ∈ R^N` with `x_i ∈ [0, v_max_i]` — N sediment monitoring points; `v_max_i = A_seg(filled_depth_i, R_i) · L_i` |
| Constraint | `Σ x_i ≤ A` (total maintenance volume budget, m³) — enforced at both init sampling and acquisition optimization |
| Objective vector | F₁ (flood severity), F₂ (drainage capacity), F₃ (sedimentation–maintenance, evaluated on scenario remaining depth) |
| Surrogate model | BoTorch `ModelListGP` (one GP per objective), `Normalize(d=N, bounds)` + `Standardize(m=1)` |
| Acquisition function | BoTorch `qLogExpectedHypervolumeImprovement` (numerically stable qEHVI) |
| Batch size `q` | Configurable via `optimization.batch_size` |
| Stopping criteria | Maximum iterations or HV stagnation over `patience` iterations |
| Discretization | None — candidates flow through as continuous volumes |
| Scenario builder | For each `x`, invert `V_remaining = v_max − x` back to remaining depth `h'` via bisection; emit `FILLED_CIRCULAR` with `Geom2 = h'` (or `CIRCULAR` if fully cleaned) |
| Output | Pareto-optimal continuous vectors `{x*}` with KPI vectors and SWMM summary metrics |

### Output Specification

The optimization produces a **JSON report** containing all Pareto-optimal solutions:

```json
{
    "conduit_names": ["C1", "C2", "C3", "C4", "C5"],
    "solutions": [
        {
            "x": [0.0, 0.0, 2.13, 0.0, 1.40],
            "total_volume_m3": 3.53,
            "kpi": [0.12, 0.85, 0.34],
            "num_flood": 3,
            "volume_flood": 125.7
        }
    ]
}
```

| Field | Description |
|---|---|
| `conduit_names` (root) | Ordered monitoring-conduit names; shared index space for every `x` vector |
| `x` | Full dense maintenance-volume vector (m³), length N. `x[j]` is volume removed at `conduit_names[j]`. Exact optimizer values (no thresholding) |
| `total_volume_m3` | `sum(x)` for this solution; respects budget `A` within L-BFGS-B tolerance |
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
- [x] Migrate decision variable to continuous maintenance-volume with budget constraint `Σ x_i ≤ A`
- [ ] Validate end-to-end loop on `sample_region.inp`
- [ ] Benchmark qEHVI convergence on sample region (hypervolume vs. iterations)
- [ ] Compare pre/post maintenance KPI vectors (Flow 2 validation)
