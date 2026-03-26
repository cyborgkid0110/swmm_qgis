"""
Reverse-convert ESRI Shapefiles back to standardized CSV datasets.

Reads Shapefiles from a QGIS editing directory (e.g. sample_region_qgis/)
and writes standardized CSVs back to the dataset directory (e.g. sample_region/).
Geometry is serialized to GeoJSON in the Shape/RouteShape CSV columns.

Usage:
    conda run -n qgis-env python src/tools/shp_to_csv.py
    conda run -n qgis-env python src/tools/shp_to_csv.py --src sample_region_qgis --dst sample_region
"""
import csv
import json
import os
import sys

from osgeo import ogr, osr

ogr.UseExceptions()

# Force UTF-8 encoding for Shapefiles (default is ISO-8859-1)
from osgeo import gdal
gdal.SetConfigOption("SHAPE_ENCODING", "UTF-8")

REPO_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


# ═══════════════════════════════════════════════════════════════════════════
# CSV schema definitions
# ═══════════════════════════════════════════════════════════════════════════

# Each schema: (csv_column_name, shapefile_field_name_truncated)
# The CSV column is the full standardized name, the SHP field is truncated
# to 10 chars. Geometry columns (Shape/RouteShape) are not in the schema —
# they are generated from the Shapefile geometry.

CANALS_COLS = [
    "ID", "Name", "Type", "Length_m", "Width_m", "BedElev_m", "LeftBank",
    "RightBank", "SlopCoef", "Material", "Grade", "Purpose", "SvcArea",
    "IrrigSys", "FlowDir", "FromNode", "ToNode", "XSType", "WtrLevel",
    "XSArea", "Location", "Province", "District", "Ward", "Manager",
    "YearBuilt", "YearUpdate", "Status", "Notes",
]

RIVERS_COLS = [
    "ID", "Name", "Code", "Strahler", "Length_m", "Width_m", "BedElev_m",
    "BankElev_m", "FlowDir", "FromNode", "ToNode", "XSType", "Material",
    "Basin", "IrrigSys", "Location", "Province", "District", "Ward",
    "Manager", "YearBuilt", "YearUpdate", "Status", "Notes",
]

WEIR_COLS = [
    "ID", "Name", "Type", "Form", "Chainage", "River", "Basin", "Length_m",
    "Width_m", "Height_m", "Diam_m", "Openings", "InvElev_m", "CrestElv",
    "Cap_MW", "Vol_Mm3", "Catch_km2", "Elev_m",
    "Grade", "Operation", "Purpose", "Receiver", "Project", "SvcArea",
    "IrrigSys", "Country", "Complete", "Location", "Province", "District",
    "Ward", "Manager", "YearBuilt", "YearUpdate", "Status", "Notes",
]

LAKES_COLS = [
    "ID", "Name", "Group", "Area_ha", "BedArea_ha", "Vol_m3", "BedElev_m",
    "CrestElv", "BankElev_m", "NatWtrLvl", "WetLvl_m", "DryLvl_m",
    "NumInlets", "Perim_m", "IrrigSys", "Location", "Province", "District",
    "Ward", "Manager", "YearBuilt", "YearUpdate", "Status", "Notes",
]

SEWERS_COLS = [
    "ID", "Name", "Type", "Diam_mm", "Size_mm", "Length_m", "Material",
    "XSArea", "FlowDir", "FromNode", "ToNode", "XSType", "StreetID",
    "DrainZone", "Catchment", "Location", "Province", "District", "Ward",
    "Manager", "YearBuilt", "YearUpdate", "Status", "Notes",
]

MANHOLES_COLS = [
    "ID", "Name", "Type", "Area_m2", "Size_m", "CoverType", "InvElev_m",
    "RimElev_m", "SewerLine", "StreetID", "DrainZone", "Catchment",
    "Location", "Province", "District", "Ward", "Manager", "YearBuilt",
    "YearUpdate", "Status", "Notes",
]

PUMPS_COLS = [
    "ID", "Name", "Source", "SewerLine", "Type", "Grade",
    "NumPumps", "Cap_m3s", "InElev_m", "OutElev_m", "AutoMonit", "TrashScr",
    "Purpose", "SvcArea", "IrrigSys", "StreetID", "Location", "Province",
    "District", "Ward", "Manager", "YearBuilt", "YearUpdate", "Status",
    "Notes",
]

