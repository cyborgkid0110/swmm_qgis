# Conversion Module Documentation

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
  - [Pipeline](#pipeline)
  - [QGIS Initialization](#qgis-initialization)
- [Class: Conversion](#class-conversion)
  - [Constructor](#constructor)
  - [Class Constants](#class-constants)
- [Static Helper Methods](#static-helper-methods)
- [Spatial Filtering Methods](#spatial-filtering-methods)
- [Coordinate Registry & Junction Deduplication](#coordinate-registry--junction-deduplication)
- [QGIS Layer Factories](#qgis-layer-factories)
- [Node Layer Creators](#node-layer-creators)
  - [create_junctions](#create_junctionscsv_pathnone)
  - [create_storage](#create_storagecsv_pathnone)
  - [create_outfalls](#create_outfallscsv_pathnone)
- [Hydrology Layer Creators](#hydrology-layer-creators)
  - [create_raingages](#create_raingagescsv_pathnone)
  - [create_subcatchments](#create_subcatchmentscsv_pathnone-coord_registrynone)
- [Timeseries Table](#timeseries-table)
- [Link Layer Creators](#link-layer-creators)
  - [create_conduits](#create_conduitscsv_pathnone)
  - [create_pumps](#create_pumpscsv_pathnone)
  - [create_orifices](#create_orificescsv_pathnone)
  - [create_weirs](#create_weirscsv_pathnone)
- [LineString Decomposition](#linestring-decomposition)
  - [create_canal_conduits](#create_canal_conduits)
  - [create_river_conduits](#create_river_conduits)
- [Congdap-Canal Integration](#congdap-canal-integration)
- [DEM Elevation Refinement](#dem-elevation-refinement)
- [MaxDepth Determination](#maxdepth-determination)
- [Auto-Junction Merge](#auto-junction-merge)
- [Options Table](#options-table)
- [Main Orchestration: run()](#main-orchestration-run)
- [Regional Scripts](#regional-scripts)
- [Component Summary](#component-summary)
- [Known Issues & Warnings](#known-issues--warnings)

---

## Overview

The conversion module (`src/conversion/conversion.py`) transforms standardized drainage/sewer datasets (CSV files with GeoJSON geometry) into EPA SWMM `.inp` input files. It uses the `generate_swmm_inp` QGIS plugin (v0.40, by Jannik Schilling) as the backend to serialize QGIS in-memory layers into the SWMM text format.

Three regional wrapper scripts provide bbox-filtered conversion for specific areas:
- `src/conversion/conversion_hanoi.py` — Hanoi region
- `src/conversion/conversion_hcm.py` — Ho Chi Minh City region
- `src/conversion/conversion_sample.py` — Sample region (cropped datasets, fast testing)

### Dependencies

| Dependency | Purpose |
|------------|---------|
| QGIS (`qgis.core`) | In-memory vector layers, geometry, processing framework |
| `generate_swmm_inp` plugin | Serializes QGIS layers to `.inp` file format |
| `openpyxl` | Writes OPTIONS table as `.xlsx` (plugin input) |
| `pyswmm` (optional) | Post-generation validation via `test.py` |

### Environment

```
conda run -n qgis-env python src/conversion/conversion.py            # full model (no bbox)
conda run -n qgis-env python src/conversion/conversion_hanoi.py     # Hanoi region only
conda run -n qgis-env python src/conversion/conversion_hcm.py       # HCM region only
conda run -n qgis-env python test.py <path>.inp       # validate with pyswmm
```

---

## Architecture

### Pipeline

```
Standardized CSVs
    │
    ▼
┌──────────────────────────────────┐
│  Conversion class                │
│  1. Read CSV rows                │
│  2. Parse GeoJSON geometry       │
│  3. Apply bbox filter (optional) │
│  4. Build QGIS in-memory layers  │
│     with SWMM field names        │
│  5. Coordinate-based junction    │
│     deduplication                │
└──────────┬───────────────────────┘
           │
           ▼
┌──────────────────────────────────┐
│  generate_swmm_inp plugin        │
│  (QGIS Processing framework)    │
│  - Reads layer attributes        │
│  - Writes [JUNCTIONS], [CONDUITS]│
│    [XSECTIONS], [PUMPS], etc.    │
│  - Handles .inp section format   │
└──────────┬───────────────────────┘
           │
           ▼
      SWMM .inp file
```

### QGIS Initialization

The module initializes QGIS at import time (module-level code, lines 20-38):
1. Sets `QGIS_PREFIX_PATH` from conda environment
2. Creates headless `QgsApplication` (no GUI)
3. Adds the `generate_swmm_inp` plugin directory to `sys.path`

This means importing `conversion.py` requires the `qgis-env` conda environment.

---

## Class: `Conversion`

### Constructor

```python
Conversion(dataset_dir, result_dir, bbox=None)
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `dataset_dir` | `str` | Root dataset directory (e.g., `dataset/`) |
| `result_dir` | `str` | Output directory for `.inp` files |
| `bbox` | `tuple` or `None` | Optional `(min_lon, min_lat, max_lon, max_lat)` spatial filter in WGS84. When set, only features within this bounding box are included. |

The constructor resolves paths to all 11 input CSV files:

| Attribute | CSV File | Component |
|-----------|----------|-----------|
| `manholes_csv` | `thoat_nuoc/manholes.csv` | Manholes |
| `sewers_csv` | `thoat_nuoc/sewers.csv` | Sewer conduits |
| `pumps_csv` | `thoat_nuoc/pumps.csv` | Pumping stations |
| `orifices_csv` | `thoat_nuoc/orifices.csv` | Tidal gates |
| `weirs_csv` | `thoat_nuoc/weir.csv` | Weirs (congdap + outlets merged) |
| `outfalls_csv` | `thoat_nuoc/outfalls.csv` | Outfalls (boundary nodes) |
| `lakes_csv` | `mang_luoi_song_ho_kenh_muong/lakes.csv` | Lakes/ponds |
| `rivers_csv` | `mang_luoi_song_ho_kenh_muong/rivers.csv` | River network |
| `canals_csv` | `mang_luoi_song_ho_kenh_muong/canals.csv` | Canal network |
| `raingages_csv` | `thuy_van/raingages.csv` | Rain gages |
| `subcatchments_csv` | `dia_hinh_khong_gian/subcatchments.csv` | Subcatchments |

### Class Constants

| Constant | Value | Description |
|----------|-------|-------------|
| `ROUGHNESS` | `{"BTCT": 0.013, "PVC": 0.011, "HDPE": 0.012}` | Manning's n by pipe material |
| `DEFAULT_ROUGHNESS` | `0.013` | Fallback Manning's n |
| `LINK_OFFSET` | `0.00005` (~5 m) | Longitude offset for auto-generating ToNode from Point-based links |

---

## Static Helper Methods

### `_read_csv(path)`
Reads a CSV file with `utf-8-sig` encoding. Returns list of `dict` rows.

### `_parse_geojson(s)`
Parses a GeoJSON string from a CSV cell. Returns `(type, coordinates)` or `(None, None)`.

- Point: `coordinates = [lon, lat]`
- LineString: `coordinates = [[lon1, lat1], [lon2, lat2], ...]`

### `_swmm_name(name, max_len=25)`
Sanitizes a name for SWMM compatibility:
1. Strips non-ASCII characters (Vietnamese diacritics)
2. Replaces spaces and unsafe characters with `_`
3. Collapses repeated underscores
4. Truncates to `max_len` (SWMM's internal limit is 25 characters, `MAXID`)

Use `max_len=20` when an `_{ID}` suffix will be appended later.

### `_safe_float(val, default=0.0)`
Parses float values with Vietnamese number format handling:
- Comma as decimal separator: `"0,5"` → `0.5`
- Leading plus sign: `"+7,33"` → `7.33`
- Compound values (semicolon-separated): `"+7,1 ; +8,52"` → `7.1` (takes first)
- Returns `default` on failure

### `_haversine(lon1, lat1, lon2, lat2)`
Computes great-circle distance in **meters** between two WGS84 points using the Haversine formula. Used to compute conduit segment lengths from coordinate pairs.

---

## Spatial Filtering Methods

### `_point_in_bbox(lon, lat)`
Returns `True` if the point falls within `self.bbox`. Always returns `True` if `bbox` is `None`.

### `_linestring_in_bbox(coords)`
Returns `True` if **any** point of the LineString falls within `self.bbox`. This means a feature is included if it intersects the bounding box (not only if fully contained).

These methods are called in every creator method to filter features before processing.

---

## Coordinate Registry & Junction Deduplication

### Problem

Canal and river LineString features share endpoints at confluences and intersections. Without deduplication, these shared points would create duplicate junctions with different names, breaking SWMM network connectivity.

### Solution: Coordinate-based Registry

A shared `coord_registry` dictionary maps coordinate keys to junction data:

```
Key:   (round(lon, 6), round(lat, 6))   # ~0.11m precision
Value: {"name": str, "elevation": float, "max_depth": float}
```

### `_build_manhole_index()`

Pre-builds a coordinate → manhole-data mapping from `manholes.csv`. This is used to **pre-seed** the coordinate registry so that auto-generated canal/river junctions at manhole locations inherit the manhole's name, elevation, and depth instead of creating a duplicate node.

Returns: `dict` with same key/value structure as `coord_registry`.

### `_get_or_create_junction(coord_registry, lon, lat, name_candidate, elevation, max_depth)`

Static method. Looks up `(round(lon,6), round(lat,6))` in the registry:
- **If found**: returns the existing junction name (deduplication)
- **If not found**: registers the new junction with the candidate name and returns it

This ensures shared endpoints between different LineString features map to the same SWMM junction.

### `_find_nearest_junction(coord_registry, lon, lat)`

Static method. Searches all junctions in the coordinate registry and returns `(junction_name, distance_m)` for the one closest to `(lon, lat)` using Haversine distance. Used by `create_subcatchments()` to resolve `OutletLon`/`OutletLat` coordinates to the nearest SWMM junction node.

---

## QGIS Layer Factories

### `_point_layer(name, fields)`
Creates an in-memory Point layer (EPSG:4326) with the given field schema.

### `_line_layer(name, fields)`
Creates an in-memory LineString layer (EPSG:4326) with the given field schema.

### `_junction_fields()`
Returns the QGIS field schema for SWMM JUNCTIONS:

| Field | Type | Description |
|-------|------|-------------|
| Name | String(150) | Junction identifier |
| Elevation | Double | Invert elevation (m) |
| MaxDepth | Double | Maximum water depth (m) |
| InitDepth | Double | Initial water depth (m), always 0.0 |
| SurDepth | Double | Surcharge depth (m), always 0.0 |
| Aponded | Double | Ponded area (m^2), always 0.0 |

### `_conduit_fields()`
Returns the QGIS field schema for SWMM CONDUITS + XSECTIONS:

| Field | Type | Description |
|-------|------|-------------|
| Name | String(150) | Conduit identifier |
| FromNode | String(150) | Upstream junction name |
| ToNode | String(150) | Downstream junction name |
| Length | Double | Conduit length (m) |
| Roughness | Double | Manning's n |
| InOffset | Double | Inlet offset (m), always 0.0 |
| OutOffset | Double | Outlet offset (m), always 0.0 |
| InitFlow | Double | Initial flow (CMS), always 0.0 |
| MaxFlow | Double | Maximum flow (CMS), always 0.0 |
| XsectShape | String(30) | Cross-section type (CIRCULAR, RECT_CLOSED, TRAPEZOIDAL) |
| Geom1 | Double | Primary dimension (depth or diameter in m) |
| Geom2 | Double | Secondary dimension (width in m, or 0) |
| Geom3 | Double | Left side slope (for TRAPEZOIDAL) |
| Geom4 | Double | Right side slope (for TRAPEZOIDAL) |
| Barrels | Int | Number of barrels, always 1 |
| Culvert, Shp_Trnsct, Kentry, Kexit, Kavg, FlapGate, Seepage | various | Optional fields (defaults) |

### `_link_from_point(lon, lat)`
Creates a short (~5 m) LineString geometry from a Point coordinate. Used for point-based link components (pumps, orifices, weirs) which are modeled as SWMM links but stored as Points in the source data.

The line runs from `(lon, lat)` to `(lon + LINK_OFFSET, lat)`.

---

## Node Layer Creators

### `create_junctions(csv_path=None)`

**Source**: `manholes.csv` (or custom path)
**SWMM section**: `[JUNCTIONS]`
**Geometry**: Point (GeoJSON in `Shape` column)

**Field mapping**:

| SWMM Field | Source | Default |
|------------|--------|---------|
| Name | `Name` (sanitized) | — |
| Elevation | `InvElev_m` | 5.0 |
| MaxDepth | `RimElev_m - InvElev_m` | 3.0 |
| InitDepth | — | 0.0 |
| SurDepth | — | 0.0 |
| Aponded | — | 0.0 |

**Returns**: `(layer, [])` — no auto-junctions produced.

### `create_storage(csv_path=None)`

**Source**: `lakes.csv`
**SWMM section**: `[STORAGE]`
**Geometry**: Point

**Field mapping**:

| SWMM Field | Source | Default |
|------------|--------|---------|
| Name | `Name` (sanitized) | — |
| Elevation | `BedElev_m` | 3.0 |
| MaxDepth | `BankElev_m - BedElev_m` | 3.0 |
| InitDepth | `WetLvl_m - BedElev_m` | 1.0 |
| Type | — | `"FUNCTIONAL"` |
| Constant | `Area_ha * 10000` | 10000.0 m^2 |

Uses flat-bottom approximation: `A(y) = Constant` (surface area independent of depth).

**Returns**: `(layer, [])`.

### `create_outfalls(csv_path=None)`

**Source**: `outfalls.csv`
**SWMM section**: `[OUTFALLS]`
**Geometry**: Point (GeoJSON in `Shape` column)

Outfalls are boundary nodes where water exits the drainage system (e.g., river discharge points). Each row in the CSV becomes an OUTFALL node.

**Field mapping**:

| SWMM Field | Source | Default |
|------------|--------|---------|
| Name | `Name` (sanitized) | `OF{ID}` |
| Elevation | `Elev_m` | 0.0 |
| Type | `Type` | `"FREE"` |
| FixedStage | `FixedStage` | 0.0 |
| FlapGate | `FlapGate` | `"NO"` |

Supported outfall types: `FREE` (critical depth), `NORMAL`, `FIXED` (fixed stage), `TIDAL`, `TIMESERIES`.

**Returns**: `layer` (no auto-junctions tuple).

---

## Hydrology Layer Creators

### `create_raingages(csv_path=None)`

**Source**: `raingages.csv`
**SWMM section**: `[RAINGAGES]`
**Geometry**: Point (GeoJSON in `Shape` column)

**Field mapping**:

| SWMM Field | Source | Default |
|------------|--------|---------|
| Name | `Name` (sanitized) | — |
| Format | `Format` | `"VOLUME"` |
| Interval | `Interval` | `"1:00"` |
| SCF | `SCF` | 1.0 |
| DataSource | `DataSource` | `"TIMESERIES"` |
| SeriesName | `SeriesName` | — |
| StationID | `StationID` | — |
| RainUnits | `RainUnits` | `"MM"` |
| FileName | — | `""` |

**Returns**: `layer` (no auto-junctions).

### `create_subcatchments(csv_path=None, coord_registry=None)`

**Source**: `subcatchments.csv`
**SWMM sections**: `[SUBCATCHMENTS]` + `[SUBAREAS]` + `[INFILTRATION]`
**Geometry**: Polygon (GeoJSON in `Shape` column, outer ring used as centroid Point)

**Outlet determination**: The CSV provides `OutletLon`/`OutletLat` coordinates (WGS84) for the subcatchment's drainage point. The method uses `_find_nearest_junction()` to search the `coord_registry` (populated during canal/sewer decomposition) and assigns the closest junction as the SWMM outlet node. The `SewerRoute` field is informational only and not used in the lookup.

**Field mapping**:

| SWMM Field | Source | Default |
|------------|--------|---------|
| Name | `Name` (sanitized) | — |
| RainGage | `RainGage` | — |
| Outlet | nearest junction to `OutletLon`/`OutletLat` | — |
| Area | `Area_ha` | 1.0 |
| Imperv | `Imperv_pct` | 25.0 |
| Width | `Width_m` | 100.0 |
| Slope | `Slope_pct` | 0.5 |
| CurbLen | `CurbLen_m` | 0.0 |
| N_Imperv | `N_Imperv` | 0.015 |
| N_Perv | `N_Perv` | 0.15 |
| S_Imperv | `S_Imperv_mm` | 1.5 |
| S_Perv | `S_Perv_mm` | 5.0 |
| PctZero | `PctZero` | 25.0 |
| RouteTo | `RouteTo` | `"OUTLET"` |
| PctRouted | `PctRouted` | 100.0 |
| InfMethod | `InfMethod` | `"MODIFIED_GREEN_AMPT"` |
| SuctHead | `SuctHead_mm` | 150.0 |
| Conductiv | `Conductiv_mmh` | 25.0 |
| InitDef | `InitDef` | 0.25 |

The subcatchment geometry is stored as a Polygon in the CSV but converted to a Point (centroid of first vertex) for SWMM. The plugin writes the polygon vertices to the `[Polygons]` section for visualization.

**Returns**: `layer` (no auto-junctions).

---

## Timeseries Table

### `create_timeseries_table(out_path=None)`

Generates an Excel `.xlsx` file with rainfall time-series data for SWMM simulation. Each rain gage references a named time series.

**Default**: Generates a synthetic 24-hour storm event `TS_CuChi` (name matches `SeriesName` in raingages CSV):

| Hour | Rainfall (mm) |
|------|--------------|
| 0-5 | 0.0 |
| 5 | 0.5 |
| 6 | 1.0 |
| 7 | 2.0 |
| 8 | 5.0 |
| 9 | 8.0 |
| 10 | 12.0 |
| 11 | 15.0 (peak) |
| 12 | 10.0 |
| 13-17 | 6.0→0.5 |
| 18-23 | 0.2→0.0 |

**Total**: 66.2 mm over 24 hours.

**Excel format**: Columns `Name`, `Date`, `Time`, `Value`, `File_Name` — matching the plugin's expected schema.

---

## Link Layer Creators

All link creators return `(layer, auto_junctions)` where `auto_junctions` is a list of `(name, lon, lat, elevation, max_depth)` tuples for nodes that need to be auto-generated.

### `create_conduits(csv_path=None)`

**Source**: `sewers.csv`
**SWMM section**: `[CONDUITS]` + `[XSECTIONS]`
**Geometry**: LineString (GeoJSON in `RouteShape` column)

**Field mapping**:

| SWMM Field | Source | Default |
|------------|--------|---------|
| Name | `Name` (sanitized) | — |
| FromNode | `FromNode` (sanitized) | — |
| ToNode | `ToNode` (sanitized) | — |
| Length | `Length_m` | 100.0 |
| Roughness | `Material` → lookup table | 0.013 |
| XsectShape | `XSType` | `"CIRCULAR"` |
| Geom1 | `Diam_mm / 1000` or `Size_mm` height | 0.4 |
| Geom2 | `Size_mm` width (RECT_CLOSED only) | 0.0 |

**Cross-section logic**:
- `CIRCULAR`: Geom1 = diameter (m), Geom2 = 0
- `RECT_CLOSED`: Geom1 = height (m), Geom2 = width (m), parsed from `"WxH"` format in `Size_mm`
- Fallback: Geom1 = 0.4 m, Geom2 = 0

**Roughness lookup** (Manning's n by material):
- BTCT (reinforced concrete): 0.013
- PVC: 0.011
- HDPE: 0.012
- Unknown: 0.013

**Returns**: `(layer, [])` — sewers reference existing manhole junctions by name, no auto-generation needed.

### `create_pumps(csv_path=None)`

**Source**: `pumps.csv`
**SWMM section**: `[PUMPS]`
**Geometry**: Point (converted to short LineString via `_link_from_point`)

**Field mapping**:

| SWMM Field | Source | Default |
|------------|--------|---------|
| Name | `Name_{ID}` | — |
| FromNode | `FromNode` or `PN{ID}_in` | — |
| ToNode | `ToNode` or `PN{ID}_out` | — |
| PumpCurve | — | `None` (plugin converts to `*` = ideal pump) |
| Status | — | `"ON"` |
| Startup | — | 0.0 |
| Shutoff | — | 0.0 |

**Auto-junctions**: 2 per pump (FromNode at point, ToNode at point + LINK_OFFSET). Both with elevation=0.0, max_depth=3.0.

### `create_orifices(csv_path=None, coord_registry=None, lake_index=None)`

**Source**: `orifices.csv`
**SWMM section**: `[ORIFICES]`
**Geometry**: Point → LineString from FromNode to ToNode

**Field mapping**:

| SWMM Field | Source | Default |
|------------|--------|---------|
| Name | `Name_{ID}` | — |
| FromNode | Resolved from `Source` attribute | `OR{ID}_up` at orifice position |
| ToNode | Resolved from `Receiver` attribute | `OR{ID}_dn` at LINK_OFFSET |
| Type | — | `"BOTTOM"` |
| InOffset | `InvElev_m` | 0.0 |
| Qcoeff | `DischCoef` | 0.65 |
| FlapGate | — | `"NO"` |
| XsectShape | — | `"RECT_CLOSED"` |
| Height | `Height_m` | 1.0 (if missing/zero) |
| Width | `Width_m` | 1.0 (if missing/zero) |

**Spatial linking logic**:

- **FromNode** (upstream): Resolved from the `Source` CSV attribute, which names the upstream sewer or canal route.
  - Finds nearest junction on that route (excluding inline weir junctions with `CD` prefix) within 500m.
  - If found, FromNode merges with that junction (same position = same node as the sewer endpoint).
  - If `Source` is empty or no match: auto-generates `OR{ID}_up` at orifice position.
  - For lake `Receiver`: FromNode snaps to nearest junction at the orifice position via `_get_or_create_junction`.

- **ToNode** (downstream): Resolved from the `Receiver` CSV attribute.
  - **Lake target**: if `Receiver` matches a lake name in `lake_index`, ToNode = lake junction `LK_{name}`.
  - **Canal/river target**: finds nearest junction on the matching route (excluding `CD` prefix weir junctions) within 500m.
    If ToNode position coincides with orifice position (< 2m), the ToNode is offset by `LINK_OFFSET` so the orifice link has non-zero length.
  - **Fallback**: nearest any junction.

**Weir junction exclusion**: `_find_nearest_junction_on_route()` is called with `exclude_prefix="CD"` to prevent orifices from accidentally connecting to inline weir junction nodes (`CD{id}_up`, `CD{id}_dn`).

**Auto-junctions**: 2 per orifice (FromNode + ToNode), elevation=0.0, max_depth=3.0. Refined by DEM.

### `create_weirs(csv_path=None)`

**Source**: `weir.csv` (merged from `congdap.csv` + `outlets.csv`)
**SWMM section**: `[WEIRS]`
**Geometry**: Point → short LineString

**Field mapping**:

| SWMM Field | Source | Default |
|------------|--------|---------|
| Name | `Name_{ID}` | — |
| FromNode | `CD{ID}_up` | — |
| ToNode | `CD{ID}_dn` | — |
| Type | — | `"TRANSVERSE"` |
| CrestHeigh | `CrestElv` | 0.0 |
| Qcoeff | — | 1.84 |
| FlapGate | — | `"NO"` |
| Height | `Height_m` | 0.5 (if missing/zero) |
| Length | `Length_m` | 10.0 (if missing/zero) |
| SideSlope | — | 0.0 |

**Auto-junctions**: 2 per weir, elevation=0.0, max_depth=3.0.

---

## LineString Decomposition

### `_decompose_linestrings(...)`

Core method that converts LineString features (canals, rivers) into connected junction+conduit networks.

**Concept**: A LineString with N coordinate points produces:
- **N junctions** (one per point, coordinate-deduplicated)
- **N-1 conduits** (one per segment between consecutive points)

```
LineString: P0 ──── P1 ──── P2 ──── P3

SWMM model:
  Junctions: J0, J1, J2, J3
  Conduits:  J0→J1, J1→J2, J2→J3
```

**Parameters**:

| Parameter | Description |
|-----------|-------------|
| `csv_path` | Path to standardized CSV with `RouteShape` column |
| `prefix` | Name prefix: `"CN"` for canals, `"RN"` for rivers |
| `layer_name` | QGIS layer name for display |
| `xs_type` | SWMM cross-section type (always `"TRAPEZOIDAL"`) |
| `roughness` | Manning's n value |
| `coord_registry` | Shared dict for coordinate-based junction dedup |
| `default_width` | Fallback bottom width (m) |
| `default_depth` | Fallback channel depth (m) |
| `default_slope` | Fallback side slope (H:V) |

**Algorithm per CSV row**:

1. Parse `RouteShape` GeoJSON → `coords[]` with N points
2. Parse physical dimensions from CSV columns:
   - `Width_m` → bottom width (Geom2)
   - `BedElev_m` → bed elevation (junction Elevation)
   - `BankElev_m` → bank elevation (used for depth)
   - `SlopCoef` → side slope (Geom3, Geom4)
3. Compute depth:
   - If `BankElev_m > BedElev_m`: depth = difference
   - Otherwise: use `default_depth`
4. For each point `i` (0..N-1):
   - Register junction via `_get_or_create_junction(coord_registry, ...)`
   - Name candidate: `{prefix}J{fid}_{i}` (e.g., `CNJ42_3`)
   - If coordinates already registered (shared endpoint) → reuse existing name
   - If coordinates match a manhole (pre-seeded) → use manhole name/elevation/depth
5. For each segment `i` (0..N-2):
   - Compute length via `_haversine(coords[i], coords[i+1])`
   - Skip if length < 0.01 m (zero-length segment)
   - Create conduit feature: Name = `{prefix}{fid}_S{i}` (e.g., `CN42_S3`)
   - TRAPEZOIDAL cross-section: Geom1=depth, Geom2=width, Geom3=Geom4=slope

**Naming convention**:

| Element | Pattern | Example | Max length |
|---------|---------|---------|------------|
| Junction | `{prefix}J{fid}_{i}` | `CNJ42_3` | ~12 chars |
| Conduit | `{prefix}{fid}_S{i}` | `CN42_S3` | ~11 chars |

`fid` is 1-based row index (not CSV `ID` column, to avoid duplicates).

**Returns**: `(layer, auto_junction_entries)` where entries are 5-tuples.

### `create_canal_conduits(csv_path=None, coord_registry=None, congdap_index=None, weir_layer=None)`

Thin wrapper calling `_decompose_linestrings()` with canal parameters and optional congdap integration:

| Parameter | Value |
|-----------|-------|
| prefix | `"CN"` |
| xs_type | `"TRAPEZOIDAL"` |
| roughness | 0.025 (earthen channel) |
| default_width | 1.0 m |
| default_depth | 0.5 m |
| default_slope | 1.0 (45-degree side slope) |

When `congdap_index` is provided, matched congdap points are inserted as inline weirs, splitting canal conduit segments at the congdap location.

**Returns**: `(layer, auto_junctions, inline_weir_feats, inline_weir_aj)`.

### `create_river_conduits(csv_path=None, coord_registry=None)`

Thin wrapper with river parameters (no congdap integration):

| Parameter | Value |
|-----------|-------|
| prefix | `"RN"` |
| xs_type | `"TRAPEZOIDAL"` |
| roughness | 0.035 (natural channel) |
| default_width | 5.0 m |
| default_depth | 2.0 m |
| default_slope | 1.0 |

**Returns**: `(layer, auto_junctions, [], [])`.

---

## Congdap-Canal Integration

### Problem

Congdap hydraulic structures (weirs) physically sit on canal lines. Previously they were modeled as standalone SWMM weir links with independent junction pairs, disconnected from the canal network. Water flowed through canals but never interacted with the weirs.

### Solution: Spatial Snapping

The conversion module now spatially matches congdap points to canal segments and inserts weirs inline into the canal junction+conduit chain.

**Before (disconnected):**
```
Canal:    CNJ1_0 ----conduit(500m)----> CNJ1_1
Congdap:  CD17_up ---weir--- CD17_dn   (floating, disconnected)
```

**After (integrated — mid-segment):**
```
Canal:    CNJ1_0 --conduit(200m)--> CD17_up --weir(~1.4m)--> CD17_dn --conduit(300m)--> CNJ1_1
```

**After (integrated — vertex, congdap at canal vertex):**
```
Canal:    CNJ1_0 --conduit--> CNJ1_1 --weir(~1.4m)--> CD17_dn --conduit--> CNJ1_2
```

### Vertex Override Algorithm

When a congdap projects to a segment endpoint (fraction ≈ 0 or ≈ 1), the upstream junction `CD_up` would be coordinate-deduplicated with the existing canal vertex junction, creating a branch instead of inline weir. The vertex override algorithm handles this:

1. **Pre-processing**: Before the segment loop, scan all congdap matches for endpoint fractions (within 1% of 0.0 or 1.0)
2. **Vertex weir**: Insert the weir AT the existing vertex junction — `junc_names[vertex] → CD_dn` — without creating a separate `CD_up`
3. **Exit override**: Record `exit_override[vertex] = CD_dn` so the next segment starts from `CD_dn` instead of `junc_names[vertex]`, forcing flow through the weir
4. **Chaining**: Multiple congdap at the same vertex are chained: `junc → weir₁ → CD₁_dn → weir₂ → CD₂_dn → ...`

### `_point_to_segment_distance(px, py, ax, ay, bx, by)`

Static method. Computes distance from point P to line segment AB in metres using flat-earth approximation (cos(lat) scaling). Returns `(distance_m, proj_lon, proj_lat, fraction)` where fraction is 0.0-1.0 position along the segment.

### `_build_congdap_spatial_index(congdap_csv, canal_csv, snap_tolerance_m=10.0)`

Matches congdap points to nearest canal segments within `snap_tolerance_m` (default 10m). Uses bounding-box pre-filter per segment to avoid brute-force distance computation.

**Returns**: `(congdap_index, matched_ids, unmatched_rows)` where:
- `congdap_index`: `{(canal_fid, seg_idx): [matches sorted by fraction]}` — each match contains `congdap_row`, `proj_lon`, `proj_lat`, `fraction`
- `matched_ids`: set of matched congdap ID strings
- `unmatched_rows`: list of unmatched congdap CSV rows (become standalone weirs)

### `_build_weir_feature(layer, row, from_node, to_node, lon, lat)`

Creates a single SWMM WEIRS QgsFeature from a congdap CSV row. Shared by both inline weir creation (during canal decomposition) and standalone weir creation.

### `create_weirs(csv_path=None, exclude_ids=None)`

Creates standalone weirs for congdap not matched to any canal. When `exclude_ids` is provided, skips congdap already integrated inline.

### Match & Connectivity Statistics (Sample Region)

| Category | Count | % |
|----------|-------|---|
| Matched (inline) | 63 | 79% |
|   — vertex override (fraction ≈ 0/1) | 49 | 61% |
|   — mid-segment (fraction 0.01–0.99) | 14 | 18% |
| Unmatched (standalone) | 17 | 21% |
| **Total** | **80** | **100%** |

| Connectivity | Count |
|--------------|-------|
| Both sides connected (inline) | 62 |
| Dead-end at canal endpoint | 1 |
| Standalone (no canal connection) | 17 |

---

## DEM Elevation Refinement

### `_load_dem()` / `_sample_dem(lon, lat)`

When `dem_path` is provided to `Conversion.__init__()`, the DEM raster (GeoTIFF, EPSG:4326) is opened via GDAL and cached for point sampling. `_sample_dem()` converts (lon, lat) to pixel coordinates and returns the ground-surface elevation in metres. Returns `None` for out-of-bounds or no-data pixels.

### `_refine_elevations(junctions_layer, storage_layer, outfalls_layer)`

Post-processing step called after all node layers are populated. For each node:

- **JUNCTIONS / STORAGE**: `Elevation = DEM_surface - MaxDepth`
- **OUTFALLS**: `Elevation = DEM_surface`

Skips nodes where DEM returns no-data.

### DEM Source

All regional scripts use `dataset/dia_hinh_khong_gian/dem/dem_compress.tif` (EPSG:4326, ~123m resolution, 7200x14400 pixels). The sample region uses a cropped 64x64 subset.

---

## MaxDepth Determination

Junction `MaxDepth` (maximum water depth at a node) is determined from CSV data before DEM refinement:

| Source | Initial Elevation | MaxDepth | After DEM Refinement |
|--------|-------------------|----------|---------------------|
| Manholes (`create_junctions`) | `InvElev_m` (default 5.0) | `RimElev_m - InvElev_m` | `DEM - MaxDepth` |
| Auto-junctions (pumps, orifices, weirs) | 0.0 | 3.0 (hardcoded) | `DEM - 3.0` |
| Canal junctions (decomposed) | `BedElev_m` (default 0.0) | `BankElev_m - BedElev_m`, or 0.5 | `DEM - MaxDepth` |
| River junctions (decomposed) | `BedElev_m` (default 0.0) | `BankElev_m - BedElev_m`, or 2.0 | `DEM - MaxDepth` |

SWMM auto-adjusts MaxDepth upward when a connected conduit's Geom1 (depth) exceeds the junction's MaxDepth, producing WARNING 02 messages. This is expected behavior with default values.

---

## Auto-Junction Merge

### `_add_auto_junctions(junctions_layer, auto_junction_entries)`

Merges auto-generated junction nodes into the main JUNCTIONS layer. Deduplicates by junction **name** (not coordinates — coordinate dedup happens earlier in `_get_or_create_junction`).

**Input**: List of `(name, lon, lat, elevation, max_depth)` tuples from:
- `create_pumps()` — 2 per pump
- `create_orifices()` — 2 per orifice
- `create_weirs()` — 2 per standalone weir
- `_decompose_linestrings()` — 1 per LineString coordinate point + 2 per inline weir

Skips any name already present in the junctions layer (from `create_junctions()`).

---

## Options Table

### `create_options_table(out_path=None)`

Generates an Excel `.xlsx` file with SWMM simulation parameters. The plugin reads this file and writes the `[OPTIONS]` section.

**Key simulation settings**:

| Option | Value | Description |
|--------|-------|-------------|
| FLOW_UNITS | CMS | Cubic meters per second |
| FLOW_ROUTING | DYNWAVE | Full dynamic wave routing |
| INFILTRATION | MODIFIED_GREEN_AMPT | Infiltration method |
| ALLOW_PONDING | YES | Allow surface ponding at nodes |
| ROUTING_STEP | 30 | Routing time step (seconds) |
| START_DATE / END_DATE | 01/01/2025 - 01/02/2025 | 1-day simulation |
| REPORT_STEP | 00:05:00 | Report every 5 minutes |

---

## Main Orchestration: `run()`

The `run(inp_file=None)` method executes the full conversion pipeline:

```
1.  Load DEM raster (if dem_path provided)
2.  Build manhole index → pre-seed coord_registry
3.  Create node layers:
    a. JUNCTIONS (from manholes CSV)
    b. STORAGE (from lakes CSV)
4.  Create link layers:
    a. CONDUITS (from sewers CSV)
    b. PUMPS → collect auto-junctions
    c. OUTLETS → collect auto-junctions
    d. ORIFICES → collect auto-junctions
5.  Build congdap spatial index (match congdap to canal segments)
6.  Create empty WEIRS layer
7.  Decompose canals WITH congdap integration:
    a. Canal conduit segments + junctions (merged into CONDUITS)
    b. Inline weir features (added to WEIRS layer)
8.  Create standalone WEIRS (unmatched congdap only, merged into WEIRS)
9.  Decompose rivers → conduit segments + junctions (merged into CONDUITS)
10. Merge all auto-junctions into JUNCTIONS layer
11. Create OUTFALLS
12. Refine node elevations from DEM:
    JUNCTIONS/STORAGE: Elevation = DEM_surface - MaxDepth
    OUTFALLS: Elevation = DEM_surface
13. Create hydrology layers:
    a. RAINGAGES (from raingages CSV)
    b. SUBCATCHMENTS (from subcatchments CSV)
14. Generate tables:
    a. OPTIONS table (.xlsx)
    b. TIMESERIES table (.xlsx)
15. Add all layers to QgsProject
16. Run "GenSwmmInp:GenerateSwmmInpFile" processing algorithm
17. Output .inp file
```

**Plugin invocation**:

```python
processing.run("GenSwmmInp:GenerateSwmmInpFile", {
    "QGIS_OUT_INP_FILE": inp_file,
    "FILE_JUNCTIONS": junctions_layer,
    "FILE_OUTFALLS": outfalls_layer,
    "FILE_STORAGES": storage_layer,
    "FILE_CONDUITS": conduits_layer,
    "FILE_PUMPS": pumps_layer,
    "FILE_OUTLETS": conv._line_layer("outlets", []),
    "FILE_ORIFICES": orifices_layer,
    "FILE_WEIRS": weirs_layer,
    "FILE_RAINGAGES": raingages_layer,
    "FILE_SUBCATCHMENTS": subcatchments_layer,
    "FILE_OPTIONS": options_path,
    "FILE_TIMESERIES": timeseries_path,
    "USE_Z_VALS": False,
})
```

All layer parameters are optional in the plugin. Passing `None` or an empty layer results in the corresponding `.inp` section being omitted.

---

## Regional Scripts

### `src/conversion/conversion_hanoi.py`

**Bounding box**: `(105.285258, 20.563299, 106.021553, 21.386961)` — derived from `Ha Noi_DEM.tif` (EPSG:32648 → WGS84).

**Outfall**: `OF01` at `(105.851, 21.022)`, elevation 4.0 m, type `FREE`.

Processes all 9 datasets but only includes features within the Hanoi DEM extent.

### `src/conversion/conversion_hcm.py`

**Bounding box**: `(106.364036, 10.382483, 106.977959, 11.158576)` — combined extent of `canals.csv` + `weir.csv`.

**Outfall**: `OF_HCM` at `(106.700, 10.730)`, elevation 0.0 m, type `FREE`.

Processes all 9 datasets but only includes features within the HCM extent.

### `src/conversion/conversion_sample.py`

**Dataset**: `sample_region/` (pre-cropped datasets, same folder structure as `dataset/`)
**Bounding box**: `(106.46, 11.09, 106.53, 11.16)` — small HCM sub-area (Củ Chi district).

No bbox filter needed — data is already cropped by `crop_sample_region.py`. Includes raingages, subcatchments, timeseries, and outfalls. Result: `sample_region.inp` — 2,454 nodes + 2,334 conduits + 80 weirs + 2 outfalls (601 KB), ~16s simulation.

All regional scripts follow the same orchestration logic as `run()` but are standalone (handle their own QGIS init and plugin registration).

---

## Component Summary

### CSV → SWMM Section Mapping

| Source CSV | SWMM Section | Geometry | Creator Method |
|------------|-------------|----------|----------------|
| manholes.csv | [JUNCTIONS] | Point | `create_junctions()` |
| lakes.csv | [STORAGE] | Point | `create_storage()` |
| outfalls.csv | [OUTFALLS] | Point | `create_outfalls()` |
| sewers.csv | [CONDUITS] + [XSECTIONS] | LineString | `create_conduits()` |
| canals.csv | [CONDUITS] + [XSECTIONS] | LineString (decomposed) | `create_canal_conduits()` |
| rivers.csv | [CONDUITS] + [XSECTIONS] | LineString (decomposed) | `create_river_conduits()` |
| pumps.csv | [PUMPS] | Point → LineString | `create_pumps()` |
| orifices.csv | [ORIFICES] | Point → LineString | `create_orifices()` |
| weir.csv | [WEIRS] | Point → LineString | `create_weirs()` |
| raingages.csv | [RAINGAGES] | Point | `create_raingages()` |
| subcatchments.csv | [SUBCATCHMENTS] + [SUBAREAS] + [INFILTRATION] | Polygon | `create_subcatchments(coord_registry=)` |
| (generated) | [TIMESERIES] | — (table) | `create_timeseries_table()` |

### Model Scale (Full, No BBox Filter)

| Component | Features | SWMM Section |
|-----------|----------|-------------|
| Manholes | 12 | JUNCTIONS |
| Auto-junctions | ~186,920 | JUNCTIONS |
| Lakes | 5 | STORAGE |
| Outfalls | 4 | OUTFALLS |
| Sewer conduits | 12 | CONDUITS |
| Canal segments | 82,457 | CONDUITS |
| River segments | 107,650 | CONDUITS |
| Pumps | 23 | PUMPS |
| Outlets | 43 | OUTLETS |
| Orifices | 6 | ORIFICES |
| Weirs | 3,707 | WEIRS |
| **Total nodes** | **~186,938** | |
| **Total links** | **~193,898** | |

### Data Quality Notes

- **Canals**: 61% have `Width_m`, 35% have `BedElev_m`, `XSType` blank for all → defaults used
- **Rivers**: 0% have dimension data → all default values (width=5m, depth=2m)
- **131 zero-length canal segments** filtered out (< 0.01 m)
- **Vietnamese number format** in canal CSV requires `_safe_float()` handling

---

## Known Issues & Warnings

1. **WARNING 02** (MaxDepth increased): SWMM auto-adjusts junction MaxDepth when connected conduit depth exceeds it. Expected with default values.

2. **WARNING 04** (minimum elevation drop): All canal/river junctions default to elevation 0.0 (no DEM lookup), so conduits have zero slope. SWMM applies minimum elevation drop automatically.

3. **OUTLETS RateCurve**: Must use `"FUNCTIONAL/DEPTH"` not `"FUNCTIONAL"`. The plugin's `get_outl_curve()` checks this exact string. Using `"FUNCTIONAL"` alone causes SWMM access violation.

4. **Point-based links**: Pumps, orifices, and weirs are stored as Point geometries but SWMM models them as links. The conversion creates a ~5m synthetic LineString via `_link_from_point()` and auto-generates FromNode/ToNode junction pairs.

5. **No DEM elevation lookup**: Junction elevations come from CSV data only. Canal/river junctions without `BedElev_m` data default to 0.0 m.
