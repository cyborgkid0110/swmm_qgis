# TASK2_optimization.md — Optimization Algorithm & SWMM Engine Integration

## Purpose

Develop a Bayesian optimization module that selects optimal sedimentation maintenance points in a drainage network, using EPA SWMM as the simulation engine to evaluate each candidate solution.

The module supports **two optimization modes**, selected via `src/boswmm/config.yaml::optimization.mode`:

- **`single`** — Minimize the scalar Flood Risk Overall Index (FROI) using `qLogExpectedImprovement` (EI).
- **`multi`**  — Minimize `[FHI, FEI, FVI, 1 − FRI]` on the Pareto front using `qLogExpectedHypervolumeImprovement` (EHVI).

Reference files for algorithm details:
- `docs/optimization/obj_func.md` — FROI definitions and objective-function formulation (replaces the old F1/F2/F3 spec)
- `docs/optimization/method.md` — BO / acquisition methodology
- `docs/optimization/summary.md` — Algorithm summary and key formulas
- `docs/kpi/README.md` — `src/kpi/` package documentation (indicators, weights, FROIComputer)
- `docs/boswmm/boswmm_module.md` — BOSWMM class detail
- `docs/boswmm/acquisition_module.md` — EI/EHVI strategy classes

---

## Operational Flows

### Flow 1 — Flood Warning & Sedimentation Solution Proposal

```
Step 1: Input BO-SWMM
  Scenario input (rainfall, sedimentation, discharge) + base .inp model
        ↓
  Compute v_max per conduit; sampling in [0, v_max]ᴺ with Σ x ≤ A
  (Sobol + rejection) → scenario builder → modified .inp
        ↓
Step 2: KPI Evaluation (delegates to src/kpi/FROIComputer)
  Run SWMM engine (pyswmm) → collect node_stats + conduit_stats
        ↓
  Compute 13 indicators per subcatchment:
    FHI (H1, H2)   — dynamic, from SWMM
    FEI (E1..E4)   — static, from external CSV
    FVI (V1..V3)   — static raw, scaled per-SC by FHI_s (dynamic)
    FRI (R1..R4)   — R1-R3 static, R4 dynamic (per-SC F2 accumulator)
        ↓
  Weighted sum per group using pre-computed IFAHP+EWM+combined ρ
        ↓
  Region aggregation (simple or area-weighted mean)
        ↓
  Package kpi vector per mode:
    single → [FROI]           with FROI = FHI · FEI · FVI · (1 − FRI)
    multi  → [FHI, FEI, FVI, 1 − FRI]
        ↓
Step 3.1: BO Acquisition (via AcquisitionFunction strategy)
  single → SingleTaskGP + qLogExpectedImprovement
  multi  → ModelListGP  + qLogExpectedHypervolumeImprovement
        ↓
  optimize_acqf with inequality_constraints (Σ x ≤ A)
  → select q continuous candidates
        ↓
Step 3.2: Evaluate + Update New Solutions
  clamp to bounds → scenario builder → evaluate via SWMM
        ↓
  Append to training set; update progress metric
    (best-so-far for EI; hypervolume for EHVI)
        ↓
  Converged? → No: loop back to Step 3.1 │ Yes: proceed to Step 4
        ↓
Step 4: Output BO-SWMM
  multi  → extract Pareto set
  single → pick argmin(train_Y)
        ↓
  Generate mode-aware JSON report
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

Three top-level packages under `src/`. The BO pipeline (`src/boswmm/`) delegates scenario `.inp` work to `src/scenario/` and all objective-function computation to `src/kpi/`.

```
src/
├── scenario/                  # scenario .inp construction + extraction (shared)
│   ├── __init__.py
│   ├── builder.py             # ScenarioBuilder    — writes scenario .inp, computes v_max
│   ├── extractor.py           # ScenarioExtractor  — reads scenario state (remaining depths)
│   └── utils/
│       ├── parser.py          # parse_inp / write_inp / parse_conduits / parse_xsections
│       └── geometry.py        # circular_segment_area + invert_circular_segment_volume
│
├── kpi/                       # FROI indicator & weight computation (objective function)
│   ├── __init__.py
│   ├── _config.py             # config loader
│   ├── config.yaml            # FROI configuration (indicator thresholds, data paths)
│   ├── aggregator.py          # point-in-polygon + upstream-BFS mapping; region averaging
│   ├── froi.py                # FROIComputer orchestrator + FROIResult dataclass
│   ├── indicators/
│   │   ├── base.py            # IndicatorGroup ABC + minmax / reference standardization
│   │   ├── hazard.py          # FHI: H1 duration, H2 volume (dynamic)
│   │   ├── exposure.py        # FEI: E1-E4 (static, from CSV)
│   │   ├── vulnerability.py   # FVI: V1-V3 (static raw; made dynamic via FHI_s in FROIComputer)
│   │   └── resilience.py      # FRI: R1-R3 static, R4 dynamic (per-SC F2 accumulator)
│   └── weights/
│       ├── ifahp.py           # 6-step IFAHP (subjective, expert-driven)
│       ├── ewm.py             # 5-step EWM (objective, data-driven)
│       └── combined.py        # preference-coefficient combination
│
└── boswmm/                    # Bayesian-optimization pipeline (Steps 1-4)
    ├── __init__.py            # exports BOSWMM, InputqEHVISWMM, KPIEvaluation, Output
    ├── _config.py             # config loader
    ├── config.yaml            # BO hyperparameters + optimization.mode
    ├── input.py               # InputqEHVISWMM   — Step 1 facade over ScenarioBuilder
    ├── kpi_evaluation.py      # KPIEvaluation    — Step 2: SWMM runner + FROIComputer delegate
    ├── acquisition.py         # AcquisitionFunction ABC + EIAcquisition + EHVIAcquisition
    ├── boswmm.py              # BOSWMM          — Step 3: mode-agnostic BO loop
    └── output.py              # OutputqEHVISWMM — Step 4: mode-aware JSON report + visualization
