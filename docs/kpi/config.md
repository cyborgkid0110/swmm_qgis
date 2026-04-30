# `src/kpi/config.yaml` -- FROI Configuration

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

  fvi:
    # V2/V3 tanh scales are hardcoded in vulnerability.py.

  fri:
    # R1-R3 static resilience indicators only. No config params needed.

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

All keys below are extracted internally when `FROIComputer` resolves its `kpi_config`:

| Config key | Internal use |
|---|---|
| `indicators.fhi.rainfall_depth_mm` | Passed to `HazardIndicators` for H2 V_ref |
| `aggregation.method` | Region aggregation strategy (`simple` / `area_weighted`) |
| `data_paths.exposure` | CSV path for `ExposureIndicators` |
| `data_paths.vulnerability` | CSV path for `VulnerabilityIndicators` |
| `data_paths.resilience` | CSV path for `ResilienceIndicators` |
| `weights.expert_matrices` | JSON paths loaded via `load_expert_matrices()` for IFAHP |

Other keys (`standardization.*`, `mapping.*`, `indicators.fei.*`, `indicators.fvi.*`) are reserved for future expansion and not currently read by the constructor.

## Loader

```python
from src.kpi._config import load_default_config, resolve_config

cfg = load_default_config()                    # always loads src/kpi/config.yaml
custom = resolve_config(None)                  # same as load_default_config()
custom = resolve_config("path/to/config.yaml") # load from a custom YAML path
custom = resolve_config({"indicators": ...})   # use a dict directly
```

`resolve_config(None)` returns the default; `resolve_config(str)` loads a YAML file; `resolve_config(dict)` returns the dict as-is (no deep merge -- the caller must provide a fully-populated structure).

Note: `FROIComputer` and `KPIEvaluation` both call `resolve_config` internally, so callers typically do not need to invoke it directly.
