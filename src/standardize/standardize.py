"""
Standardize datasets to Shapefiles, organised by data type.

All conversions read from standardized CSVs (created by migrate_all.py)
and produce ESRI Shapefiles with EPSG:4326 (WGS84).

Data types (from docs/dataset.rst):
  2. River, Lake, and Canal Network  -> RiverLakeCanalNetwork
  3. Urban Drainage System           -> UrbanDrainageSystem
  5. Pollution Sources               -> PollutionSources

Usage:
  python standardize.py --base-dir g:/workspace/github/swmm/dataset
  python standardize.py --base-dir ... --type 2     # only River/Lake/Canal
  python standardize.py --base-dir ... --type 3     # only Urban Drainage
  python standardize.py --base-dir ... --type 5     # only Pollution Sources
"""
import csv, json, os, sys
from osgeo import ogr, osr

ogr.UseExceptions()


# ══════════════════════════════════════════════════════════════════════════════
# Shared helpers
# ══════════════════════════════════════════════════════════════════════════════

def _make_shapefile(out_dir, name, geom_type, srs_epsg, fields):
    """Create a new shapefile and return (datasource, layer)."""
    os.makedirs(out_dir, exist_ok=True)
    shp_path = os.path.join(out_dir, name + ".shp")

    drv = ogr.GetDriverByName("ESRI Shapefile")
    if os.path.exists(shp_path):
        drv.DeleteDataSource(shp_path)

    ds = drv.CreateDataSource(out_dir)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(srs_epsg)
    layer = ds.CreateLayer(name, srs, geom_type)

    for fdef in fields:
        shp_name, ftype, width = fdef[0], fdef[1], fdef[2]
        precision = fdef[3] if len(fdef) > 3 else (4 if ftype == ogr.OFTReal else 0)
        fd = ogr.FieldDefn(shp_name, ftype)
        fd.SetWidth(width)
        fd.SetPrecision(precision)
        layer.CreateField(fd)

    return ds, layer


def _write_cpg(out_dir, name):
    with open(os.path.join(out_dir, name + ".cpg"), "w") as f:
        f.write("UTF-8")


def _report(shp_path, name, out_dir, n_ok, n_skip):
    print(f"  Created: {shp_path}")
    print(f"  Features: {n_ok}  |  Skipped: {n_skip}")
    for ext in [".shp", ".shx", ".dbf", ".prj", ".cpg"]:
        p = os.path.join(out_dir, name + ext)
        sz = os.path.getsize(p) if os.path.exists(p) else 0
        print(f"    {name}{ext}  ({sz:,} bytes)")


def _set_fields(feat, row, fields):
    """Set attribute fields on a feature from a CSV row.

    fields: list of (csv_col, shp_name, ogr_type, width)
    """
    for csv_col, shp_name, ftype, *_ in fields:
        val = row.get(csv_col, "").strip()
        if not val or val == "<Null>":
            continue
        try:
            if ftype == ogr.OFTInteger:
                feat.SetField(shp_name, int(float(val)))
            elif ftype == ogr.OFTReal:
                feat.SetField(shp_name, float(val))
            else:
                feat.SetField(shp_name, val)
        except (ValueError, TypeError):
            pass


def _parse_geojson_point(shape_str):
    """Extract (lon, lat) from a GeoJSON Shape string."""
    try:
        obj = json.loads(shape_str)
        coords = obj["coordinates"]
        return float(coords[0]), float(coords[1])
    except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError):
        return None


def _parse_geojson_geometry(shape_str):
    """Parse a GeoJSON Shape string and return an ogr.Geometry."""
    try:
        obj = json.loads(shape_str)
        return ogr.CreateGeometryFromJson(json.dumps(obj))
    except (json.JSONDecodeError, TypeError, RuntimeError):
        return None


def _detect_encoding(path):
    for enc in ["utf-8-sig", "utf-8", "latin-1", "cp1258", "cp1252"]:
        try:
            with open(path, encoding=enc) as f:
                f.read(4096)
            return enc
        except (UnicodeDecodeError, UnicodeError):
            pass
    return "latin-1"


