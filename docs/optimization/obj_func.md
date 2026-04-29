# Objective Function — Flood Risk Overall Index (FROI)

**Source:** `src/kpi/` (indicators, weights, aggregator, FROI orchestrator).
**Config:** `src/kpi/config.yaml` (indicator thresholds, data paths, expert matrices).

---

## 1. Framework

The objective function follows the **UNDRR/IPCC flood-risk assessment** convention. Four sub-indices are combined multiplicatively:

$$FROI = FHI \times FEI \times FVI \times (1 - FRI)$$

| Sub-index | Group | Meaning |
|---|---|---|
| **FHI** | Hazard | Direct physical impact of flooding |
| **FEI** | Exposure | People, property, infrastructure in the flood zone |
| **FVI** | Vulnerability | Susceptibility of exposed elements to damage |
| **FRI** | Resilience | Capacity to cope, adapt, recover |

Each sub-index is a weighted sum of indicators, standardized to [0, 1]:

$$FI = \sum_{m=1}^{M} \rho_m \cdot x_m$$

where `ρ_m` are computed at pipeline start via **IFAHP + EWM + preference-coefficient combination** (see §3).

---

## 2. Indicator Set (13 total)

Indicators are computed **per subcatchment** and aggregated to the region via either arithmetic or area-weighted mean.

### 2.1 FHI — Flood Hazard Index (2 indicators, both dynamic)

| ID | Indicator | Source | Per-SC Aggregation | Standardization |
|---|---|---|---|---|
| H1 | Flood duration | `pyswmm` `node.statistics["flooding_duration"]` | Mean across junctions in SC | `x / T_ref`, clamped to [0,1] |
| H2 | Flood volume  | `pyswmm` `node.statistics["flooding_volume"]` | **Sum** across junctions in SC | `min(1, x / V_ref_sc)` |

`T_ref` = simulation duration in hours. `V_ref_sc` = `rainfall_depth_mm × area_sc × 10` (m³).

**Dropped from the original spec:**
- *Flood depth*: redundant with flood volume.
- *Flow velocity (2D)*: requires a 2D surface model unavailable in SWMM 5.

### 2.2 FEI — Flood Exposure Index (4 indicators, all static)

| ID | Indicator | Source | Standardization |
|---|---|---|---|
| E1 | Population density | Vietnam Administrative Units (tinhthanhvn.com) | min-max across SCs |
| E2 | Land-use score | JAXA 2023SEA_v25.09 raster → per-SC zonal mean | pre-scored in [0, 1] via class-to-score table |
| E3 | Road network density | OpenStreetMap | min-max |
| E4 | Facilities level | OSM POI weighted by facility importance | min-max |

### 2.3 FVI — Flood Vulnerability Index (3 indicators, raw values are static but per-SC FVI is **dynamic**)

| ID | Indicator | Source | Direction |
|---|---|---|---|
| V1 | Elderly & children rate | danso.org/viet-nam | Positive (higher rate → higher vulnerability) |
| V2 | GDP / GRDP | tinhthanhvn.com + thuvienphapluat.vn | Positive; `tanh(grdp_trillion_vnd / 500)` |
| V3 | Average income | GSO / provincial statistics | Negative; `1 - tanh(income_million_vnd / 100)` |

**Key design decision — dynamic FVI via FHI scaling:** Vulnerability represents damage *when flooding occurs*. An area with vulnerable demographics but no flood contribution has effective vulnerability zero. Therefore the raw FVI per subcatchment is scaled by the subcatchment-level FHI:

$$FVI_s = FHI_s \cdot \sum_{m=1}^{3} \rho_m^{(V)} \cdot V_{m,s}$$

This makes FVI change per SWMM evaluation even though V1–V3 are city-wide constants.

### 2.4 FRI -- Flood Resilience Index (3 indicators; all static)

All FRI indicators use **positive standardization** within the group (higher `R_m` = more resilience). The outer formula `(1 - FRI)` handles the sign inversion.

| ID | Indicator | Source | Standardization |
|---|---|---|---|
| R1 | Distance to emergency services | OSM POI + grid-based | `(max - raw) / (max - min)` (invert) |
| R2 | Shelter count (schools + hospitals) | OSM POI | min-max |
| R3 | Warning coverage | Population-based proxy | raw ratio in [0, 1] |

