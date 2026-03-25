# Standardization Module

The `standardize.py` module converts standardized CSV datasets into ESRI Shapefiles (EPSG:4326). Each conversion method takes `csv_path` and `out_dir` as arguments — no dataset paths are hardcoded.

## Dependencies

- `csv` - CSV file parsing
- `json` - JSON parsing for GeoJSON geometries
- `os` - File system operations
- `sys` - Command-line argument handling
- `osgeo.ogr` - GDAL/OGR library for geospatial vector data
- `osgeo.osr` - GDAL/OGR spatial reference system handling

---

## Helper Functions

### `_make_shapefile`
Creates a new ESRI Shapefile with the specified geometry type, coordinate reference system, and attribute fields. Returns the data source and layer objects for writing features.

### `_write_cpg`
Writes a `.cpg` codepage file to specify UTF-8 encoding for the shapefile's attribute data.

### `_report`
Prints a summary report after shapefile creation, including the number of features processed, skipped records, and file sizes for all shapefile components.

### `_set_fields`
Populates attribute fields on a feature from a CSV row, handling type conversion for integer, real, and string field types.

### `_parse_geojson_point`
Extracts longitude and latitude coordinates from a GeoJSON Point geometry string.

### `_parse_geojson_geometry`
Parses a GeoJSON geometry string (Point, LineString, Polygon, etc.) and returns an OGR Geometry object. Used for non-point geometries such as canal polylines.

### `_detect_encoding`
Attempts to detect the character encoding of a file by testing common encodings (UTF-8, Latin-1, Windows codepages).

### `_convert_point`
Generic converter: reads a standardized CSV with a GeoJSON Point column and produces a Point shapefile. Parameters: `csv_path`, `out_dir`, `name`, `fields`, `geom_col` (default `"Shape"`).

### `_convert_line`
Generic converter: reads a standardized CSV with a GeoJSON LineString column and produces a LineString shapefile. Parameters: `csv_path`, `out_dir`, `name`, `fields`, `geom_col` (default `"RouteShape"`).

---

## Classes

### `RiverLakeCanalNetwork`

Handles data group 2: River, Lake, and Canal Network datasets.

| Method | Geometry | Description |
|--------|----------|-------------|
| `convert_rivers(csv_path, out_dir)` | LineString | River network (2,013 features) |
| `convert_canals(csv_path, out_dir)` | LineString | Canal/ditch network (2,271 features) |
| `convert_lakes(csv_path, out_dir)` | Point | Lakes and detention ponds |
| `convert_congdap(csv_path, out_dir)` | Point | Hydraulic structures (3,707 features) |
| `convert_mekong_dams(csv_path, out_dir)` | Point | Mekong dam database (1,055 features) |

### `UrbanDrainageSystem`

Handles data group 3: Urban Drainage System datasets.

| Method | Geometry | Description |
|--------|----------|-------------|
| `convert_sewers(csv_path, out_dir)` | LineString | Sewer conduits |
| `convert_manholes(csv_path, out_dir)` | Point | Manholes / junctions |
| `convert_pumps(csv_path, out_dir)` | Point | Pumping stations |
| `convert_outlets(csv_path, out_dir)` | Point | Outlets / outfalls |
| `convert_orifices(csv_path, out_dir)` | Point | Orifices / tidal control gates |

### `PollutionSources`

Handles data group 5: Pollution Sources (for water quality modeling).

| Method | Geometry | Description |
|--------|----------|-------------|
| `convert_discharge_2022(csv_path, out_dir)` | Point | Discharge locations 2022 (21 features) |
| `convert_discharge_2023(csv_path, out_dir)` | Point | Discharge locations 2023 (29 features) |

---

## Command-Line Interface

The module requires `--base-dir` to specify the dataset root directory:

| Command | Description |
|---------|-------------|
| `python standardize.py --base-dir <path>` | Run all conversions |
| `python standardize.py --base-dir <path> --type 2` | Convert only River/Lake/Canal Network |
| `python standardize.py --base-dir <path> --type 3` | Convert only Urban Drainage System |
| `python standardize.py --base-dir <path> --type 5` | Convert only Pollution Sources |