def _convert_point(csv_path, out_dir, name, fields, geom_col="Shape"):
    """Generic converter: standardized CSV with GeoJSON Point -> Point shapefile."""
    print(f"\n  Converting {name} ...")

    shp_fields = [(f[1], f[2], f[3]) for f in fields]
    ds, layer = _make_shapefile(out_dir, name, ogr.wkbPoint, 4326, shp_fields)

    enc = _detect_encoding(csv_path)
    with open(csv_path, encoding=enc) as f:
        reader = csv.DictReader(f)
        n_ok, n_skip = 0, 0

        for row in reader:
            shape_str = row.get(geom_col, "").strip()
            coords = _parse_geojson_point(shape_str)
            if coords is None:
                n_skip += 1
                continue
            lon, lat = coords

            feat = ogr.Feature(layer.GetLayerDefn())
            pt = ogr.Geometry(ogr.wkbPoint)
            pt.AddPoint(lon, lat)
            feat.SetGeometry(pt)
            _set_fields(feat, row, fields)
            layer.CreateFeature(feat)
            feat = None
            n_ok += 1

    ds = None
    _write_cpg(out_dir, name)
    _report(os.path.join(out_dir, name + ".shp"), name, out_dir, n_ok, n_skip)


def _convert_line(csv_path, out_dir, name, fields, geom_col="RouteShape"):
    """Generic converter: standardized CSV with GeoJSON LineString -> LineString shapefile."""
    print(f"\n  Converting {name} ...")

    shp_fields = [(f[1], f[2], f[3]) for f in fields]
    ds, layer = _make_shapefile(out_dir, name, ogr.wkbLineString, 4326, shp_fields)

    enc = _detect_encoding(csv_path)
    with open(csv_path, encoding=enc) as f:
        reader = csv.DictReader(f)
        n_ok, n_skip = 0, 0

        for row in reader:
            shape_str = row.get(geom_col, "").strip()
            geom = _parse_geojson_geometry(shape_str)
            if geom is None:
                n_skip += 1
                continue

            feat = ogr.Feature(layer.GetLayerDefn())
            feat.SetGeometry(geom)
            _set_fields(feat, row, fields)
            layer.CreateFeature(feat)
            feat = None
            n_ok += 1

    ds = None
    _write_cpg(out_dir, name)
    _report(os.path.join(out_dir, name + ".shp"), name, out_dir, n_ok, n_skip)


# ══════════════════════════════════════════════════════════════════════════════
# Type 2: River, Lake, and Canal Network
# ══════════════════════════════════════════════════════════════════════════════