ORIFICES_COLS = [
    "ID", "Name", "FromNode", "ToNode", "Position", "Type", "Form",
    "Length_m", "Width_m", "Height_m", "Openings", "InvElev_m", "CrestElv",
    "DischCoef", "ClearSpan", "SillElev", "GateMtrl", "GateCtrl", "Purpose",
    "Receiver", "SvcArea", "Grade", "Location", "Province", "District", "Ward",
    "Manager", "YearBuilt", "YearUpdate", "Status", "Notes",
]

OUTFALLS_COLS = [
    "ID", "Name", "Type", "Elev_m", "FixedStage", "FlapGate",
    "Receiver", "SewerLine", "Location", "Province", "District", "Ward",
    "Manager", "YearBuilt", "YearUpdate", "Status", "Notes",
]

RAINGAGES_COLS = [
    "ID", "Name", "Format", "Interval", "SCF", "DataSource", "SeriesName",
    "StationID", "RainUnits", "Location", "Province", "District", "Ward",
    "Manager", "YearBuilt", "YearUpdate", "Status", "Notes",
]

SUBCATCHMENTS_COLS = [
    "ID", "Name", "RainGage", "OutletLon", "OutletLat", "SewerRoute",
    "Area_ha", "Imperv_pct", "Width_m",
    "Slope_pct", "CurbLen_m", "N_Imperv", "N_Perv", "S_Imperv_mm",
    "S_Perv_mm", "PctZero", "RouteTo", "PctRouted", "InfMethod",
    "SuctHead_mm", "Conductiv_mmh", "InitDef", "Location", "Province",
    "District", "Ward", "Manager", "YearBuilt", "YearUpdate", "Status",
    "Notes",
]

DISCHARGE_COLS = [
    "ID", "Name", "Discharger", "Address", "Industry", "Receiver",
    "DischPt", "IrrigSys", "Treatment", "Permit", "PermitOrg", "Standard",
    "FlowRate", "ExpiryDt", "DischTerm", "Location", "Province", "District",
    "Ward", "Manager", "YearBuilt", "YearUpdate", "Status", "Notes",
]


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _truncate(name, max_len=10):
    return name[:max_len]


def _build_col_map(csv_columns):
    """Build mapping from truncated SHP field name → full CSV column name.

    Handles collisions: if two CSV columns truncate to the same 10-char
    name, the first one wins (rare in practice).
    """
    col_map = {}
    for col in csv_columns:
        shp_name = _truncate(col)
        if shp_name not in col_map:
            col_map[shp_name] = col
    return col_map


def _geom_to_geojson(geom):
    """Convert OGR Geometry to GeoJSON dict string."""
    gtype = geom.GetGeometryType()

    if gtype == ogr.wkbPoint:
        return json.dumps({
            "type": "Point",
            "coordinates": [geom.GetX(), geom.GetY()]
        })
    elif gtype == ogr.wkbLineString:
        coords = []
        for i in range(geom.GetPointCount()):
            coords.append([geom.GetX(i), geom.GetY(i)])
        return json.dumps({"type": "LineString", "coordinates": coords})
    elif gtype in (ogr.wkbPolygon, ogr.wkbPolygon25D):
        rings = []
        for ri in range(geom.GetGeometryCount()):
            ring = geom.GetGeometryRef(ri)
            ring_coords = []
            for i in range(ring.GetPointCount()):
                ring_coords.append([ring.GetX(i), ring.GetY(i)])
            rings.append(ring_coords)
        return json.dumps({"type": "Polygon", "coordinates": rings})
    else:
        return ""


def _read_shapefile(shp_path):
    """Open Shapefile and return (layer, feature_count) or (None, 0)."""
    if not os.path.exists(shp_path):
        return None, 0
    ds = ogr.Open(shp_path, 0)
    if ds is None:
        return None, 0
    layer = ds.GetLayer()
    return ds, layer.GetFeatureCount()


