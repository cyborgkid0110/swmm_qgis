# `src/kpi/indicators/` -- Indicator Groups

Four classes, one per index. All produce **standardized per-subcatchment matrices** that `FROIComputer` accumulates into the region sub-indices.

| Class | File | Group | M | Dynamic? |
|---|---|---|---|---|
| `HazardIndicators` | `hazard.py` | FHI | 2 | Yes |
| `ExposureIndicators` | `exposure.py` | FEI | 4 | No (cached at init) |
| `VulnerabilityIndicators` | `vulnerability.py` | FVI | 3 | No (made dynamic in FROIComputer via FHI_s scaling) |
| `ResilienceIndicators` | `resilience.py` | FRI | 3 | No (cached at init) |

Shared base: `IndicatorGroup` (`base.py`) with `minmax_standardize` and `reference_standardize` helpers.

---

## `HazardIndicators`

| Indicator | Source | Per-SC aggregation | Standardization |
|---|---|---|---|
| H1 -- flood duration | `node.statistics["flooding_duration"]` | Mean across junctions in SC | `x / T_ref`, clamped |
| H2 -- flood volume | `node.statistics["flooding_volume"]` | **Sum** across junctions in SC | `min(1, x / V_ref_s)` where `V_ref_s = rainfall_depth_mm * area_ha * 10` |

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

`compute(node_stats, sim_duration_hours=None) -> (normalized, fhi_s_raw)` returns the standardized `(S, 2)` matrix.

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
| E1 -- population density | min-max across SCs |
| E2 -- land use score | already in [0, 1] (JAXA class -> exposure score) |
| E3 -- road density | min-max |
| E4 -- facility score | min-max |

```python
ExposureIndicators(subcatchment_names, exposure_csv)
```

`compute()` returns the cached `(S, 4)` matrix on every call.

---

## `VulnerabilityIndicators`

Three city-wide indicators broadcast to all subcatchments:

```csv
city,elderly_children_rate,grdp_trillion_vnd,income_million_vnd
Ha Noi,0.357,486.0,72.0
```

| Indicator | Direction | Normalization |
|---|---|---|
| V1 -- elderly & children rate | positive | Raw ratio already in [0,1] |
| V2 -- GDP / GRDP | positive | `tanh(grdp_trillion_vnd / v2_scale)` |
| V3 -- average income | **negative** | `1 - tanh(income_million_vnd / v3_scale)` |

V2 and V3 use `tanh(x / scale)` normalization because their raw values (trillion VND, million VND) have no natural upper bound. The `scale` parameter controls the steepness: values near `scale` map to ~0.76. Defaults: `v2_scale=500.0`, `v3_scale=100.0`.

```python
VulnerabilityIndicators(subcatchment_names, vulnerability_csv,
                        v2_scale=500.0, v3_scale=100.0)
```

`compute()` returns `(S, 3)` where all rows are identical (city-wide). The dynamic FVI scaling by FHI_s happens inside `FROIComputer`, not here.

---

## `ResilienceIndicators`

Three static indicators from a CSV. All cached at init.

```csv
subcatchment_id,avg_emergency_distance_m,shelter_count,warning_coverage_ratio
S1,850,4,0.78
...
```

| Indicator | Standardization |
|---|---|
| R1 -- emergency distance | min-max, then inverted (closer -> higher resilience) |
| R2 -- shelter count | min-max (higher count -> higher resilience) |
| R3 -- warning coverage | raw ratio in [0, 1] |

All three are **positive within FRI** (higher = more resilient). The outer FROI formula `(1 - FRI)` handles sign inversion.

```python
ResilienceIndicators(subcatchment_names, resilience_csv)

R_norm = fri.compute()   # shape (S, 3)
```

---

## Standardization helpers (`base.py`)

```python
minmax_standardize(values, positive=True) -> np.ndarray
reference_standardize(values, reference, positive=True, clamp=True) -> np.ndarray
```

`minmax` returns 0.5 when all values are equal (neutral) -- avoids NaN on constant columns. `reference_standardize` divides by a fixed bound; use it for dynamic SWMM-derived indicators so standardization is stable across evaluations.