class RiverLakeCanalNetwork:
    """Data group 2 - rivers, canals, lakes, dams."""

    # ── 2.1 Rivers ────────────────────────────────────────────────────────────
    @staticmethod
    def convert_rivers(csv_path, out_dir):
        print("\n[Type 2] Rivers")
        _convert_line(
            csv_path=csv_path,
            out_dir=out_dir,
            name="rivers",
            fields=[
                ("ID",         "ID",         ogr.OFTInteger, 10),
                ("Name",       "Name",       ogr.OFTString,  150),
                ("Code",       "Code",       ogr.OFTString,  20),
                ("Strahler",   "Strahler",   ogr.OFTInteger, 5),
                ("Length_m",   "Length_m",    ogr.OFTReal,    12),
                ("Width_m",    "Width_m",    ogr.OFTReal,    10),
                ("BedElev_m",  "BedElev_m",  ogr.OFTReal,    10),
                ("BankElev_m", "BankElev_m", ogr.OFTReal,    10),
                ("FlowDir",    "FlowDir",    ogr.OFTString,  20),
                ("FromNode",   "FromNode",   ogr.OFTString,  20),
                ("ToNode",     "ToNode",     ogr.OFTString,  20),
                ("XSType",     "XSType",     ogr.OFTString,  30),
                ("Material",   "Material",   ogr.OFTString,  40),
                ("Basin",      "Basin",      ogr.OFTString,  80),
                ("IrrigSys",   "IrrigSys",   ogr.OFTString,  120),
                ("Location",   "Location",   ogr.OFTString,  150),
                ("Manager",    "Manager",    ogr.OFTString,  80),
                ("YearBuilt",  "YearBuilt",  ogr.OFTInteger, 5),
                ("YearUpdate", "YearUpdate", ogr.OFTInteger, 5),
                ("Status",     "Status",     ogr.OFTString,  30),
                ("Notes",      "Notes",      ogr.OFTString,  254),
            ],
        )

    # ── 2.2 Canals ────────────────────────────────────────────────────────────
    @staticmethod
    def convert_canals(csv_path, out_dir):
        print("\n[Type 2] Canals")
        _convert_line(
            csv_path=csv_path,
            out_dir=out_dir,
            name="canals",
            fields=[
                ("ID",         "ID",         ogr.OFTInteger, 10),
                ("Name",       "Name",       ogr.OFTString,  150),
                ("Type",       "Type",       ogr.OFTString,  30),
                ("Length_m",   "Length_m",    ogr.OFTReal,    12),
                ("Width_m",    "Width_m",    ogr.OFTString,  10),
                ("BedElev_m",  "BedElev_m",  ogr.OFTString,  30),
                ("LeftBank",   "LeftBank",   ogr.OFTString,  30),
                ("RightBank",  "RightBank",  ogr.OFTString,  30),
                ("SlopCoef",   "SlopCoef",   ogr.OFTString,  20),
                ("Material",   "Material",   ogr.OFTString,  40),
                ("Grade",      "Grade",      ogr.OFTString,  10),
                ("Purpose",    "Purpose",    ogr.OFTString,  60),
                ("SvcArea",    "SvcArea",    ogr.OFTReal,    12),
                ("IrrigSys",   "IrrigSys",   ogr.OFTString,  120),
                ("FlowDir",    "FlowDir",    ogr.OFTString,  20),
                ("FromNode",   "FromNode",   ogr.OFTString,  20),
                ("ToNode",     "ToNode",     ogr.OFTString,  20),
                ("XSType",     "XSType",     ogr.OFTString,  30),
                ("WtrLevel",   "WtrLevel",   ogr.OFTReal,    10),
                ("XSArea",     "XSArea",     ogr.OFTReal,    10),
                ("Location",   "Location",   ogr.OFTString,  150),
                ("Manager",    "Manager",    ogr.OFTString,  80),
                ("YearBuilt",  "YearBuilt",  ogr.OFTInteger, 5),
                ("YearUpdate", "YearUpdate", ogr.OFTInteger, 5),
                ("Notes",      "Notes",      ogr.OFTString,  254),
            ],
        )

    # ── 2.3 Lakes ─────────────────────────────────────────────────────────────
    @staticmethod
    def convert_lakes(csv_path, out_dir):
        print("\n[Type 2] Lakes")
        _convert_point(
            csv_path=csv_path,
            out_dir=out_dir,
            name="lakes",
            fields=[
                ("ID",         "ID",         ogr.OFTInteger, 10),
                ("Name",       "Name",       ogr.OFTString,  150),
                ("Group",      "Group",      ogr.OFTString,  40),
                ("Area_ha",    "Area_ha",    ogr.OFTReal,    12),
                ("BedArea_ha", "BedArea_ha", ogr.OFTReal,    12),
                ("Vol_m3",     "Vol_m3",     ogr.OFTReal,    15),
                ("BedElev_m",  "BedElev_m",  ogr.OFTReal,    10),
                ("CrestElv",   "CrestElv",   ogr.OFTReal,    10),
                ("BankElev_m", "BankElev_m", ogr.OFTReal,    10),
                ("NatWtrLvl",  "NatWtrLvl",  ogr.OFTReal,    10),
                ("WetLvl_m",   "WetLvl_m",   ogr.OFTReal,    10),
                ("DryLvl_m",   "DryLvl_m",   ogr.OFTReal,    10),
                ("NumInlets",  "NumInlets",  ogr.OFTInteger, 5),
                ("Perim_m",    "Perim_m",    ogr.OFTReal,    12),
                ("IrrigSys",   "IrrigSys",   ogr.OFTString,  120),
                ("Location",   "Location",   ogr.OFTString,  150),
                ("Province",   "Province",   ogr.OFTString,  50),
                ("District",   "District",   ogr.OFTString,  50),
                ("Status",     "Status",     ogr.OFTString,  30),
                ("Notes",      "Notes",      ogr.OFTString,  254),
            ],
        )

    # ── 2.4a CONGDAP (hydraulic structures) ───────────────────────────────────
    @staticmethod
    def convert_congdap(csv_path, out_dir):
        print("\n[Type 2] CONGDAP")
        _convert_point(
            csv_path=csv_path,
            out_dir=out_dir,
            name="congdap",
            fields=[
                ("ID",         "ID",         ogr.OFTInteger, 10),
                ("Name",       "Name",       ogr.OFTString,  150),
                ("Type",       "Type",       ogr.OFTString,  60),
                ("Form",       "Form",       ogr.OFTString,  60),
                ("Chainage",   "Chainage",   ogr.OFTString,  40),
                ("Length_m",   "Length_m",    ogr.OFTReal,    10),
                ("Width_m",    "Width_m",    ogr.OFTReal,    10),
                ("Height_m",   "Height_m",   ogr.OFTReal,    10),
                ("Diam_m",     "Diam_m",     ogr.OFTReal,    10),
                ("Openings",   "Openings",   ogr.OFTInteger, 5),
                ("InvElev_m",  "InvElev_m",  ogr.OFTReal,    10),
                ("CrestElv",   "CrestElv",   ogr.OFTReal,    10),
                ("Grade",      "Grade",      ogr.OFTString,  10),
                ("Operation",  "Operation",  ogr.OFTString,  60),
                ("Purpose",    "Purpose",    ogr.OFTString,  100),
                ("SvcArea",    "SvcArea",    ogr.OFTReal,    12),
                ("IrrigSys",   "IrrigSys",   ogr.OFTString,  120),
                ("Location",   "Location",   ogr.OFTString,  120),
                ("Manager",    "Manager",    ogr.OFTString,  80),
                ("YearBuilt",  "YearBuilt",  ogr.OFTInteger, 5),
                ("YearUpdate", "YearUpdate", ogr.OFTInteger, 5),
                ("Notes",      "Notes",      ogr.OFTString,  254),
            ],
        )

    # ── 2.4b Mekong Dams ─────────────────────────────────────────────────────
    @staticmethod
    def convert_mekong_dams(csv_path, out_dir):
        print("\n[Type 2] Mekong Dams")
        _convert_point(
            csv_path=csv_path,
            out_dir=out_dir,
            name="mekong_dams",
            fields=[
                ("ID",         "ID",         ogr.OFTInteger, 10),
                ("Name",       "Name",       ogr.OFTString,  150),
                ("Type",       "Type",       ogr.OFTString,  60),
                ("River",      "River",      ogr.OFTString,  80),
                ("Basin",      "Basin",      ogr.OFTString,  80),
                ("Height_m",   "Height_m",   ogr.OFTReal,    10),
                ("Length_m",   "Length_m",    ogr.OFTReal,    10),
                ("Cap_MW",     "Cap_MW",     ogr.OFTReal,    12),
                ("Vol_Mm3",    "Vol_Mm3",    ogr.OFTReal,    12),
                ("Catch_km2",  "Catch_km2",  ogr.OFTReal,    12),
                ("Elev_m",     "Elev_m",     ogr.OFTReal,    10),
                ("Purpose",    "Purpose",    ogr.OFTString,  100),
                ("SvcArea",    "SvcArea",    ogr.OFTReal,    12),
                ("Country",    "Country",    ogr.OFTString,  40),
                ("Complete",   "Complete",   ogr.OFTInteger, 5),
                ("Location",   "Location",   ogr.OFTString,  150),
                ("Status",     "Status",     ogr.OFTString,  30),
                ("Notes",      "Notes",      ogr.OFTString,  254),
            ],
        )


