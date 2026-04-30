# `src/kpi/` — Flood Risk (FROI) Computation Package

This package implements the objective function of the BO-SWMM pipeline. It is the sole owner of:

- **Indicators** — 12 per-subcatchment measurements grouped into 4 indices (FHI, FEI, FVI, FRI).
- **Weights** — IFAHP (subjective) + EWM (objective) + preference-coefficient combination.
- **Aggregator** — point-in-polygon and upstream-BFS mapping from SWMM junctions/conduits to subcatchments.
- **FROIComputer** — orchestrator that auto-loads KPI config and exposes a single `evaluate(node_stats)` entry point to the rest of the pipeline.

## Documentation map

| File | Topic |
|---|---|
| [`indicators.md`](indicators.md) | `HazardIndicators`, `ExposureIndicators`, `VulnerabilityIndicators`, `ResilienceIndicators`, plus the shared `IndicatorGroup` base |
| [`weights.md`](weights.md) | IFAHP, EWM, and combined-weight algorithms |
| [`aggregator.md`](aggregator.md) | Spatial + topological mapping helpers and region aggregation |
| [`froi.md`](froi.md) | `FROIComputer` orchestrator and `FROIResult` dataclass |
| [`config.md`](config.md) | `src/kpi/config.yaml` schema and loader |

## Relationship to the BO-SWMM package

```
src/boswmm/kpi_evaluation.py
        │  (run SWMM, hand stats off)
        ▼
src/kpi/froi.py::FROIComputer
        │  (orchestrate)
        ├── src/kpi/indicators/   (compute H/E/V/R per subcatchment)
        ├── src/kpi/weights/      (compute rho per group — one-off at init)
        └── src/kpi/aggregator.py (map junctions/conduits to SCs; region average)
```

The `src.boswmm` package contains only the BO loop and scenario-construction glue. All objective-function math lives under `src/kpi/` and is consumed via `FROIComputer`.

## Related project-level docs

- [`docs/optimization/obj_func.md`](../optimization/obj_func.md) — high-level FROI framework
- [`PLAN_indicators.md`](../../PLAN_indicators.md) — detailed per-indicator extraction specs
- [`indicators.md`](../../indicators.md) — ground-truth indicator table maintained by the user
- [`weights.md`](../../weights.md) — IFAHP / EWM / combined-weight mathematical derivations