---

## Standardized CSV Dataset Schema

All standardized CSVs are created by `migrate_all.py` from raw datasets. They follow a unified schema per component, using English field names (max 10 characters for shapefile DBF compatibility).

**Conventions:**
- All shapefiles use **EPSG:4326 (WGS84)** as the standard CRS
- Field names are **English, max 10 characters** (shapefile DBF limitation)
- Each component has **Core fields** (essential for hydraulic modeling) and **Metadata fields** (administrative/tracking)
- Fields marked with `*` are required; others are optional

**Data sources used:**
- `dataset.rst` - data structure requirements
- `rawdata.csv` - potential customer raw data fields (HCMC drainage management system)
- Existing datasets: river shapefile, canal CSV, CONGDAP CSV, drainage CSVs, pollution CSVs, Mekong dam CSVs

### Common Metadata Fields (shared by all components)

| Field Name | Type | Width | Description | Source mapping |
|------------|------|-------|-------------|----------------|
| `ID` | Integer | 10 | Unique feature identifier | stt / stt_id / OBJECTID |
| `Name` | String | 150 | Feature name | TenCongDap / TenKenhMuong / Name1 etc. |
| `Location` | String | 150 | Address / place description | DiaDiem / DiaChi |
| `Province` | String | 50 | Province/City | Tinh/Thanh pho |
| `District` | String | 50 | District | Quan/Huyen |
| `Ward` | String | 50 | Ward/Commune | Phuong/Xa |
| `Manager` | String | 80 | Managing organization | DonViQuanLy / Ma don vi quan ly |
| `YearBuilt` | Integer | 5 | Year of construction/commissioning | NamSuDung |
| `YearUpdate` | Integer | 5 | Year data was last updated | NamCapNhat |
| `Status` | String | 30 | Operational status | Tinh trang hoat dong / Status |
| `Notes` | String | 254 | Remarks | GhiChu |

---

### Group 2: River, Lake, and Canal Network

#### 2.1 River

**Geometry:** LineString | **Source datasets:** `river/river.shp` (2,013 features)

| Field Name | Type | Width | Description | River SHP | rawdata.csv |
|------------|------|-------|-------------|-----------|-------------|
| `ID`* | Integer | 10 | Feature ID | OBJECTID | - |
| `Name` | String | 150 | River name | Name | Ten muong, song |
| `Code` | String | 20 | River/waterway code | Code | Ma muong/song |
| `Strahler`* | Integer | 5 | Stream order (Strahler) | Strahler | - |
| `Length_m`* | Real | 12 | Segment length (m) | Length | Chieu dai (m) |
| `Width_m` | Real | 10 | Average width (m) | - | Chieu rong trung binh (m) |
| `BedElev_m` | Real | 10 | Bed elevation (m) | - | - |
| `BankElev_m` | Real | 10 | Bank elevation (m) | - | - |
| `FlowDir` | String | 20 | Flow direction | - | Huong chay |
| `FromNode`* | String | 20 | Start node ID of the route | - | Diem bat dau |
| `ToNode`* | String | 20 | End node ID of the route | - | Diem ket thuc |
| `RouteShape` | String | 254 | Route path as GeoJSON LineString | - | - |
| `XSType` | String | 30 | Cross-section profile type (TRAPEZOIDAL, IRREGULAR, etc.) | - | - |
| `Material` | String | 40 | Lining material | - | Chat lieu |
| `Basin` | String | 80 | River basin name | - | - |
| `IrrigSys` | String | 120 | Irrigation system name | - | He thong thu gom |

#### 2.2 Canal / Ditch

**Geometry:** LineString | **Source datasets:** `HTQLTL_CTTL_KENHMUONG2023.csv` (2,280 features)

