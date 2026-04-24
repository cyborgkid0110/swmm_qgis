# `src/kpi/config.yaml` — FROI Configuration

The canonical configuration for the FROI objective function. Loaded by `src.kpi._config.load_default_config()`; a user-supplied dict of the same shape can override at runtime via `resolve_config(user_config)`.

## Schema

```yaml
indicators:
  fhi:
    # Reference for H2 volume standardization:
    #   V_ref_s = rainfall_depth_mm * area_ha * 10   (m^3)
    rainfall_depth_mm: 20.0

  fei:
    land_use_raster: "data/exposure/vietnam_landuse.tif"   # used if raster-based E2 is enabled
    # Tests on Site_Drainage_Model.inp use the pre-computed land_use_score
    # column in data/exposure/exposure.csv (mock values in local feet CRS).

  fvi:
    # Reference ranges for potential upstream normalization. Indicator CSVs
    # currently ship values already standardized to [0, 1], so these are
    # informational.
    income_ref_range: [30.0, 150.0]    # million VND / person / year
    grdp_ref_range: [10.0, 700.0]      # trillion VND

  fri:
    r4_zeta: 0.5      # Weight on Q_peak/Q_full term in R4 raw
    r4_gamma: 0.5     # Weight on T_surch/T_ref term in R4 raw
    # R4 reference is computed at init from a baseline (x=0) SWMM run
    # via FROIComputer.set_r4_reference_from_baseline(...)

aggregation:
  method: "simple"        # "simple" or "area_weighted"

standardization:
  fhi_method: "reference" # "reference" (fixed bounds) or "data" (min-max)
  external_method: "data" # for FEI/FVI/FRI static indicators

mapping:
  use_polygons: true      # primary: [POLYGONS] point-in-polygon
  fallback: "upstream_bfs"

data_paths:
  exposure:      "data/exposure/exposure.csv"
  vulnerability: "data/vulnerability/vulnerability.csv"
  resilience:    "data/resilience/resilience_static.csv"

weights:
  expert_matrices:
    fhi: "data/weights/expert_fhi.json"
    fei: "data/weights/expert_fei.json"
    fvi: "data/weights/expert_fvi.json"
    fri: "data/weights/expert_fri.json"
```

## Keys consumed by `FROIComputer`

| Config key | Constructor arg |
|---|---|
| `indicators.fhi.rainfall_depth_mm` | `rainfall_depth_mm` |
| `indicators.fri.r4_zeta`, `r4_gamma` | `r4_zeta`, `r4_gamma` |
| `aggregation.method` | `aggregation_method` |
| `data_paths.exposure` | `exposure_csv` |
| `data_paths.vulnerability` | `vulnerability_csv` |
| `data_paths.resilience` | `resilience_csv` |
| `weights.expert_matrices` | `load_expert_matrices(...)` → `expert_matrices` |

Other keys (`standardization.*`, `mapping.*`, `indicators.fei.*`, `indicators.fvi.*`) are reserved for future expansion and not currently read by the constructor — they document intended behavior for manual tuning.

## Loader

```python
from src.kpi._config import load_default_config, resolve_config

cfg = load_default_config()
# Override inline:
custom = resolve_config({
    "indicators": {"fri": {"r4_zeta": 0.7, "r4_gamma": 0.3}},
    ...  # same top-level shape
})
```

`resolve_config(None)` returns the default; `resolve_config(dict)` returns the dict as-is (no deep merge — the caller must provide a fully-populated structure).