# ══════════════════════════════════════════════════════════════════════════════
# Type 3: Urban Drainage System
# ══════════════════════════════════════════════════════════════════════════════

class UrbanDrainageSystem:
    """Data group 3 - sewer conduits, manholes, pumps, outlets, orifices."""

    # ── 3.1 Sewer Network ─────────────────────────────────────────────────────
    @staticmethod
    def convert_sewers(csv_path, out_dir):
        print("\n[Type 3] Sewers")
        _convert_line(
            csv_path=csv_path,
            out_dir=out_dir,
            name="sewers",
            fields=[
                ("ID",         "ID",         ogr.OFTInteger, 10),
                ("Name",       "Name",       ogr.OFTString,  150),
                ("Type",       "Type",       ogr.OFTString,  30),
                ("Diam_mm",    "Diam_mm",    ogr.OFTReal,    10),
                ("Size_mm",    "Size_mm",    ogr.OFTString,  30),
                ("Length_m",   "Length_m",    ogr.OFTReal,    12),
                ("Material",   "Material",   ogr.OFTString,  40),
                ("XSArea",     "XSArea",     ogr.OFTReal,    10),
                ("FlowDir",    "FlowDir",    ogr.OFTString,  20),
                ("FromNode",   "FromNode",   ogr.OFTString,  20),
                ("ToNode",     "ToNode",     ogr.OFTString,  20),
                ("XSType",     "XSType",     ogr.OFTString,  30),
                ("DrainZone",  "DrainZone",  ogr.OFTString,  30),
                ("Catchment",  "Catchment",  ogr.OFTString,  30),
                ("Location",   "Location",   ogr.OFTString,  150),
                ("Province",   "Province",   ogr.OFTString,  50),
                ("District",   "District",   ogr.OFTString,  50),
                ("Status",     "Status",     ogr.OFTString,  30),
                ("Notes",      "Notes",      ogr.OFTString,  254),
            ],
        )

    # ── 3.2 Manholes ──────────────────────────────────────────────────────────
    @staticmethod
    def convert_manholes(csv_path, out_dir):
        print("\n[Type 3] Manholes")
        _convert_point(
            csv_path=csv_path,
            out_dir=out_dir,
            name="manholes",
            fields=[
                ("ID",         "ID",         ogr.OFTInteger, 10),
                ("Name",       "Name",       ogr.OFTString,  150),
                ("Type",       "Type",       ogr.OFTString,  30),
                ("Area_m2",    "Area_m2",    ogr.OFTReal,    10),
                ("Size_m",     "Size_m",     ogr.OFTString,  30),
                ("CoverType",  "CoverType",  ogr.OFTString,  40),
                ("InvElev_m",  "InvElev_m",  ogr.OFTReal,    10),
                ("RimElev_m",  "RimElev_m",  ogr.OFTReal,    10),
                ("SewerLine",  "SewerLine",  ogr.OFTString,  80),
                ("DrainZone",  "DrainZone",  ogr.OFTString,  30),
                ("Catchment",  "Catchment",  ogr.OFTString,  30),
                ("Location",   "Location",   ogr.OFTString,  150),
                ("Province",   "Province",   ogr.OFTString,  50),
                ("District",   "District",   ogr.OFTString,  50),
                ("Status",     "Status",     ogr.OFTString,  30),
                ("Notes",      "Notes",      ogr.OFTString,  254),
            ],
        )

    # ── 3.3 Pumping Stations ──────────────────────────────────────────────────
    @staticmethod
    def convert_pumps(csv_path, out_dir):
        print("\n[Type 3] Pumping Stations")
        _convert_point(
            csv_path=csv_path,
            out_dir=out_dir,
            name="pumps",
            fields=[
                ("ID",         "ID",         ogr.OFTInteger, 10),
                ("Name",       "Name",       ogr.OFTString,  150),
                ("FromNode",   "FromNode",   ogr.OFTString,  20),
                ("ToNode",     "ToNode",     ogr.OFTString,  20),
                ("Position",   "Position",   ogr.OFTString,  80),
                ("Type",       "Type",       ogr.OFTString,  30),
                ("Cap_m3s",    "Cap_m3s",    ogr.OFTString,  30),
                ("Purpose",    "Purpose",    ogr.OFTString,  100),
                ("SvcArea",    "SvcArea",    ogr.OFTReal,    12),
                ("IrrigSys",   "IrrigSys",   ogr.OFTString,  120),
                ("Location",   "Location",   ogr.OFTString,  150),
                ("Manager",    "Manager",    ogr.OFTString,  80),
                ("YearBuilt",  "YearBuilt",  ogr.OFTInteger, 5),
                ("YearUpdate", "YearUpdate", ogr.OFTInteger, 5),
                ("Status",     "Status",     ogr.OFTString,  30),
                ("Notes",      "Notes",      ogr.OFTString,  254),
            ],
        )

    # ── 3.4 Outlets / Outfalls ────────────────────────────────────────────────
    @staticmethod
    def convert_outlets(csv_path, out_dir):
        print("\n[Type 3] Outlets")
        _convert_point(
            csv_path=csv_path,
            out_dir=out_dir,
            name="outlets",
            fields=[
                ("ID",         "ID",         ogr.OFTInteger, 10),
                ("Name",       "Name",       ogr.OFTString,  150),
                ("FromNode",   "FromNode",   ogr.OFTString,  20),
                ("ToNode",     "ToNode",     ogr.OFTString,  20),
                ("Type",       "Type",       ogr.OFTString,  60),
                ("Form",       "Form",       ogr.OFTString,  60),
                ("Length_m",   "Length_m",    ogr.OFTReal,    10),
                ("Width_m",    "Width_m",    ogr.OFTReal,    10),
                ("Height_m",   "Height_m",   ogr.OFTReal,    10),
                ("Diam_m",     "Diam_m",     ogr.OFTReal,    10),
                ("Openings",   "Openings",   ogr.OFTInteger, 5),
                ("InvElev_m",  "InvElev_m",  ogr.OFTReal,    10),
                ("CrestElv",   "CrestElv",   ogr.OFTReal,    10),
                ("Operation",  "Operation",  ogr.OFTString,  60),
                ("Purpose",    "Purpose",    ogr.OFTString,  100),
                ("Project",    "Project",    ogr.OFTString,  200),
                ("Location",   "Location",   ogr.OFTString,  120),
                ("YearBuilt",  "YearBuilt",  ogr.OFTInteger, 5),
                ("YearUpdate", "YearUpdate", ogr.OFTInteger, 5),
                ("Notes",      "Notes",      ogr.OFTString,  254),
            ],
        )

    # ── 3.5 Orifices / Control Gates ──────────────────────────────────────────
    @staticmethod
    def convert_orifices(csv_path, out_dir):
        print("\n[Type 3] Orifices")
        _convert_point(
            csv_path=csv_path,
            out_dir=out_dir,
            name="orifices",
            fields=[
                ("ID",         "ID",         ogr.OFTInteger, 10),
                ("Name",       "Name",       ogr.OFTString,  150),
                ("FromNode",   "FromNode",   ogr.OFTString,  20),
                ("ToNode",     "ToNode",     ogr.OFTString,  20),
                ("Position",   "Position",   ogr.OFTString,  80),
                ("Type",       "Type",       ogr.OFTString,  60),
                ("Form",       "Form",       ogr.OFTString,  60),
                ("Length_m",   "Length_m",    ogr.OFTReal,    10),
                ("Width_m",    "Width_m",    ogr.OFTReal,    10),
                ("Height_m",   "Height_m",   ogr.OFTReal,    10),
                ("Openings",   "Openings",   ogr.OFTInteger, 5),
                ("InvElev_m",  "InvElev_m",  ogr.OFTReal,    10),
                ("CrestElv",   "CrestElv",   ogr.OFTReal,    10),
                ("ClearSpan",  "ClearSpan",  ogr.OFTString,  40),
                ("SillElev",   "SillElev",   ogr.OFTString,  20),
                ("GateMtrl",   "GateMtrl",   ogr.OFTString,  60),
                ("GateCtrl",   "GateCtrl",   ogr.OFTString,  60),
                ("Purpose",    "Purpose",    ogr.OFTString,  200),
                ("SvcArea",    "SvcArea",    ogr.OFTReal,    12),
                ("Grade",      "Grade",      ogr.OFTString,  10),
                ("Location",   "Location",   ogr.OFTString,  120),
                ("YearBuilt",  "YearBuilt",  ogr.OFTInteger, 5),
                ("YearUpdate", "YearUpdate", ogr.OFTInteger, 5),
                ("Notes",      "Notes",      ogr.OFTString,  254),
            ],
        )