| Field Name | Type | Width | Description | Canal CSV | rawdata (Ranh) | rawdata (Muong) |
|------------|------|-------|-------------|-----------|-----------------|-----------------|
| `ID`* | Integer | 10 | Feature ID | stt_id | - | Ma muong/song |
| `Name`* | String | 150 | Canal/ditch name | TenKenhMuong | Ten ranh | Ten muong, song |
| `Type` | String | 30 | Canal/Ditch | - | Loai ranh | - |
| `Length_m`* | Real | 12 | Length (m) | ChieuDai | Chieu dai (m) | Chieu dai (m) |
| `Width_m` | Real | 10 | Width (m) | BeRongKenh | Kich thuoc (m) | Chieu rong trung binh (m) |
| `BedElev_m` | Real | 10 | Bed elevation (m) | CaoTrinhDayKenh | Cao do day ranh (m) | - |
| `LeftBank` | String | 30 | Left bank elevation | CaoTrinhBoTrai | - | - |
| `RightBank` | String | 30 | Right bank elevation | CaoTrinhBoPhai | - | - |
| `SlopCoef` | String | 20 | Side slope coefficient | HeSoMai | Do doc (%) | - |
| `Material` | String | 40 | Lining material/structure | KetCauCongTrinh | Chat lieu | Chat lieu |
| `Grade` | String | 10 | Infrastructure grade (I-IV) | CapCongTrinh | - | - |
| `Purpose` | String | 60 | Function (irrigation/drainage) | MucTieuNhiemVu | - | - |
| `SvcArea` | Real | 12 | Service area (ha) | DienTichPhucVu | - | - |
| `IrrigSys` | String | 120 | Parent irrigation system | HeThongCongTrinhThuyLoi | Ma he thong thu gom | Ma he thong thu gom |
| `FlowDir` | String | 20 | Flow direction | - | Huong tuyen thoat nuoc | Huong chay |
| `FromNode`* | String | 20 | Start node ID of the route | - | Diem bat dau | Diem bat dau |
| `ToNode`* | String | 20 | End node ID of the route | - | Diem ket thuc | Diem ket thuc |
| `RouteShape` | String | 254 | Route path as GeoJSON LineString | Shape | - | - |
| `XSType` | String | 30 | Cross-section profile type | - | - | Mat cat dien hinh |
| `WtrLevel` | Real | 10 | Design water level (m) | - | Cao do muc nuoc (m) | Cao do muc nuoc thiet ke (m) |
| `XSArea` | Real | 10 | Cross-section area (m2) | - | Tiet dien (m2) | - |

#### 2.3 Lake / Detention Pond

**Geometry:** Point (centroid) or Polygon (boundary) | **Source datasets:** `rawdata.csv` (Ho dieu hoa)

| Field Name | Type | Width | Description | rawdata (Ho dieu hoa) |
|------------|------|-------|-------------|----------------------|
| `ID`* | Integer | 10 | Feature ID | Ma ho dieu hoa |
| `Name`* | String | 150 | Lake/pond name | Ten ho dieu hoa |
| `Group` | String | 40 | Lake group classification | Nhom ho |
| `Area_ha`* | Real | 12 | Surface area (ha) | Dien tich ho ung voi dinh bo ke (ha) |
| `BedArea_ha` | Real | 12 | Bottom area (ha) | Dien tich day ho (ha) |
| `Vol_m3`* | Real | 15 | Storage volume (m3) | Dung tich ho ung voi dinh bo ke (m3) |
| `BedElev_m`* | Real | 10 | Bottom elevation (m) | Cao do day (m) |
| `CrestElv` | Real | 10 | Embankment crest elev (m) | Cao do dinh bo ke (m) |
| `BankElev_m` | Real | 10 | Grass bank elevation (m) | Cao do bo co (m) |
| `NatWtrLvl` | Real | 10 | Natural water level (m) | Cao do muc nuoc tu nhien (m) |
| `WetLvl_m` | Real | 10 | Wet season control level (m) | Muc nuoc khong che mua mua (m) |
| `DryLvl_m` | Real | 10 | Dry season control level (m) | Muc nuoc khong che mua kho (m) |
| `NumInlets` | Integer | 5 | Number of inlet/outlet structures | So luong cua cong ra vao ho |
| `Perim_m` | Real | 12 | Perimeter at crest (m) | Chu vi ung voi dinh bo ke (m) |
| `IrrigSys` | String | 120 | Parent drainage system | Ma he thong thu gom |

#### 2.4 Dam / Hydraulic Structure

