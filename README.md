# SWMM Hydraulic Modeling for Urban Flood Simulation & Sediment Maintenance Optimization

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20Windows-lightgrey.svg)]()
[![SWMM](https://img.shields.io/badge/Engine-EPA%20SWMM-green.svg)](https://www.epa.gov/water-research/storm-water-management-model-swmm)
[![BoTorch](https://img.shields.io/badge/Optimizer-BoTorch%20qEHVI-orange.svg)](https://botorch.org/)

## Table of Contents

1. [Introduction](#introduction)
2. [Features](#features)
3. [Project Architecture](#project-architecture)
4. [Installation](#installation)
5. [Usage](#usage)
6. [Optimization Module](#optimization-module)
7. [Results](#results)
8. [Contributing](#contributing)
9. [License](#license)

---

## Introduction

This project builds an end-to-end pipeline for **urban flood simulation** and **sediment maintenance optimization** in drainage networks, using EPA SWMM as the hydraulic simulation engine. It targets cities with large, complex sewer and canal networks (Ho Chi Minh City, Hanoi) where sedimentation in drainage conduits contributes significantly to flood risk.

The pipeline has two main components:

1. **Data Conversion Module** — Transform digitized drainage network datasets (CSV, XLSX, Shapefile) from city GIS databases into EPA SWMM `.inp` hydraulic model files.
2. **Optimization Module** — Apply a multi-objective Bayesian optimization algorithm (qEHVI) to select the optimal set of sediment maintenance points, minimizing flood severity, drainage capacity loss, and sedimentation burden simultaneously.

---

## Features

- **Multi-source data ingestion** — Standardize and merge rivers, canals, lakes, weirs, sewers, manholes, pumps, orifices, outfalls, raingages, subcatchments, and discharge sources from heterogeneous city databases.
- **Automated SWMM model generation** — Convert standardized geospatial data to fully valid EPA SWMM `.inp` files with DEM-based junction elevation refinement.
- **QGIS-compatible intermediate format** — Output standardized Shapefiles for manual inspection and editing in QGIS before final conversion.
- **Multi-objective optimization** — Use BoTorch's `qLogExpectedHypervolumeImprovement` (qEHVI) to find Pareto-optimal maintenance strategies over three competing objectives (F₁, F₂, F₃).
- **SWMM-in-the-loop evaluation** — Each candidate maintenance plan is evaluated by running a full EPA SWMM hydraulic simulation via `pyswmm`, parsing `.rpt`/`.out` results, and computing KPI vectors.
- **Pareto front visualization** — Generate 3D and 2D pairwise scatter plots of the Pareto front alongside hypervolume convergence charts.
- **JSON report export** — Output Pareto-optimal maintenance solutions with KPI values and selected conduit names.

---

## Project Architecture

```
swmm_qgis/
├── src/
│   ├── standardize/
│   │   ├── migrate_all.py          # Raw CSV/SHP → standardized CSV
│   │   └── standardize.py          # Standardized CSV → Shapefile (12 components)
│   ├── conversion/
│   │   ├── conversion.py           # SWMM conversion (all components → .inp)
│   │   ├── conversion_hanoi.py     # Hanoi region (4,474 nodes + 4,471 links)
│   │   ├── conversion_hcm.py       # HCM region (81,402 nodes + 88,364 links)
│   │   └── conversion_sample.py    # Sample region (fast testing)
│   ├── tools/
│   │   ├── csv_to_shp.py           # CSV → Shapefile for QGIS editing
│   │   └── shp_to_csv.py           # Shapefile → CSV after QGIS editing
│   ├── scenario/                   # Shared scenario .inp layer (Task 2)
│   │   ├── builder.py                  # ScenarioBuilder — writes scenario .inp, computes v_max
│   │   ├── extractor.py                # ScenarioExtractor — reads scenario state
│   │   └── utils/                      # parser.py (syntax) + geometry.py (segment area)
│   ├── qehvi_swmm/                 # Optimization pipeline (Task 2)
│   │   ├── config.yaml                 # Default config: kpi / bo / constraints sections
│   │   ├── input.py                    # Step 1: InputqEHVISWMM facade over ScenarioBuilder
│   │   ├── kpi_evaluation.py           # Step 2: SWMM execution + KPI computation
│   │   ├── qehvi_swmm.py               # Step 3: BO loop (GP + qEHVI + Pareto update)
│   │   └── output.py                   # Step 4: Pareto extraction + JSON report + visualization
│
├── docs/
│   ├── TASK1_conversion.md         # Data conversion module plan
│   ├── TASK2_optimization.md       # Optimization algorithm plan
│   ├── optimization/               # KPI formulations, qEHVI methodology
│   └── qehvi-swmm/                 # Module API documentation
│
├── result/
│   ├── swmm_output/                # Generated .inp files
│   └── optimization/               # Pareto report (report.json) + figures
│
├── test.py                         # End-to-end optimization pipeline test
└── CLAUDE.md                       # Master project summary
```

---

## Installation

This project requires a **conda environment** with QGIS, GDAL, PyTorch, BoTorch, and pyswmm.

```bash
conda create -n qgis-env python=3.12
conda activate qgis-env
conda install -c conda-forge qgis gdal pytorch-gpu torchvision torchaudio botorch pyswmm matplotlib
```

> **Note:** On Linux without a GPU, replace `pytorch-gpu` with `pytorch`.

To activate the environment for subsequent runs:

```bash
conda activate qgis-env
# or for single-command execution:
conda run -n qgis-env python <script.py>
```

---

## Usage

### Task 1 — Data Conversion

**Step 1:** Migrate raw datasets to standardized CSV format:

```bash
conda run -n qgis-env python src/standardize/migrate_all.py
```

**Step 2:** Convert standardized CSV to Shapefile for QGIS inspection:

```bash
conda run -n qgis-env python src/standardize/standardize.py
```

**Step 3:** Generate SWMM `.inp` hydraulic model:

```bash
# Sample region (fast, ~2,530 nodes)
conda run -n qgis-env python src/conversion/conversion_sample.py

# Hanoi region (4,474 nodes + 4,471 links)
conda run -n qgis-env python src/conversion/conversion_hanoi.py

# HCM region (81,402 nodes + 88,364 links)
conda run -n qgis-env python src/conversion/conversion_hcm.py
```

Generated models are saved to `result/swmm_output/`.

### Task 2 — Optimization

Run the end-to-end qEHVI-SWMM optimization pipeline:

```bash
conda run -n qgis-env python test_full.py
```

This will:
1. Build sedimentation scenarios from `temp_data/sed.csv`
2. Run the qEHVI Bayesian optimization loop (SWMM-in-the-loop)
3. Save the Pareto report to `result/optimization/report.json`
4. Generate visualization figures in `result/optimization/`

---

## Optimization Module

### Decision Variable

The optimization operates over a **binary decision vector** `x ∈ {0, 1}^N` where N is the number of sediment monitoring points (conduits). Each element indicates:

- `x[i] = 1` — perform sediment maintenance at conduit i (clear sedimentation)
- `x[i] = 0` — no maintenance (conduit remains partially blocked)

### Objective Functions

The optimizer minimizes three competing KPIs simultaneously:

| Objective | Name | Description |
|---|---|---|
| **F₁** | Flood Severity Index | Weighted sum of flood volume and duration at each junction, normalized by system inflow and simulation duration |
| **F₂** | Drainage Capacity Index | Length-weighted sum of flow ratio and surcharge duration across all conduits |
| **F₃** | Sedimentation–Maintenance Index | Ratio of sediment cross-sectional area to full pipe area, summed over non-maintained conduits |

### Algorithm

The optimization uses BoTorch's **qLogExpectedHypervolumeImprovement** (qEHVI):

```
1. Sobol initial sampling → n_init binary candidates
2. Evaluate via SWMM → [F₁, F₂, F₃] KPI vectors
3. Fit GP surrogate (ModelListGP, one GP per objective)
4. Optimize qEHVI acquisition → q new continuous candidates
5. Discretize to binary (threshold 0.5) → evaluate via SWMM
6. Update Pareto front (non-dominated filtering)
7. Check convergence (HV stagnation over patience iterations)
8. Repeat 3–7 until converged or max_iter reached
9. Extract Pareto set → JSON report + visualizations
```

Key hyperparameters in the `config.yaml` (`bo:` and `constraints:` sections):

```yaml
bo:
  n_init: 16          # initial Sobol samples (post-rejection)
  max_iter: 50        # maximum BO iterations
  batch_size: 3       # candidates per iteration
  patience: 10        # early stop patience (-1 to disable)
constraints:
  maintenance_budget: 128.0   # A: total maintenance volume cap (m^3)
```

### Output

The JSON report (`result/optimization/report.json`) lists all Pareto-optimal solutions:

```json
{
    "solutions": [
        {
            "sed_points": ["C3", "C7", "C8", "C10"],
            "kpi": [2.68, 14.46, 0.36],
            "num_flood": 9,
            "volume_flood": 24524.1
        }
    ]
}
```

| Field | Description |
|---|---|
| `sed_points` | Conduit names selected for maintenance |
| `kpi` | `[F₁, F₂, F₃]` objective values |
| `num_flood` | Number of junctions where flooding occurs |
| `volume_flood` | Total flood volume (m³) |

---

## Exmaples

### Generated SWMM Models

| Model | Nodes | Links | Size |
|---|---|---|---|
| `hanoi_model.inp` | 4,474 | 4,471 | 1.0 MB |
| `hcm_model.inp` | 81,402 | 88,364 | 22.4 MB |
| `hanoi_sewer_sample.inp` | 186,932 | 193,898 | 50 MB |
| `sample_region.inp` | ~2,530 | ~2,432 conduits + 80 weirs | 666 KB |

All models validated with EPA SWMM5 (0 errors, 0.000% continuity error).

### Optimization Visualization

The pipeline produces two figures in `result/optimization/`:

- **`optimization_results.png`** — Three 3D Pareto front views, hypervolume convergence chart, and notable solutions table.
- **`pareto_front.png`** — Three 3D views + three 2D pairwise projections (F₁–F₂, F₁–F₃, F₂–F₃).

