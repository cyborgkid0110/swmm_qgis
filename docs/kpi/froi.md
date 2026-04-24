# `src/kpi/froi.py` — FROIComputer Orchestrator

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
    r4_zeta=0.5, r4_gamma=0.5,
    aggregation_method="simple",        # or "area_weighted"
)

# One-off: seed R4 reference from a baseline SWMM run
_, baseline_cond, baseline_hours = KPIEvaluation._run_swmm(base_inp_path)
froi.set_r4_reference_from_baseline(baseline_cond, baseline_hours)

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
ResilienceIndicators.compute(conduit_stats, sim_hours)    -> (S, 4) R_norm

Per-SC indices:
    FHI_s = H_norm @ ρ_H
    FEI_s = E_norm @ ρ_E
    FVI_s = FHI_s * (V_norm @ ρ_V)        ← dynamic scaling
    FRI_s = R_norm @ ρ_R

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
- FVI: fully available at init (static raw values).
- FHI: **not available** — no SWMM run has happened yet. Currently padded with zeros, which forces EWM to assign uniform θ. IFAHP still contributes ω, so the combined ρ is IFAHP-dominated.
- FRI: R1–R3 available; R4 padded with a constant 0.5 placeholder (same reason).

This is a known trade-off — weights are set up-front with limited information about the dynamic columns. If you want R4 to carry more weight in FRI after a real run, you can re-fit:

```python
# After a handful of real evaluations you could call something like:
# theta_fri = ewm_weights(observed_R_matrix)
# rho_fri = combined_weights(ifahp_fri.weights, theta_fri)
# froi._weights["fri"] = rho_fri
```

No public API for re-fitting is exposed yet — it's a future enhancement if the baseline-weight problem proves material.

---

## Baseline R4 reference

`ResilienceIndicators.R4_ref` must be seeded before the first call to `evaluate` that you want to use for optimization. Use either:

```python
froi.set_r4_reference_from_baseline(baseline_conduit_stats, baseline_hours)
```

or run `evaluate` once first — on the first call, the method falls back to the current run's max as an on-the-fly reference. The seeded form is preferred because it keeps R4 comparable across evaluations.

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