# ══════════════════════════════════════════════════════════════════════════════
# Type 5: Pollution Sources
# ══════════════════════════════════════════════════════════════════════════════

class PollutionSources:
    """Data group 5 - discharge/pollution source locations."""

    @staticmethod
    def convert_discharge(csv_path, out_dir):
        print("\n[Type 5] Discharge")
        _convert_point(
            csv_path=csv_path,
            out_dir=out_dir,
            name="discharge",
            fields=[
                ("ID",         "ID",         ogr.OFTInteger, 10),
                ("Name",       "Name",       ogr.OFTString,  254),
                ("Discharger", "Discharger", ogr.OFTString,  200),
                ("Address",    "Address",    ogr.OFTString,  200),
                ("Industry",   "Industry",   ogr.OFTString,  100),
                ("Receiver",   "Receiver",   ogr.OFTString,  150),
                ("DischPt",    "DischPt",    ogr.OFTString,  200),
                ("IrrigSys",   "IrrigSys",   ogr.OFTString,  120),
                ("Treatment",  "Treatment",  ogr.OFTString,  200),
                ("Permit",     "Permit",     ogr.OFTString,  150),
                ("PermitOrg",  "PermitOrg",  ogr.OFTString,  100),
                ("Standard",   "Standard",   ogr.OFTString,  100),
                ("FlowRate",   "FlowRate",   ogr.OFTString,  50),
                ("ExpiryDt",   "ExpiryDt",   ogr.OFTString,  30),
                ("DischTerm",  "DischTerm",  ogr.OFTString,  100),
                ("YearUpdate", "YearUpdate", ogr.OFTInteger, 5),
                ("Notes",      "Notes",      ogr.OFTString,  254),
            ],
        )