**Geometry:** Point | **Source datasets:** `CONGDAP2023.csv` (3,707 features), `mekongdam_database.csv` (1,055 features)

| Field Name | Type | Width | Description | CONGDAP | Mekong DB |
|------------|------|-------|-------------|---------|-----------|
| `ID`* | Integer | 10 | Feature ID | stt | ID |
| `Name`* | String | 150 | Structure name | TenCongDap | Name1 |
| `Type` | String | 60 | Structure type | LoaiCongTrinh | - |
| `Form` | String | 60 | Structure form | HinhThuc | - |
| `Chainage` | String | 40 | Chainage/station | LyTrinh | - |
| `River` | String | 80 | River name | - | River |
| `Basin` | String | 80 | River basin | - | Basin |
| `Length_m` | Real | 10 | Structure length (m) | ChieuDai | Length_m |
| `Width_m` | Real | 10 | Structure width (m) | BeRong | - |
| `Height_m` | Real | 10 | Structure height (m) | ChieuCao | Height_m |
| `Diam_m` | Real | 10 | Diameter (m) | DuongKinh | - |
| `Openings` | Integer | 5 | Number of openings | SoCua | - |
| `InvElev_m`* | Real | 10 | Invert elevation (m) | CaoTrinhDayCong | - |
| `CrestElv` | Real | 10 | Crown/crest elevation (m) | CaoTrinhDinhCong | - |
| `Cap_MW` | Real | 12 | Power capacity (MW) | - | Capacity_MW |
| `Vol_Mm3` | Real | 12 | Reservoir volume (million m3) | - | Volume_milm3 |
| `Catch_km2` | Real | 12 | Catchment area (km2) | - | Catch_km2 |
| `Elev_m` | Real | 10 | Site elevation (m) | - | Elevation_m |
| `Grade` | String | 10 | Infrastructure grade | CapCongTrinh | - |
| `Operation` | String | 60 | Operation mode | HinhThucVanHanh | - |
| `Purpose` | String | 100 | Function/purpose | MucTieuNhiemVu | Use1 |
| `SvcArea` | Real | 12 | Service area (ha) | DienTichPhucVu_ha | Area_km2 |
| `IrrigSys` | String | 120 | Irrigation system | HeThongCongTrinhThuyLoi | - |
| `Country` | String | 40 | Country | - | Country |
| `Complete` | Integer | 5 | Completion year | - | Completion |

---

### Group 3: Urban Drainage System

#### 3.1 Sewer Network (Conduits)

**Geometry:** LineString | **Source datasets:** `rawdata.csv` (Cong thoat nuoc, Ranh thoat nuoc)

| Field Name | Type | Width | Description | rawdata (Cong thoat nuoc) |
|------------|------|-------|-------------|---------------------------|
| `ID`* | Integer | 10 | Feature ID | - |
| `Name`* | String | 150 | Sewer route name | Ten tuyen cong/ranh thoat nuoc |
| `Type` | String | 30 | Classification code | Ma phan loai |
| `Diam_mm`* | Real | 10 | Diameter (mm) for circular | Duong kinh (mm) |
| `Size_mm` | String | 30 | Dimensions (mm) for non-circular | Kich thuoc (mm) |
| `Length_m`* | Real | 12 | Length (m) | Chieu dai (m) |
| `Material` | String | 40 | Pipe material (concrete, PVC, etc.) | Chat lieu |
| `XSArea` | Real | 10 | Cross-section area (m2) | Tiet dien (m2) |
| `FlowDir` | String | 20 | Flow direction | Huong tuyen thoat nuoc |
| `FromNode`* | String | 20 | Upstream node ID (manhole/junction) | Diem bat dau |
| `ToNode`* | String | 20 | Downstream node ID (manhole/junction) | Diem ket thuc |
| `RouteShape` | String | 254 | Route path as GeoJSON LineString | - |
| `XSType` | String | 30 | Cross-section profile type (CIRCULAR, RECT_CLOSED, etc.) | Hinh dang |
| `StreetID` | String | 30 | Street number | So hieu duong |
| `DrainZone` | String | 30 | Drainage zone code | Ma vung thoat nuoc |
| `Catchment` | String | 30 | Catchment code | Ma luu vuc thoat nuoc |

