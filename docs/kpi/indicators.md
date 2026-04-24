# `src/kpi/indicators/` — Indicator Groups

Four classes, one per index. All produce **standardized per-subcatchment matrices** that `FROIComputer` accumulates into the region sub-indices.

| Class | File | Group | M | Dynamic? |
|---|---|---|---|---|
| `HazardIndicators` | `hazard.py` | FHI | 2 | Yes |
| `ExposureIndicators` | `exposure.py` | FEI | 4 | No (cached at init) |
| `VulnerabilityIndicators` | `vulnerability.py` | FVI | 3 | No (made dynamic in FROIComputer via FHI_s scaling) |
| `ResilienceIndicators` | `resilience.py` | FRI | 4 | R4 yes, R1–R3 cached |

Shared base: `IndicatorGroup` (`base.py`) with `minmax_standardize` and `reference_standardize` helpers.

---

## `HazardIndicators`

| Indicator | Source | Per-SC aggregation | Standardization |
|---|---|---|---|
| H1 — flood duration | `node.statistics["flooding_duration"]` | Mean across junctions in SC | `x / T_ref`, clamped |
| H2 — flood volume | `node.statistics["flooding_volume"]` | **Sum** across junctions in SC | `min(1, x / V_ref_s)` where `V_ref_s = rainfall_depth_mm × area_ha × 10` |

```python
HazardIndicators(
    subcatchment_names: list[str],
    junction_to_sc: dict[str, str],
    subcatchment_areas: dict[str, float],   # hectares
    *,
    rainfall_depth_mm: float = 50.0,
    sim_duration_hours: float = 1.0,
)
```

`compute(node_stats, sim_duration_hours=None) -> (normalized, fhi_s_raw)` returns the standardized `(S, 2)` matrix. The second return value is currently identical — reserved for a future version of FHI_s that is computed here rather than in `FROIComputer`.

---

## `ExposureIndicators`

All 4 indicators are loaded once from a single CSV:

```csv
subcatchment_id,population_density,land_use_score,road_density,facility_score
S1,12500,0.85,14.2,8.3
...
```

| Indicator | Standardization |
|---|---|
| E1 — population density | min-max across SCs |
| E2 — land use score | already in [0, 1] (JAXA class → exposure score) |
| E3 — road density | min-max |
| E4 — facility score | min-max |

```python
ExposureIndicators(subcatchment_names, exposure_csv)
```

`compute()` returns the cached `(S, 4)` matrix on every call.

---

## `VulnerabilityIndicators`

Three city-wide indicators broadcast to all subcatchments:

```csv
city,elderly_children_rate,grdp_normalized,income_normalized
Ha Noi,0.357,0.68,0.45
```

| Indicator | Direction | Notes |
|---|---|---|
| V1 — elderly & children rate | positive | `(P<15 + P>60) / P_total` |
| V2 — GDP / GRDP | positive | Normalized against national range upstream |
| V3 — average income | **negative** (inverted upstream) | Treat the CSV value as already representing "higher = more vulnerable" |

```python
VulnerabilityIndicators(subcatchment_names, vulnerability_csv)
```

`compute()` returns `(S, 3)` where all rows are identical (city-wide). The dynamic FVI scaling by FHI_s happens inside `FROIComputer`, not here — this class stays dumb.

---

## `ResilienceIndicators`

Mixed static + dynamic. R1–R3 come from a CSV; R4 is recomputed each SWMM run.

```csv
subcatchment_id,avg_emergency_distance_m,shelter_count,warning_coverage_ratio
S1,850,4,0.78
...
```

| Indicator | Standardization |
|---|---|
| R1 — emergency distance | min-max, then inverted (closer → higher resilience) |
| R2 — shelter count | min-max (higher count → higher resilience) |
| R3 — warning coverage | raw ratio in [0, 1] |
| R4 — drainage capacity | `1 − min(1, raw / R4_ref)`, per-subcatchment F2 accumulator |

All four are **positive within FRI** (higher = more resilient). The outer FROI formula `(1 − FRI)` handles sign inversion.

R4 raw formula (per subcatchment `s`):

$$R4_s^{raw} = \sum_{c \in C_s} L_c \left[\zeta \cdot \frac{Q_c^{peak}}{Q_c^{full}} + \gamma \cdot \frac{T_c^{surch}}{T_{ref}}\right]$$

`Q_full` comes from Manning's equation at construction time (same helper as `src/boswmm/kpi_evaluation.py`'s legacy F2).

```python
ResilienceIndicators(
    subcatchment_names,
    resilience_csv,
    conduit_to_sc,
    conduit_props,
    xsection_props,
    node_elevations,
    *,
    r4_zeta=0.5,
    r4_gamma=0.5,
)

# Seed the R4 reference from a baseline run (call once before optimization):
fri.set_r4_reference(fri.compute_r4_raw(baseline_conduit_stats, baseline_hours))

# Full per-SC FRI indicators on each evaluation:
R_norm = fri.compute(conduit_stats, sim_duration_hours)   # shape (S, 4)
```

If `set_r4_reference` is never called, `compute` falls back to using the current run's max as an on-the-fly reference (uninformative but safe).

---

## Standardization helpers (`base.py`)

```python
minmax_standardize(values, positive=True) -> np.ndarray
reference_standardize(values, reference, positive=True, clamp=True) -> np.ndarray
```

`minmax` returns 0.5 when all values are equal (neutral) — avoids NaN on constant columns. `reference_standardize` divides by a fixed bound; use it for dynamic SWMM-derived indicators so standardization is stable across evaluations.