R4 (drainage capacity) was removed because it caused double-counting between the SWMM decision variables (sediment maintenance points) and the SWMM output (conduit surcharge statistics). In the HEVR framework used with a hydraulic model, the Resilience group should only contain elements beyond the model's computational scope.

---

## 3. Weight Computation — IFAHP + EWM + Combined

Weights `ρ_m` per group come from fusing **subjective** (expert-driven) and **objective** (data-driven) signals.

### 3.1 IFAHP (subjective)
Reference: `weights.md` §1. Six steps on an intuitionistic fuzzy pairwise matrix per expert:
1. Expert provides `(μ_ab, ν_ab)` for every pair, with `μ + ν ≤ 1`.
2. Compute per-expert reliability `λ_k` from matrix averages.
3. **IFWAA aggregation** with weights `λ_k`:
   - `μ_ab = 1 − Π(1 − μ_ab^(k))^{λ_k}`  (optimistic accumulation for membership)
   - `ν_ab = Π (ν_ab^(k))^{λ_k}`           (geometric product for non-membership)

   The asymmetry is deliberate. Applying the optimistic operator to both `μ` and `ν` (a common mistake) inflates both sides and breaks the IF constraint: in adversarial inputs the resulting cell can have `μ + ν > 1`. The geometric product on `ν` keeps `μ_ab + ν_ab ≤ 1` cell-by-cell.
4. **Distance-based consistency check.** Build a perfectly consistent matrix `R_bar` via Algorithm I (transitive closure of adjacent preferences), then compute `d(R_bar, R) = 1/(2(M-1)(M-2)) * sum(|mu_bar-mu| + |nu_bar-nu| + |pi_bar-pi|)`. **If `d >= 0.10`, the implementation falls back to uniform weights (sum omega = 1/M each)** and emits a `UserWarning` -- inconsistent expert judgments must be re-elicited rather than silently used.
5. Extract per-indicator triplet `(μ_m, ν_m, π_m)` by row averaging.
6. Fuzzy-entropy raw weight:
   $$\hat{\omega}_m = -\frac{1}{M \ln 2} \left[ \mu_m \ln \mu_m + \nu_m \ln \nu_m + (1 − \pi_m) \ln(1 − \pi_m) − \pi_m \ln 2 \right]$$
   Normalized: `ω_m = ω̂_m / Σ ω̂_i`.

### 3.2 EWM (objective)
Reference: `weights.md` §2. Five steps on a per-SC data matrix:
1. Min-max standardize (positive or negative direction per indicator).
2. Proportions `p_nm = r_nm / Σ_n r_nm`.
3. Entropy `e_m = −(1 / ln N) Σ p_nm ln p_nm`.
4. Redundancy `d_m = 1 − e_m`.
5. Normalize `θ_m = d_m / Σ d_i`.

### 3.3 Combined (preference coefficient)
$$\varepsilon_m = \frac{\theta_m^2}{\omega_m^2 + \theta_m^2}, \quad
\rho_m = \frac{\sqrt{(\varepsilon_m \omega_m)^2 + ((1 − \varepsilon_m) \theta_m)^2}}{\sum_i \sqrt{\cdots}}$$

When `ω_m = θ_m`, `ε = 0.5` (balanced mix). When data is very informative (`θ ≫ ω`), `ε → 1` and the combined weight leans toward `ω`; when data is uninformative (`θ ≪ ω`), it leans toward `θ`. This counter-intuitive dual weighting is intentional in the source method — it amplifies whichever signal has *more* uncertainty relative to the other.

**Computed once at init.** Weights do not change per SWMM evaluation.

---

## 4. Optimization Modes

`src/boswmm/config.yaml` selects the mode; `KPIEvaluation` and `BOSWMM` honor it.

| Mode | Objective vector | BoTorch acquisition |
|---|---|---|
| `single` | `[FROI]` (minimize scalar) | `qLogExpectedImprovement` |
| `multi`  | `[FHI, FEI, FVI, 1 − FRI]` (minimize all 4) | `qLogExpectedHypervolumeImprovement` |