#### 3.2 Manholes (Ho ga)

**Geometry:** Point | **Source datasets:** `rawdata.csv` (Ho ga)

| Field Name | Type | Width | Description | rawdata (Ho ga) |
|------------|------|-------|-------------|-----------------|
| `ID`* | Integer | 10 | Feature ID | - |
| `Name`* | String | 150 | Manhole name | Ten ho ga |
| `Type` | String | 30 | Manhole type | Ma phan loai ho ga |
| `Area_m2` | Real | 10 | Manhole area (m2) | Dien tich ho ga (m2) |
| `Size_m` | String | 30 | Manhole dimensions (m) | Kich thuoc ho ga (m) |
| `CoverType` | String | 40 | Cover type | Chung loai nap ho ga |
| `InvElev_m`* | Real | 10 | Invert elevation (m) | Cao do day ga (m) |
| `RimElev_m`* | Real | 10 | Rim/ground elevation (m) | Cao do mat duong (m) |
| `SewerLine` | String | 80 | Name of the connected sewer route | Ten tuyen thoat nuoc |
| `StreetID` | String | 30 | Street number | So hieu duong |
| `DrainZone` | String | 30 | Drainage zone code | Ma vung thoat nuoc |
| `Catchment` | String | 30 | Catchment code | Ma luu vuc thoat nuoc |

#### 3.3 Pumping Stations (Tram bom)

**Geometry:** Line (SWMM link) | **Source datasets:** `HTQLTL_CTTL_TRAMBOM2023.csv` (23 features)

| Field Name | Type | Width | Description | TRAMBOM CSV | rawdata |
|------------|------|-------|-------------|-------------|---------|
| `ID`* | Integer | 10 | Feature ID | stt_id | Ma tram |
| `Name`* | String | 150 | Station name | TenTramBom | Ten tram |
| `FromNode`* | String | 20 | Upstream node ID | - | - |
| `ToNode`* | String | 20 | Downstream node ID | - | - |
| `Position` | String | 80 | Location description | - | - |
| `Type` | String | 30 | Station type/classification | Loai | Ma phan loai |
| `Grade` | String | 10 | Station grade | - | Cap tram |
| `NumPumps` | Integer | 5 | Number of pumps | - | So luong bom |
| `Cap_m3s`* | String | 30 | Pump capacity (m3/s) | CongSuat | Cong suat bom (m3/s) |
| `InElev_m` | Real | 10 | Inlet elevation (m) | - | Cao do dau vao (m) |
| `OutElev_m` | Real | 10 | Outlet elevation (m) | - | Cao do dau ra (m) |
| `AutoMonit` | String | 10 | Auto water level monitoring? | - | Theo doi muc nuoc tu dong |
| `TrashScr` | String | 40 | Trash screen system | - | He thong cao rac/song chan rac |
| `Purpose` | String | 100 | Function/purpose | MucTieuNhiemVu | - |
| `SvcArea` | Real | 12 | Service area (ha) | DienTichPhucVu_ha | - |
| `IrrigSys` | String | 120 | Irrigation system | HeThongCongTrinhThuyLoi | Ma he thong thu gom |
| `StreetID` | String | 30 | Street number | - | So hieu duong |

#### 3.4 Outlets / Outfalls (Cua xa)

**Geometry:** Line (SWMM link) | **Source datasets:** `CONGDUOIDE2023.csv` (43 features)