```

`ScenarioBuilder` and `ScenarioExtractor` are mutually independent — see `docs/boswmm/scenario_module.md`. `FROIComputer` is called by `KPIEvaluation` on every SWMM evaluation — see `docs/kpi/froi.md`.

> **Note:** `KPIEvaluation` is modularized separately because it is reused both during initial evaluation (Step 2) and inside the optimization loop (Step 3.2). Initial Sobol sampling belongs to Step 3 (`BOSWMM`), not Step 1.

### Class Responsibilities

#### `InputqEHVISWMM` — Step 1: Input Data

| Responsibility | Detail |
|---|---|
| Load base hydraulic model | Parse base `.inp` file into section-based representation |
| Apply scenario modifications | Optionally replace rainfall ([RAINGAGES]+[TIMESERIES]) and discharge ([INFLOWS]) from CSV |
| Configure sedimentation | Load sedimentation CSV (conduit, filled_depth); define N monitoring points |
| Build modified .inp | For any continuous vector `x ∈ [0, v_max]^N`, produce a modified `.inp` with FILLED_CIRCULAR for partially-cleaned conduits (or CIRCULAR for fully cleaned) |

#### `KPIEvaluation` — Step 2: SWMM + FROI Packaging

| Responsibility | Detail |
|---|---|
| Run SWMM simulation | Execute `.inp` via `pyswmm` |
| Collect statistics | Gather per-junction node stats and per-conduit link stats |
| Delegate FROI calculation | Pass stats to `FROIComputer.evaluate(...)`; no objective math lives in this class |
| Package kpi vector | Return `[FROI]` (single) or `[FHI, FEI, FVI, 1 − FRI]` (multi) per the configured mode |

#### `FROIComputer` (`src/kpi/froi.py`) — objective function

| Responsibility | Detail |
|---|---|
| Build subcatchment mapping | Spatial point-in-polygon (primary) + upstream BFS (fallback) via `src/kpi/aggregator.py` |
| Instantiate indicator groups | `HazardIndicators`, `ExposureIndicators`, `VulnerabilityIndicators`, `ResilienceIndicators` |
| Compute weights once | IFAHP + EWM + combined per group via `src/kpi/weights/` |
| Evaluate per SWMM run | Produce per-SC FHI/FEI/FVI_raw/FRI, apply FVI_s = FHI_s × FVI_raw_s scaling, aggregate to region, compute FROI |

#### `AcquisitionFunction` (`src/boswmm/acquisition.py`) — strategy

| Responsibility | Detail |
|---|---|
| Fit surrogate | `SingleTaskGP` (single) or `ModelListGP` (multi) with `Normalize` + `Standardize` transforms |
| Build acquisition | `qLogExpectedImprovement` (single) or `qLogExpectedHypervolumeImprovement` (multi) with Sobol QMC sampler |
| Optimize acquisition | `optimize_acqf` with `inequality_constraints = [(arange(N), -1, -A)]` |
| Progress metric | `-min(train_Y)` (single) or Pareto-front hypervolume (multi) |

#### `BOSWMM` — Step 3: Optimization Loop

| Responsibility | Detail |
|---|---|
| Initial sampling | Scaled Sobol draws in `[0, v_max]^N` with rejection on `Σ x ≤ A` |
| BO loop | Delegate propose/fit/acquire to the `AcquisitionFunction` strategy; clamp candidates, evaluate via `KPIEvaluation`; extend training set |
| Convergence check | Stop if the acquisition strategy's progress metric has not improved for `patience` iterations (disabled when `patience: -1`) |
| Cleanup | Delete scenario `.inp`/`.rpt`/`.out` after each iteration |

#### `OutputqEHVISWMM` (aliased `Output`) — Step 4: Output Data

| Responsibility | Detail |
|---|---|
| Extract solutions | Pareto set (multi) or argmin (single) |
| Generate JSON report | Mode-aware schema with `mode`, `objective_labels`, full sub-index breakdown per solution |
| Visualize | Single: FROI histogram + convergence. Multi: C(M, 2) pairwise 2D projections + HV convergence |

### Design Requirements

| Item | Specification |
|---|---|
| Decision variables | Continuous `x ∈ R^N` with `x_i ∈ [0, v_max_i]` — N sediment monitoring points; `v_max_i = A_seg(filled_depth_i, R_i) · L_i` |
| Constraint | `Σ x_i ≤ A` (total maintenance volume budget, m³) — enforced at both init sampling and acquisition optimization |
| Objective vector (single) | `[FROI]`, with `FROI = FHI · FEI · FVI · (1 − FRI)` |
| Objective vector (multi)  | `[FHI, FEI, FVI, 1 − FRI]` |
| Surrogate model (single) | `SingleTaskGP` with `Normalize(d=N, bounds)` + `Standardize(m=1)` |
| Surrogate model (multi)  | `ModelListGP` — one `SingleTaskGP` per objective with the same transforms |
| Acquisition (single) | `qLogExpectedImprovement` |
| Acquisition (multi)  | `qLogExpectedHypervolumeImprovement` |
| Batch size `q` | Configurable via `optimization.batch_size` |
| Stopping criteria | Maximum iterations or progress-metric stagnation over `patience` iterations |
| Discretization | None — candidates flow through as continuous volumes |
| Scenario builder | For each `x`, invert `V_remaining = v_max − x` back to remaining depth `h'` via bisection; emit `FILLED_CIRCULAR` with `Geom2 = h'` (or `CIRCULAR` if fully cleaned) |
| Output | Pareto-optimal continuous vectors (multi) or argmin vector (single) with per-solution FROI + sub-indices |

### Output Specification

The optimization produces a **JSON report** containing all Pareto-optimal solutions:

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
| `conduit_names` (root) | Ordered monitoring-conduit names; shared index space for every `x` vector |
| `x` | Full dense maintenance-volume vector (m³), length N. Exact optimizer values (no thresholding) |
| `total_volume_m3` | `sum(x)` for this solution; respects budget `A` within L-BFGS-B tolerance |
| `kpi` | Objective vector matching `objective_labels` |
| `froi`, `fhi`, `fei`, `fvi`, `fri` | Sub-index values — always populated regardless of mode |
| `num_flood`, `volume_flood` | SWMM summary metrics (flooded junction count + total flood volume, m³) |

### Key Implementation Notes
- Uses BoTorch's `qLogExpectedImprovement` (single) and `qLogExpectedHypervolumeImprovement` (multi) — both numerically stable log-space variants. Internal details (MC sampling, box decomposition) are abstracted by the library.
- Mode selection is driven by `optimization.mode` in `src/boswmm/config.yaml`; the `AcquisitionFunction` factory instantiates the matching strategy class. Adding a new acquisition function = subclass `AcquisitionFunction` and register with the factory.
- `KPIEvaluation` is reused in both Step 2 (initial evaluation) and Step 3.2 (loop evaluation) — must be independently callable.
- `FROIComputer` is constructed once at pipeline start; its weights are cached. Only the dynamic indicators (H1, H2, R4) are recomputed per SWMM run.
- SWMM call failures raise `RuntimeError`; BOSWMM does not auto-retry. Wrap `evaluator.evaluate` externally for long-running studies.

---

## Remaining Tasks

- [x] Build HTML algorithm flowchart (Sub-Task 1) → `docs/optimization/flowchart.html`
- [x] Define decision variable and output JSON format, flowchart revision
- [x] Implement `InputqEHVISWMM` class (Step 1: scenario loading + .inp modification)
- [x] Implement `KPIEvaluation` class (Step 2: SWMM execution + KPI packaging)
- [x] Implement BO loop class (Step 3: was `qEHVISWMM`, now `BOSWMM` with mode support)
- [x] Implement `Output` class (Step 4: Pareto / best-solution extraction + JSON report)
- [x] Migrate decision variable to continuous maintenance-volume with budget constraint `Σ x_i ≤ A`
- [x] Redesign objective function around UNDRR/IPCC FROI framework (`src/kpi/`)
- [x] Support single (EI) and multi (EHVI) optimization modes via `AcquisitionFunction` strategy
- [x] Validate end-to-end loop on `models/Site_Drainage_Model.inp` (both modes)
- [ ] Benchmark convergence on realistic-size models (HV vs. iterations for multi; FROI trace for single)
- [ ] Collect real external data for FEI/FVI/FRI indicators (replace synthetic stubs in `data/`)
- [ ] Compare pre/post maintenance KPI vectors (Flow 2 validation)