# ══════════════════════════════════════════════════════════════════════════════
# CLI entry point
# ══════════════════════════════════════════════════════════════════════════════

def _j(base, *parts):
    """Join base directory with sub-path parts."""
    return os.path.join(base, *parts)


def run_all(base_dir):
    print("=" * 60)
    print("Dataset Standardization - CSV to Shapefile")
    print(f"Base directory: {base_dir}")
    print("=" * 60)

    rlc = "mang_luoi_song_ho_kenh_muong"
    tn  = "thoat_nuoc"
    nt  = "nguon_thai"

    RiverLakeCanalNetwork.convert_rivers(
        _j(base_dir, rlc, "rivers.csv"),
        _j(base_dir, rlc, "rivers"))
    RiverLakeCanalNetwork.convert_canals(
        _j(base_dir, rlc, "canals.csv"),
        _j(base_dir, rlc, "canals"))
    RiverLakeCanalNetwork.convert_lakes(
        _j(base_dir, rlc, "lakes.csv"),
        _j(base_dir, rlc, "lakes"))
    RiverLakeCanalNetwork.convert_congdap(
        _j(base_dir, rlc, "congdap.csv"),
        _j(base_dir, rlc, "congdap"))
    RiverLakeCanalNetwork.convert_mekong_dams(
        _j(base_dir, rlc, "dams.csv"),
        _j(base_dir, rlc, "mekong_dams"))

    UrbanDrainageSystem.convert_sewers(
        _j(base_dir, tn, "sewers.csv"),
        _j(base_dir, tn, "sewers"))
    UrbanDrainageSystem.convert_manholes(
        _j(base_dir, tn, "manholes.csv"),
        _j(base_dir, tn, "manholes"))
    UrbanDrainageSystem.convert_pumps(
        _j(base_dir, tn, "pumps.csv"),
        _j(base_dir, tn, "pumps"))
    UrbanDrainageSystem.convert_outlets(
        _j(base_dir, tn, "outlets.csv"),
        _j(base_dir, tn, "outlets"))
    UrbanDrainageSystem.convert_orifices(
        _j(base_dir, tn, "orifices.csv"),
        _j(base_dir, tn, "orifices"))

    PollutionSources.convert_discharge(
        _j(base_dir, nt, "discharge.csv"),
        _j(base_dir, nt, "discharge"))

    print("\n" + "=" * 60)
    print("All conversions complete.")


