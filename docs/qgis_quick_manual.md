# Working with Sample Region Datasets in QGIS Desktop

## Table of Contents

- [1. Open QGIS Desktop](#1-open-qgis-desktop)
- [2. Load Sample Region Shapefiles](#2-load-sample-region-shapefiles)
- [3. Add Satellite Basemap](#3-add-satellite-basemap)
- [4. Create New Drainage System (thoat_nuoc) Shapefiles](#4-create-new-drainage-system-thoat_nuoc-shapefiles)
  - [4a. Create Manholes (Point layer)](#4a-create-manholes-point-layer)
  - [4b. Create Sewers (LineString layer)](#4b-create-sewers-linestring-layer)
  - [4c. Create Pumps (Point layer)](#4c-create-pumps-point-layer)
  - [4d. Create Lakes / Detention Ponds (Point layer)](#4d-create-lakes--detention-ponds-point-layer)
  - [4e. Create Orifices / Control Gates (Point layer)](#4e-create-orifices--control-gates-point-layer)
- [5. Edit Existing Features](#5-edit-existing-features)
  - [5a. Start Editing](#5a-start-editing)
  - [5b. Move a Point Feature](#5b-move-a-point-feature)
  - [5c. Move a Line/Polygon Feature](#5c-move-a-linepolygon-feature)
  - [5d. Reshape a Line](#5d-reshape-a-line-change-vertex-positions)
  - [5e. Connect a Line Endpoint to Another Line](#5e-connect-a-line-endpoint-to-another-line)
  - [5f. Edit Attributes](#5f-edit-attributes)
  - [5g. Delete Features](#5g-delete-features)
  - [5h. Add New Features to Existing Layer](#5h-add-new-features-to-existing-layer)
  - [5i. Undo/Redo](#5i-undoredo)
- [6. Save Edits](#6-save-edits)
- [7. Reverse-Convert Shapefiles to Standardized CSV](#7-reverse-convert-shapefiles-to-standardized-csv)
- [Tips](#tips)

---

## 1. Open QGIS Desktop

Launch QGIS 3.44.8 from `C:\Users\Public\Desktop\QGIS 3.44.8`.

## 2. Load Sample Region Shapefiles

Shapefiles are pre-generated in `sample_region_qgis/` by running:

```bash
conda run -n qgis-env python src/tools/csv_to_shp.py
```

To load them in QGIS:

1. **Layer > Add Layer > Add Vector Layer** (`Ctrl+Shift+V`)
2. Browse to `sample_region_qgis/`, select the `.shp` files you need
3. Repeat for each component (canals, rivers, weirs, pumps, raingages, subcatchments)

## 3. Add Satellite Basemap

1. **Plugins > Manage and Install Plugins** > search "QuickMapServices" > Install
2. **Web > QuickMapServices > Settings** > "More services" tab > "Get contributed pack"
3. **Web > QuickMapServices > Google > Google Satellite**

## 4. Create New Drainage System (thoat_nuoc) Shapefiles

### 4a. Create Manholes (Point layer)

1. **Layer > Create Layer > New Shapefile Layer**
2. Settings:
   - File name: `sample_region_qgis/thoat_nuoc/manholes/manholes.shp`
   - Geometry type: **Point**
   - CRS: **EPSG:4326 (WGS84)**
3. Add fields (click "Add to Fields List" for each):

| Name       | Type                             |
|------------|----------------------------------|
| Name       | Text (length 100)                |
| InvElev_m  | Decimal (length 10, precision 2) |
| RimElev_m  | Decimal (length 10, precision 2) |
| MaxDepth_m | Decimal (length 10, precision 2) |
| SewerLine  | Text (length 100)                |

4. Click **OK** to create the empty layer
5. Click the **Toggle Editing** button (pencil icon) on the toolbar
6. Click **Add Point Feature** (the point+star icon)
7. Click on the map where you want each manhole — a dialog will pop up for attributes
8. When done, click **Toggle Editing** again and **Save**

### 4b. Create Sewers (LineString layer)

1. **Layer > Create Layer > New Shapefile Layer**
2. Settings:
   - File name: `sample_region_qgis/thoat_nuoc/sewers/sewers.shp`
   - Geometry type: **Line**
   - CRS: **EPSG:4326 (WGS84)**
3. Add fields:

| Name      | Type                             |
|-----------|----------------------------------|
| Name      | Text (length 100)                |
| FromNode  | Text (length 100)                |
| ToNode    | Text (length 100)                |
| Length_m  | Decimal (length 10, precision 2) |
| Width_m   | Decimal (length 10, precision 2) |
| Height_m  | Decimal (length 10, precision 2) |
| Material  | Text (length 50)                 |
| Roughness | Decimal (length 10, precision 4) |

4. Click **OK**, then **Toggle Editing**
5. Click **Add Line Feature** — click points along the sewer route, right-click to finish
6. Fill in attributes in the popup dialog
7. Save when done

### 4c. Create Pumps (Point layer)

Pumps are converted to SWMM **Pump** links. The standardized CSV uses Point geometry; the conversion module auto-generates `FromNode`/`ToNode` junctions.

1. **Layer > Create Layer > New Shapefile Layer**
2. Settings:
   - File name: `sample_region_qgis/thoat_nuoc/pumps/pumps.shp`
   - Geometry type: **Point**
   - CRS: **EPSG:4326 (WGS84)**
3. Add fields:

| Name      | Type                             | Description                              |
|-----------|----------------------------------|------------------------------------------|
| Name      | Text (length 150)                | Station name                             |
| Source     | Text (length 80)                 | Source node supplying water to pump       |
| SewerLine  | Text (length 80)                 | Sewer route the pump supplies water to   |
| Type      | Text (length 30)                 | Station type/classification              |
| Grade     | Text (length 10)                 | Station grade                            |
| NumPumps  | Whole number (length 5)          | Number of pumps                          |
| Cap_m3s   | Text (length 30)                 | Pump capacity (m3/s)                     |
| InElev_m  | Decimal (length 10, precision 2) | Inlet elevation (m)                      |
| OutElev_m | Decimal (length 10, precision 2) | Outlet elevation (m)                     |
| Purpose   | Text (length 100)                | Function/purpose                         |
| SvcArea   | Decimal (length 12, precision 2) | Service area (ha)                        |

4. Click **OK**, then **Toggle Editing**
5. Click **Add Point Feature** — place the point at the pump station location
6. Fill in attributes (at minimum: Name, Cap_m3s)
7. Save (`Ctrl+S`)

### 4d. Create Lakes / Detention Ponds (Point layer)

Lakes are converted to SWMM **Storage Units** (nodes that store water volume).

1. **Layer > Create Layer > New Shapefile Layer**
2. Settings:
   - File name: `sample_region_qgis/mang_luoi_song_ho_kenh_muong/lakes/lakes.shp`
   - Geometry type: **Point**
   - CRS: **EPSG:4326 (WGS84)**
3. Add fields:

| Name       | Type                             | Description                      |
|------------|----------------------------------|----------------------------------|
| Name       | Text (length 150)                | Lake/pond name                   |
| Group      | Text (length 40)                 | Lake group classification        |
| Area_ha    | Decimal (length 12, precision 2) | Surface area (ha)                |
| BedArea_ha | Decimal (length 12, precision 2) | Bottom area (ha)                 |
| Vol_m3     | Decimal (length 15, precision 2) | Storage volume (m3)              |
| BedElev_m  | Decimal (length 10, precision 2) | Bottom elevation (m)             |
| CrestElv   | Decimal (length 10, precision 2) | Embankment crest elevation (m)   |
| BankElev_m | Decimal (length 10, precision 2) | Bank elevation (m)               |
| NatWtrLvl  | Decimal (length 10, precision 2) | Natural water level (m)          |
| WetLvl_m   | Decimal (length 10, precision 2) | Wet season control level (m)     |
| DryLvl_m   | Decimal (length 10, precision 2) | Dry season control level (m)     |
| NumInlets  | Whole number (length 5)          | Number of inlet/outlet structures|
| Perim_m    | Decimal (length 12, precision 2) | Perimeter at crest (m)           |

4. Click **OK**, then **Toggle Editing**
5. Click **Add Point Feature** — place the point at the lake centroid on the satellite basemap
6. Fill in attributes (at minimum: Name, Area_ha, Vol_m3, BedElev_m)
7. Save (`Ctrl+S`)

**Tip:** After creating lakes, run `shp_to_csv.py` to convert back to CSV. The conversion module will convert lakes to SWMM Storage Units with tabular depth-area curves.

### 4e. Create Orifices / Control Gates (Point layer)

Orifices are converted to SWMM **Orifice** links (flow control structures). The standardized CSV uses Point geometry; the conversion module auto-generates `FromNode`/`ToNode` junctions.

1. **Layer > Create Layer > New Shapefile Layer**
2. Settings:
   - File name: `sample_region_qgis/thoat_nuoc/orifices/orifices.shp`
   - Geometry type: **Point**
   - CRS: **EPSG:4326 (WGS84)**
3. Add fields:

| Name      | Type                             | Description                              |
|-----------|----------------------------------|------------------------------------------|
| Name      | Text (length 150)                | Gate name                                |
| Type      | Text (length 60)                 | Structure type (SIDE / BOTTOM)           |
| Form      | Text (length 60)                 | Shape (CIRCULAR / RECT_CLOSED)           |
| Length_m   | Decimal (length 10, precision 2) | Length (m)                               |
| Width_m    | Decimal (length 10, precision 2) | Width (m)                                |
| Height_m   | Decimal (length 10, precision 2) | Height (m)                               |
| Openings   | Whole number (length 5)          | Number of openings                       |
| InvElev_m  | Decimal (length 10, precision 2) | Invert elevation (m)                     |
| CrestElv   | Decimal (length 10, precision 2) | Crown elevation (m)                      |
| DischCoef  | Decimal (length 10, precision 4) | Discharge coefficient                    |
| Purpose    | Text (length 200)                | Function/purpose                         |
| Receiver   | Text (length 80)                 | Receiving water body                     |
| SvcArea    | Decimal (length 12, precision 2) | Service area (ha)                        |

4. Click **OK**, then **Toggle Editing**
5. Click **Add Point Feature** — place the point at the gate location on the satellite basemap
6. Fill in attributes (at minimum: Name, Type, Form, Height_m, InvElev_m)
7. Save (`Ctrl+S`)

## 5. Edit Existing Features

### 5a. Start Editing

1. Select a layer in the Layers panel
2. Click **Toggle Editing** (pencil icon on toolbar)

### 5b. Move a Point Feature

1. Enable editing (pencil icon)
2. Click the **"Move Feature(s)"** tool (icon with 4 arrows) in the Advanced Digitizing toolbar
   - If toolbar not visible: **View > Toolbars > Advanced Digitizing Toolbar**
3. Click on the point you want to move, then click the new location
4. Save (`Ctrl+S` or click the save icon)

### 5c. Move a Line/Polygon Feature

Same as moving a point — use **"Move Feature(s)"** tool.

### 5d. Reshape a Line (change vertex positions)

1. Enable editing (pencil icon)
2. Click the **"Vertex Tool"** (icon with a node/dot and arrows) or press `V`
3. Click on the line — red dots appear at each vertex
4. Drag any vertex to a new position
5. To add a vertex: hover on a line segment, a "+" marker appears — click to add
6. To delete a vertex: click on it, then press `Delete`
7. Save (`Ctrl+S`)

### 5e. Connect a Line Endpoint to Another Line

1. Enable **Snapping**: **Project > Snapping Settings** > enable for All Layers, type = Vertex, tolerance ~10px
2. Add a vertex on the target line at the connection point:
   - Select the target line's layer, enable editing
   - Press `V` (Vertex Tool), hover on the target line where you want the connection — click the "+" to add a vertex
   - Save (`Ctrl+S`)
3. Snap the endpoint of the other line to that vertex:
   - Select the other line's layer, enable editing
   - Press `V` (Vertex Tool), drag the endpoint — it will snap (pink/magenta square indicator)
   - Save (`Ctrl+S`)

### 5f. Edit Attributes

1. Enable editing (pencil icon)
2. Open Attribute Table: right-click layer > **Open Attribute Table** (or press `F6`)
3. Click on a cell to edit its value
4. Or: use the **"Identify Features"** tool (click on map feature) > edit values in the panel
5. Save (`Ctrl+S`)

### 5g. Delete Features

1. Enable editing (pencil icon)
2. Use **"Select Features by area or single click"** tool (or press `S`)
3. Click on the feature(s) to select (hold `Shift` for multiple)
4. Press `Delete` key
5. Save (`Ctrl+S`)

### 5h. Add New Features to Existing Layer

1. Enable editing (pencil icon)
2. For Point layers: click **"Add Point Feature"** tool, then click on map
3. For Line layers: click **"Add Line Feature"** tool, click points along the line, right-click to finish
4. Fill in attributes in the popup dialog
5. Save (`Ctrl+S`)

### 5i. Undo/Redo

- `Ctrl+Z` to undo last edit
- `Ctrl+Shift+Z` to redo (or `Ctrl+Y`)

## 6. Save Edits

Saving the **QGIS project** (`.qgs`/`.qgz`) only saves layer styling and layout — **not the data**.

To save edits to each Shapefile layer:

1. Select the layer in the Layers panel
2. Make sure editing mode is active (pencil icon)
3. Press `Ctrl+S` — this saves edits **back to the original .shp file**
4. Or: click the **Save Layer Edits** icon (floppy disk with pencil) in the Digitizing toolbar

## 7. Reverse-Convert Shapefiles to Standardized CSV

After editing in QGIS, run:

```bash
conda run -n qgis-env python src/tools/shp_to_csv.py
```

This converts all Shapefiles in `sample_region_qgis/` back to standardized CSVs in `sample_region/`, preserving full column names and GeoJSON geometry columns.

## Tips

- **Snapping**: **Project > Snapping Settings** (or press `S`) — enable so sewer endpoints snap to manhole points. Set tolerance to ~5 meters.
- **Labels**: Right-click layer > Properties > Labels > "Single Labels" > select Name field
- **Digitizing toolbar**: **View > Toolbars > Digitizing Toolbar** (if not visible)
- **Advanced Digitizing toolbar**: **View > Toolbars > Advanced Digitizing Toolbar** (for Move Feature, Vertex Tool, etc.)
- **Sketching**: Hold `Shift` while drawing lines for straight horizontal/vertical segments