| Field Name | Type | Width | Description | CONGDUOIDE CSV | rawdata (Cua xa) |
|------------|------|-------|-------------|----------------|------------------|
| `ID`* | Integer | 10 | Feature ID | stt_id | Ma cua xa |
| `Name`* | String | 150 | Outlet name | TenCongDap | Ten cua xa |
| `FromNode`* | String | 20 | Upstream node ID | - | - |
| `ToNode`* | String | 20 | Downstream/outfall node ID | - | - |
| `Position` | String | 80 | Location description | - | - |
| `Type` | String | 60 | Structure type | LoaiCongTrinh | Ma phan loai cua xa |
| `Form` | String | 60 | Structure form | HinhThuc | - |
| `Size_m` | String | 30 | Dimensions (m) | - | Kich thuoc (m) |
| `Length_m` | Real | 10 | Structure length (m) | ChieuDai | - |
| `Width_m` | Real | 10 | Width (m) | BeRong | - |
| `Height_m` | Real | 10 | Height (m) | ChieuCao | - |
| `Diam_m` | Real | 10 | Diameter (m) | DuongKinh | - |
| `Openings` | Integer | 5 | Number of openings | SoCua | - |
| `InvElev_m`* | Real | 10 | Invert elevation (m) | CaoTrinhDayCong | Cao do day cua xa (m) |
| `CrestElv` | Real | 10 | Crown elevation (m) | CaoTrinhDinhCong | - |
| `DesignWL` | Real | 10 | Design water level (m) | - | Cao do muc nuoc thiet ke (m) |
| `MaxCap_kW` | Real | 10 | Max capacity (kW) | - | Cong suat toi da (kW) |
| `FlapType` | String | 30 | Flap gate type | - | Loai cua phai |
| `Operation` | String | 60 | Operation mode | HinhThucVanHanh | - |
| `Purpose` | String | 100 | Function/purpose | MucTieuNhiemVu | - |
| `Receiver` | String | 80 | Receiving water body | - | Nguon tiep nhan |
| `Project` | String | 200 | Parent project | CumCongTrinh | - |

#### 3.5 Orifices / Control Gates (Cong kiem soat trieu)

**Geometry:** Line (SWMM link) | **Source datasets:** `CONGKIEMSOATTRIEU2023.csv` (6 features)

| Field Name | Type | Width | Description | CONGKIEMSOATTRIEU CSV |
|------------|------|-------|-------------|----------------------|
| `ID`* | Integer | 10 | Feature ID | stt |
| `Name`* | String | 150 | Gate name | TenCongDap |
| `FromNode`* | String | 20 | Upstream node ID | - |
| `ToNode`* | String | 20 | Downstream node ID | - |
| `Position` | String | 80 | Location description | ViTri |
| `Type` | String | 60 | Structure type (SIDE/BOTTOM per SWMM) | LoaiCongTrinh |
| `Form` | String | 60 | Orifice shape (CIRCULAR/RECT_CLOSED) | HinhThuc |
| `Length_m` | Real | 10 | Length (m) | ChieuDai |
| `Width_m` | Real | 10 | Width (m) | BeRong |
| `Height_m` | Real | 10 | Height (m) | ChieuCao |
| `Openings`* | Integer | 5 | Number of openings | SoCua |
| `InvElev_m`* | Real | 10 | Invert elevation (m) | CaoTrinhDayCong |
| `CrestElv` | Real | 10 | Crown elevation (m) | CaoTrinhDinhCong |
| `DischCoef` | Real | 10 | Discharge coefficient | - |
| `ClearSpan` | String | 40 | Clear span dimensions | CC_KhauDo_m |
| `SillElev` | String | 20 | Sill elevation | CC_CaoTrinhNguong_m |
| `GateMtrl` | String | 60 | Gate material | CC_LoaiVatLieuCuaVan |
| `GateCtrl` | String | 60 | Gate control mechanism | CC_KieuDongMoCuaVan |
| `Purpose` | String | 200 | Function/purpose | MucTieuNhiemVu |
| `SvcArea` | Real | 12 | Service area (ha) | DienTichPhucVu_ha |
| `Grade` | String | 10 | Infrastructure grade | CapCongTrinh |

---

### Group 5: Pollution Sources

#### 5.1 Discharge / Pollution Source Locations

**Geometry:** Point | **Source datasets:** `VITRIXATHAI2022.csv` (21 features), `VITRIXATHAIVAOCTTL2023.csv` (29 features)

