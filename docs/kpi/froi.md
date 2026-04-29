# `src/kpi/froi.py` -- FROIComputer Orchestrator

Central entry point that the BO-SWMM pipeline calls on every SWMM evaluation.

```python
from src.kpi.froi import FROIComputer, load_expert_matrices

froi = FROIComputer(
    inp_sections,                       # from parse_inp(path)
    exposure_csv="data/exposure/exposure.csv",
    vulnerability_csv="data/vulnerability/vulnerability.csv",
    resilience_csv="data/resilience/resilience_static.csv",
    expert_matrices=load_expert_matrices({
        "fhi": "data/weights/expert_fhi.json",
        "fei": "data/weights/expert_fei.json",
        "fvi": "data/weights/expert_fvi.json",
        "fri": "data/weights/expert_fri.json",
    }),
    rainfall_depth_mm=20.0,
    sim_duration_hours=6.0,
    aggregation_method="simple",        # or "area_weighted"
)

# Per-evaluation call
result = froi.evaluate(node_stats, conduit_stats, sim_duration_hours)
```

---

## Pipeline

`FROIComputer.__init__` performs all the one-off work:

1. Parse the `.inp` for subcatchment order + areas + element properties.
2. Build the junction-to-SC and conduit-to-SC maps (via `src.kpi.aggregator`).
3. Instantiate the four indicator groups (`HazardIndicators`, `ExposureIndicators`, `VulnerabilityIndicators`, `ResilienceIndicators`).
4. Compute weights per group via IFAHP + EWM + preference-coefficient combination (see `weights.md`).

`evaluate(node_stats, conduit_stats, sim_duration_hours)` runs on every SWMM evaluation:

```
HazardIndicators.compute(node_stats, sim_duration_hours)  -> (S, 2) H_norm
ExposureIndicators.compute()                              -> (S, 4) E_norm (cached)
VulnerabilityIndicators.compute()                         -> (S, 3) V_norm (cached)
ResilienceIndicators.compute()                            -> (S, 3) R_norm (cached)

Per-SC indices:
    FHI_s = H_norm @ rho_H
    FEI_s = E_norm @ rho_E
    FVI_s = FHI_s * (V_norm @ rho_V)        <- dynamic scaling
    FRI_s = R_norm @ rho_R

Region aggregation (simple or area-weighted):
    FHI = mean_s FHI_s,  FEI = ...,  FVI = ...,  FRI = ...

FROI = FHI * FEI * FVI * (1 - FRI)
```

All intermediates are surfaced in the return value:

```python
@dataclass
class FROIResult:
    fhi: float; fei: float; fvi: float; fri: float; froi: float
    fhi_per_sc: np.ndarray
    fei_per_sc: np.ndarray
    fvi_per_sc: np.ndarray
    fri_per_sc: np.ndarray

    def as_objective_vector(self, mode: str) -> list[float]:
        ...  # [FROI] or [FHI, FEI, FVI, 1 - FRI]
```

---

## Weight computation at init

Uses the already-computed standardized matrices as EWM inputs:

- FEI: fully available at init (static).
- FVI: fully available at init (static, tanh-normalized).
- FRI: fully available at init (R1-R3 all static).
- FHI: **not available** -- no SWMM run has happened yet. Currently padded with zeros, which forces EWM to assign uniform theta. IFAHP still contributes omega, so the combined rho is IFAHP-dominated.

---

## Expert matrix loader

```python
load_expert_matrices({
    "fhi": "data/weights/expert_fhi.json",
    ...
}) -> dict[str, list[np.ndarray]]
```

Each JSON file has this shape:

```json
{
  "group": "FHI",
  "indicators": ["H1_flood_duration", "H2_flood_volume"],
  "experts": [
    {
      "name": "Expert 1",
      "matrix": [
        [[0.5, 0.5], [0.35, 0.45]],
        [[0.45, 0.35], [0.5, 0.5]]
      ]
    }
  ]
}
```

The `group` and `indicators` keys are informational; only `experts[*].matrix` is consumed. Multiple experts per file are aggregated inside `ifahp_weights`.