if __name__ == "__main__":
    # parse --base-dir
    base_dir = None
    if "--base-dir" in sys.argv:
        idx = sys.argv.index("--base-dir")
        if idx + 1 < len(sys.argv):
            base_dir = sys.argv[idx + 1]

    if base_dir is None:
        print("Error: --base-dir is required.")
        print("Usage: python standardize.py --base-dir <path> [--type 2|3|5]")
        sys.exit(1)

    # parse --type
    type_filter = None
    if "--type" in sys.argv:
        idx = sys.argv.index("--type")
        if idx + 1 < len(sys.argv):
            type_filter = sys.argv[idx + 1]

    rlc = "mang_luoi_song_ho_kenh_muong"
    tn  = "thoat_nuoc"
    nt  = "nguon_thai"

    if type_filter == "2":
        RiverLakeCanalNetwork.convert_rivers(
            _j(base_dir, rlc, "rivers.csv"),
            _j(base_dir, rlc, "rivers"))
        RiverLakeCanalNetwork.convert_canals(
            _j(base_dir, rlc, "canals.csv"),
            _j(base_dir, rlc, "canals"))
        RiverLakeCanalNetwork.convert_lakes(
            _j(base_dir, rlc, "lakes.csv"),
            _j(base_dir, rlc, "lakes"))
        RiverLakeCanalNetwork.convert_congdap(
            _j(base_dir, rlc, "congdap.csv"),
            _j(base_dir, rlc, "congdap"))
        RiverLakeCanalNetwork.convert_mekong_dams(
            _j(base_dir, rlc, "dams.csv"),
            _j(base_dir, rlc, "mekong_dams"))
    elif type_filter == "3":
        UrbanDrainageSystem.convert_sewers(
            _j(base_dir, tn, "sewers.csv"),
            _j(base_dir, tn, "sewers"))
        UrbanDrainageSystem.convert_manholes(
            _j(base_dir, tn, "manholes.csv"),
            _j(base_dir, tn, "manholes"))
        UrbanDrainageSystem.convert_pumps(
            _j(base_dir, tn, "pumps.csv"),
            _j(base_dir, tn, "pumps"))
        UrbanDrainageSystem.convert_outlets(
            _j(base_dir, tn, "outlets.csv"),
            _j(base_dir, tn, "outlets"))
        UrbanDrainageSystem.convert_orifices(
            _j(base_dir, tn, "orifices.csv"),
            _j(base_dir, tn, "orifices"))
    elif type_filter == "5":
        PollutionSources.convert_discharge(
            _j(base_dir, nt, "discharge.csv"),
            _j(base_dir, nt, "discharge"))
    else:
        run_all(base_dir)