| Field Name | Type | Width | Description | 2022 CSV | 2023 CSV |
|------------|------|-------|-------------|----------|----------|
| `ID`* | Integer | 10 | Feature ID | stt | stt |
| `Name`* | String | 254 | Description/title | Title | Title |
| `Discharger` | String | 200 | Discharging entity | DonViXaThai | DonViXaThai |
| `Address` | String | 200 | Address | - | DiaChi |
| `Industry` | String | 100 | Industry sector | - | NganhNghe |
| `Receiver` | String | 150 | Receiving water body | - | NguonTiepNhan |
| `DischPt` | String | 200 | Discharge point description | - | ViTriXaThai |
| `IrrigSys` | String | 120 | Connected irrigation system | - | HTCTTL |
| `Treatment` | String | 200 | Wastewater treatment system | - | HTXLNT |
| `Permit` | String | 150 | Discharge permit reference | - | GPXT |
| `PermitOrg` | String | 100 | Permit-issuing authority | DonViCapGiayPhep | DonViCapPhep |
| `Standard` | String | 100 | Discharge quality standard | - | QuyChuanXT |
| `FlowRate` | String | 50 | Discharge flow rate | - | LLXT |
| `ExpiryDt` | String | 30 | Permit expiry date | - | NgayHetHan |
| `DischTerm` | String | 100 | Discharge period/term | - | ThoiHanXaThai |

---

## Component Summary

| Component | Geometry | SWMM Element | Group | Current Dataset | rawdata.csv |
|-----------|----------|--------------|-------|-----------------|-------------|
| River | LineString | Conduit (open channel) | 2 | river.shp (2,013) | Muong thoat nuoc |
| Canal/Ditch | LineString | Conduit (open channel) | 2 | KENHMUONG (2,280) | Ranh thoat nuoc |
| Lake/Pond | Point/Polygon | Storage Unit (node) | 2 | - | Ho dieu hoa |
| Dam/Structure | Point | Weir (link) | 2 | CONGDAP (3,707) + Mekong (1,055) | - |
| Sewer conduit | LineString | Conduit (closed) | 3 | - | Cong thoat nuoc |
| Manhole | Point | Junction (node) | 3 | - | Ho ga |
| Pumping station | Line | Pump (link) | 3 | TRAMBOM (23) | Tram bom thoat nuoc |
| Outlet/Outfall | Line | Outlet (link) | 3 | CONGDUOIDE (43) | Cua xa |
| Orifice/Gate | Line | Orifice (link) | 3 | CONGKIEMSOATTRIEU (6) | - |
| Pollution source | Point | - | 5 | VITRIXATHAI (21+29) | Nha may XLNT |

## Notes

1. **EPA SWMM topology:** SWMM models a drainage network as nodes (junctions, outfalls, storage units) connected by links (conduits, pumps, orifices, outlets, weirs). All link components (3.3-3.5, plus conduits) require `FromNode`/`ToNode` fields referencing node IDs. All route components (2.1, 2.2, 3.1) use `FromNode`/`ToNode` for network connectivity, `RouteShape` for the GeoJSON LineString path geometry, and `XSType` for cross-section profile type.

2. **Missing datasets:** Sewer conduits, manholes, lakes, and cross-sections have field definitions in `rawdata.csv` but no actual spatial data yet. The standardization module should have conversion methods ready for when data arrives.

3. **Field name truncation:** Shapefile DBF format limits field names to 10 characters. Longer names in this document are for readability; the actual shapefile field names in `standardize.py` use abbreviated versions (e.g. `InvElev_m` -> `InvertElev`, `CrownElev` -> `CrstElv_m`).

4. **Coordinate handling:** Current datasets provide coordinates in three ways:
   - `Lat`/`Lon` columns (Mekong DB) - already WGS84
   - `Shape` column with GeoJSON (HCMC datasets) - already WGS84
   - `ToaDoX`/`ToaDoY` columns (HCMC datasets) - VN2000/UTM, needs reprojection

5. **Encoding:** HCMC datasets use `latin-1` encoding; Mekong datasets use `utf-8-sig`. The `_detect_encoding()` helper handles this automatically.

6. **Cross-section data:** `rawdata.csv` includes a "Mat cat ngang" (cross-section) component. This is critical for hydraulic modeling but is not a standalone spatial feature - it should be linked to river/canal features via a foreign key relationship. Consider a separate shapefile or attribute linkage.