# ═══════════════════════════════════════════════════════════════════════════
# ShpToCsv converter class
# ═══════════════════════════════════════════════════════════════════════════

class ShpToCsv:
    """Convert ESRI Shapefiles back to standardized CSV datasets."""

    def __init__(self, src_dir, dst_dir):
        """
        Args:
            src_dir: Source Shapefile directory (e.g. sample_region_qgis/).
            dst_dir: Destination CSV directory (e.g. sample_region/).
        """
        self.src_dir = src_dir
        self.dst_dir = dst_dir

    def _convert(self, shp_path, csv_path, csv_columns, geom_col):
        """Generic Shapefile → CSV conversion.

        Args:
            shp_path: Path to input .shp file.
            csv_path: Path to output .csv file.
            csv_columns: List of full CSV column names (without geom_col).
            geom_col: Name of geometry column ("Shape" or "RouteShape").

        Returns:
            Number of features written.
        """
        ds, count = _read_shapefile(shp_path)
        if ds is None:
            print(f"  SKIP (not found): {shp_path}")
            return 0

        layer = ds.GetLayer()
        col_map = _build_col_map(csv_columns)

        # Get actual SHP field names
        layer_defn = layer.GetLayerDefn()
        shp_fields = []
        for i in range(layer_defn.GetFieldCount()):
            shp_fields.append(layer_defn.GetFieldDefn(i).GetName())

        os.makedirs(os.path.dirname(csv_path), exist_ok=True)

        # CSV header = all csv_columns + geom_col at the end
        header = list(csv_columns) + [geom_col]

        n_ok = 0
        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=header)
            writer.writeheader()

            layer.ResetReading()
            for feat in layer:
                row = {}
                # Map SHP fields back to CSV columns
                for shp_name in shp_fields:
                    csv_col = col_map.get(shp_name)
                    if csv_col is None:
                        continue
                    val = feat.GetField(shp_name)
                    if val is not None:
                        row[csv_col] = str(val)
                    else:
                        row[csv_col] = ""

                # Geometry → GeoJSON
                geom = feat.GetGeometryRef()
                if geom:
                    row[geom_col] = _geom_to_geojson(geom)
                else:
                    row[geom_col] = ""

                # Fill missing columns with empty string
                for col in csv_columns:
                    if col not in row:
                        row[col] = ""

                writer.writerow(row)
                n_ok += 1

        ds = None
        name = os.path.splitext(os.path.basename(csv_path))[0]
        print(f"  {name}: {n_ok} features -> {csv_path}")
        return n_ok

    # ── Component conversion methods ──────────────────────────────────────

    def convert_canals(self):
        """Canals Shapefile -> CSV (LineString, RouteShape)."""
        return self._convert(
            os.path.join(self.src_dir, "mang_luoi_song_ho_kenh_muong", "canals", "canals.shp"),
            os.path.join(self.dst_dir, "mang_luoi_song_ho_kenh_muong", "canals.csv"),
            CANALS_COLS, "RouteShape")

    def convert_rivers(self):
        """Rivers Shapefile -> CSV (LineString, RouteShape)."""
        return self._convert(
            os.path.join(self.src_dir, "mang_luoi_song_ho_kenh_muong", "rivers", "rivers.shp"),
            os.path.join(self.dst_dir, "mang_luoi_song_ho_kenh_muong", "rivers.csv"),
            RIVERS_COLS, "RouteShape")

    def convert_weirs(self):
        """Weirs Shapefile -> CSV (Point, Shape)."""
        return self._convert(
            os.path.join(self.src_dir, "thoat_nuoc", "weirs", "weirs.shp"),
            os.path.join(self.dst_dir, "thoat_nuoc", "weir.csv"),
            WEIR_COLS, "Shape")

    def convert_lakes(self):
        """Lakes Shapefile -> CSV (Point, Shape)."""
        return self._convert(
            os.path.join(self.src_dir, "mang_luoi_song_ho_kenh_muong", "lakes", "lakes.shp"),
            os.path.join(self.dst_dir, "mang_luoi_song_ho_kenh_muong", "lakes.csv"),
            LAKES_COLS, "Shape")

    def convert_sewers(self):
        """Sewers Shapefile -> CSV (LineString, RouteShape)."""
        return self._convert(
            os.path.join(self.src_dir, "thoat_nuoc", "sewers", "sewers.shp"),
            os.path.join(self.dst_dir, "thoat_nuoc", "sewers.csv"),
            SEWERS_COLS, "RouteShape")

    def convert_manholes(self):
        """Manholes Shapefile -> CSV (Point, Shape)."""
        return self._convert(
            os.path.join(self.src_dir, "thoat_nuoc", "manholes", "manholes.shp"),
            os.path.join(self.dst_dir, "thoat_nuoc", "manholes.csv"),
            MANHOLES_COLS, "Shape")

    def convert_pumps(self):
        """Pumps Shapefile -> CSV (Point, Shape)."""
        return self._convert(
            os.path.join(self.src_dir, "thoat_nuoc", "pumps", "pumps.shp"),
            os.path.join(self.dst_dir, "thoat_nuoc", "pumps.csv"),
            PUMPS_COLS, "Shape")

    def convert_orifices(self):
        """Orifices Shapefile -> CSV (Point, Shape)."""
        return self._convert(
            os.path.join(self.src_dir, "thoat_nuoc", "orifices", "orifices.shp"),
            os.path.join(self.dst_dir, "thoat_nuoc", "orifices.csv"),
            ORIFICES_COLS, "Shape")

    def convert_outfalls(self):
        """Outfalls Shapefile -> CSV (Point, Shape)."""
        return self._convert(
            os.path.join(self.src_dir, "thoat_nuoc", "outfalls", "outfalls.shp"),
            os.path.join(self.dst_dir, "thoat_nuoc", "outfalls.csv"),
            OUTFALLS_COLS, "Shape")

    def convert_raingages(self):
        """Rain gages Shapefile -> CSV (Point, Shape)."""
        return self._convert(
            os.path.join(self.src_dir, "thuy_van", "raingages", "raingages.shp"),
            os.path.join(self.dst_dir, "thuy_van", "raingages.csv"),
            RAINGAGES_COLS, "Shape")

    def convert_subcatchments(self):
        """Subcatchments Shapefile -> CSV (Polygon, Shape)."""
        return self._convert(
            os.path.join(self.src_dir, "dia_hinh_khong_gian", "subcatchments", "subcatchments.shp"),
            os.path.join(self.dst_dir, "dia_hinh_khong_gian", "subcatchments.csv"),
            SUBCATCHMENTS_COLS, "Shape")

    def convert_discharge(self):
        """Discharge Shapefile -> CSV (Point, Shape)."""
        return self._convert(
            os.path.join(self.src_dir, "nguon_thai", "discharge", "discharge.shp"),
            os.path.join(self.dst_dir, "nguon_thai", "discharge.csv"),
            DISCHARGE_COLS, "Shape")

    def convert_all(self):
        """Convert all components."""
        print(f"Shapefile -> CSV: {self.src_dir} -> {self.dst_dir}")
        print("=" * 60)

        total = 0
        print("\n[Group 1: Topography]")
        total += self.convert_subcatchments()

        print("\n[Group 2: River/Lake/Canal Network]")
        total += self.convert_canals()
        total += self.convert_rivers()
        total += self.convert_lakes()

        print("\n[Group 3: Urban Drainage System]")
        total += self.convert_sewers()
        total += self.convert_manholes()
        total += self.convert_pumps()
        total += self.convert_weirs()
        total += self.convert_orifices()
        total += self.convert_outfalls()

        print("\n[Group 4: Hydrology]")
        total += self.convert_raingages()

        print("\n[Group 5: Pollution Sources]")
        total += self.convert_discharge()

        print("\n" + "=" * 60)
        print(f"Total: {total} features converted")
        return total


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Convert Shapefiles back to standardized CSV datasets")
    parser.add_argument("--src", default=os.path.join(REPO_DIR, "sample_region_qgis"),
                        help="Source Shapefile directory")
    parser.add_argument("--dst", default=os.path.join(REPO_DIR, "sample_region"),
                        help="Destination CSV directory")
    args = parser.parse_args()

    converter = ShpToCsv(args.src, args.dst)
    converter.convert_all()


if __name__ == "__main__":
    main()