All entries are minimized (lower = better flood outcome). In multi mode, the Pareto front is extracted at the end of the BO loop.

---

## 5. Per-Evaluation Pipeline

Inside `KPIEvaluation.evaluate(inp_path)`:

```
Decision vector x (maintenance volumes, length N)
        │
        ▼
ScenarioBuilder.build_scenario(x) → scenario .inp
        │
        ▼
SWMM Simulation (pyswmm)
        │
        ├── node_stats    : {junction: {flooding_volume, flooding_duration, …}}
        ├── conduit_stats : {conduit: {peak_flow, time_surcharged, …}}
        └── sim_duration_hours
        │
        ▼
FROIComputer.evaluate(node_stats, conduit_stats, sim_hours)
    • HazardIndicators  → (S,2) H_norm           [dynamic]
    • ExposureIndicators → (S,4) E_norm           [cached at init]
    • VulnerabilityIndicators → (S,3) V_norm     [cached at init]
    • ResilienceIndicators → (S,3) R_norm           [cached at init]
        │
        ▼
Per-SC indices (ρ_group are pre-computed IFAHP+EWM weights):
    FHI_s = H_norm @ ρ_H
    FEI_s = E_norm @ ρ_E
    FVI_s = FHI_s · (V_norm @ ρ_V)   ← dynamic scaling by per-SC hazard
    FRI_s = R_norm @ ρ_R
        │
        ▼
Region aggregation (simple or area-weighted mean):
    FHI, FEI, FVI, FRI
        │
        ▼
FROI = FHI · FEI · FVI · (1 − FRI)
        │
        ▼
Return depending on mode:
    single → {"kpi": [FROI], …}
    multi  → {"kpi": [FHI, FEI, FVI, 1 − FRI], …}
```

Of the 12 indicators, **only 2 are recomputed per evaluation** (H1, H2). FHI_s x FVI_raw scaling is a single multiply per subcatchment. Per-evaluation overhead is comparable to the legacy F1+F2+F3 computation -- one SWMM run plus light arithmetic.

---

## 6. Range Analysis

- `FHI, FEI, FRI ∈ [0, 1]` — weighted sums of [0, 1] indicators with Σ ρ = 1.
- `FVI_s = FHI_s · FVI_s^{raw}` with both factors in [0, 1], so `FVI_s ∈ [0, 1]`.
- `FROI ∈ [0, 1]` — product of four [0, 1] scalars.

---

## 7. Dependency on the Decision Variable

The decision variable `x ∈ [0, v_max]^N` (sediment maintenance volumes) only affects SWMM simulation results. Consequences:

- **FHI** changes per evaluation.
- **FEI** stays constant — demographics/land-use/roads don't depend on x.
- **FVI** changes per evaluation **through the FHI_s scaling**, even though V1–V3 are static.
- **FRI** stays constant -- R1-R3 are all static.

**In multi-objective mode,** the GP surrogates for FEI and FRI see zero variance (by design). BoTorch prints an `InputDataWarning` about non-standardized data -- benign. The effective multi-objective problem is 2-D (FHI, FVI) scaled by constants FEI and (1-FRI).

**In single-objective mode,** FROI varies through FHI and FVI; the constant FEI and FRI just scale the magnitude.

---

## Reference Files

| File | Role |
|---|---|
| `src/kpi/froi.py` | `FROIComputer` — orchestrates indicators + weights |
| `src/kpi/indicators/` | 4 indicator groups + `IndicatorGroup` base class |
| `src/kpi/weights/` | IFAHP, EWM, combined-weight algorithms |
| `src/kpi/aggregator.py` | Point-in-polygon subcatchment mapping + region aggregation |
| `src/kpi/config.yaml` | FROI configuration (data paths, references, mode-agnostic params) |
| `src/boswmm/kpi_evaluation.py` | Thin wrapper: run SWMM + delegate to FROIComputer |
| `indicators.md` | High-level indicator table (project-level spec) |
| `weights.md` | IFAHP / EWM / combined-weight derivations |
| `PLAN_indicators.md` | Detailed per-indicator extraction & calculation spec |
