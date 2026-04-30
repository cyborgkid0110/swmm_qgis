# `src/kpi/froi.py` -- FROIComputer Orchestrator

Central entry point that the BO-SWMM pipeline calls on every SWMM evaluation.

## Constructor

```python
FROIComputer(inp_sections, *, kpi_config=None)
```

| Parameter | Required | Description |
|---|---|---|
| `inp_sections` | Yes | Parsed `.inp` sections (`parse_inp(path)` output). |
| `kpi_config` | No (kw) | KPI configuration. A parsed dict, a path to a YAML file, or `None` to load the package default (`src/kpi/config.yaml`). |

All indicator data paths, expert matrix paths, rainfall depth, and aggregation
method are extracted internally from the resolved config.

```python
from src.kpi.froi import FROIComputer
from src.scenario.utils.parser import parse_inp

# Default config (loads src/kpi/config.yaml automatically):
froi = FROIComputer(parse_inp("models/Site_Drainage_Model.inp"))

# Custom config path:
froi = FROIComputer(parse_inp("models/Site_Drainage_Model.inp"),
                    kpi_config="custom/kpi_config.yaml")

# Per-evaluation call
result = froi.evaluate(node_stats)
```

---

## Pipeline

`FROIComputer.__init__` performs all the one-off work:

1. Resolve the KPI config (default or user-provided).
2. Parse the `.inp` for subcatchment order + areas + element properties.
3. Build the junction-to-SC and conduit-to-SC maps (via `src.kpi.aggregator`).
4. Instantiate the four indicator groups (`HazardIndicators`, `ExposureIndicators`, `VulnerabilityIndicators`, `ResilienceIndicators`).
5. Load expert matrices and compute weights per group via IFAHP + EWM + preference-coefficient combination (see `weights.md`).

`evaluate(node_stats)` runs on every SWMM evaluation:

```
HazardIndicators.compute(node_stats)                      -> (S, 2) H_norm
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
