"""
Convert standardized CSV datasets to ESRI Shapefiles for QGIS editing.

Reads CSVs from a dataset directory (e.g. sample_region/) and writes
Shapefiles to a separate output directory (e.g. sample_region_qgis/).
Geometry is parsed from GeoJSON in the Shape/RouteShape CSV columns.

Usage:
    conda run -n qgis-env python src/tools/csv_to_shp.py
    conda run -n qgis-env python src/tools/csv_to_shp.py --src dataset --dst dataset_qgis
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
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _make_shapefile(out_dir, name, geom_type, fields):
    """Create a new ESRI Shapefile. Returns (datasource, layer)."""
    os.makedirs(out_dir, exist_ok=True)
    shp_path = os.path.join(out_dir, name + ".shp")

    drv = ogr.GetDriverByName("ESRI Shapefile")
    if os.path.exists(shp_path):
        drv.DeleteDataSource(shp_path)

    ds = drv.CreateDataSource(out_dir)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    layer = ds.CreateLayer(name, srs, geom_type)

    for fdef in fields:
        fname, ftype, width = fdef[0], fdef[1], fdef[2]
        precision = fdef[3] if len(fdef) > 3 else (4 if ftype == ogr.OFTReal else 0)
        fd = ogr.FieldDefn(fname, ftype)
        fd.SetWidth(width)
        fd.SetPrecision(precision)
        layer.CreateField(fd)

    return ds, layer


def _write_cpg(out_dir, name):
    """Write UTF-8 codepage file for Shapefile."""
    with open(os.path.join(out_dir, name + ".cpg"), "w") as f:
        f.write("UTF-8")


def _parse_geojson(s):
    """Parse GeoJSON string → (type, coordinates) or (None, None)."""
    try:
        g = json.loads(s)
        return g["type"], g["coordinates"]
    except Exception:
        return None, None


def _safe_float(val, default=0.0):
    """Parse float, handling Vietnamese number format."""
    try:
        s = str(val).strip()
        if not s:
            return default
        if ";" in s:
            s = s.split(";")[0].strip()
        s = s.lstrip("+").replace(",", ".")
        return float(s)
    except (ValueError, TypeError):
        return default


def _truncate_field_name(name, max_len=10):
    """Truncate field name to Shapefile limit (10 chars)."""
    return name[:max_len]


def _build_fields(csv_headers, geom_col):
    """Build OGR field definitions from CSV headers.

    Skips the geometry column. Maps known numeric fields to OFTReal,
    ID to OFTInteger, everything else to OFTString.
    """
    REAL_FIELDS = {
        "Length_m", "Width_m", "Height_m", "Diam_m", "Diam_mm", "Size_mm",
        "Size_m", "BedElev_m", "BankElev_m", "InvElev_m", "RimElev_m",
        "CrestElv", "WetLvl_m", "DryLvl_m", "NatWtrLvl", "Cap_m3s",
        "Cap_MW", "Vol_Mm3", "Vol_m3", "Catch_km2", "XSArea", "SlopCoef",
        "Roughness", "InElev_m", "OutElev_m", "Area_ha", "BedArea_ha",
        "Perim_m", "Imperv_pct", "Slope_pct", "CurbLen_m", "N_Imperv",
        "N_Perv", "S_Imperv_mm", "S_Perv_mm", "PctZero", "PctRouted",
        "SuctHead_mm", "Conductiv_mmh", "InitDef", "Elev_m", "MaxCap_kW",
        "DischCoef", "ClearSpan", "SillElev", "DesignWL", "FlowRate",
        "MaxDepth_m", "SCF", "Area_m2",
    }
    INT_FIELDS = {"ID", "Strahler", "Openings", "NumPumps", "NumInlets",
                  "Chainage", "YearBuilt", "YearUpdate"}

    fields = []
    for col in csv_headers:
        if col == geom_col:
            continue
        shp_name = _truncate_field_name(col)
        if col in INT_FIELDS:
            fields.append((shp_name, ogr.OFTInteger, 10, 0, col))
        elif col in REAL_FIELDS:
            fields.append((shp_name, ogr.OFTReal, 16, 4, col))
        else:
            fields.append((shp_name, ogr.OFTString, 254, 0, col))
    return fields


# ═══════════════════════════════════════════════════════════════════════════
# CsvToShp converter class
# ═══════════════════════════════════════════════════════════════════════════

class CsvToShp:
    """Convert standardized CSV datasets to ESRI Shapefiles."""

    def __init__(self, src_dir, dst_dir):
        """
        Args:
            src_dir: Source dataset directory (e.g. sample_region/).
            dst_dir: Destination directory for Shapefiles (e.g. sample_region_qgis/).
        """
        self.src_dir = src_dir
        self.dst_dir = dst_dir

    def _convert_points(self, csv_path, out_dir, name, geom_col="Shape"):
        """Convert a Point CSV to Shapefile."""
        if not os.path.exists(csv_path):
            print(f"  SKIP (not found): {csv_path}")
            return 0

        with open(csv_path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames
            rows = list(reader)

        if not rows:
            print(f"  SKIP (empty): {os.path.basename(csv_path)}")
            return 0

        fields = _build_fields(headers, geom_col)
        ogr_fields = [(f[0], f[1], f[2], f[3]) for f in fields]
        ds, layer = _make_shapefile(out_dir, name, ogr.wkbPoint, ogr_fields)

        n_ok = 0
        for row in rows:
            gtype, coords = _parse_geojson(row.get(geom_col, ""))
            if gtype != "Point":
                continue
            feat = ogr.Feature(layer.GetLayerDefn())
            pt = ogr.Geometry(ogr.wkbPoint)
            pt.AddPoint(coords[0], coords[1])
            feat.SetGeometry(pt)
            for shp_name, ftype, _, _, csv_col in fields:
                val = row.get(csv_col, "").strip()
                if not val:
                    continue
                if ftype == ogr.OFTInteger:
                    feat.SetField(shp_name, int(_safe_float(val)))
                elif ftype == ogr.OFTReal:
                    feat.SetField(shp_name, _safe_float(val))
                else:
                    feat.SetField(shp_name, val)
            layer.CreateFeature(feat)
            n_ok += 1

        _write_cpg(out_dir, name)
        ds = None
        print(f"  {name}: {n_ok} features -> {out_dir}")
        return n_ok

    def _convert_lines(self, csv_path, out_dir, name, geom_col="RouteShape"):
        """Convert a LineString CSV to Shapefile."""
        if not os.path.exists(csv_path):
            print(f"  SKIP (not found): {csv_path}")
            return 0

        with open(csv_path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames
            rows = list(reader)

        if not rows:
            print(f"  SKIP (empty): {os.path.basename(csv_path)}")
            return 0

        fields = _build_fields(headers, geom_col)
        ogr_fields = [(f[0], f[1], f[2], f[3]) for f in fields]
        ds, layer = _make_shapefile(out_dir, name, ogr.wkbLineString, ogr_fields)

        n_ok = 0
        for row in rows:
            gtype, coords = _parse_geojson(row.get(geom_col, ""))
            if gtype != "LineString" or len(coords) < 2:
                continue
            feat = ogr.Feature(layer.GetLayerDefn())
            line = ogr.Geometry(ogr.wkbLineString)
            for c in coords:
                line.AddPoint(c[0], c[1])
            feat.SetGeometry(line)
            for shp_name, ftype, _, _, csv_col in fields:
                val = row.get(csv_col, "").strip()
                if not val:
                    continue
                if ftype == ogr.OFTInteger:
                    feat.SetField(shp_name, int(_safe_float(val)))
                elif ftype == ogr.OFTReal:
                    feat.SetField(shp_name, _safe_float(val))
                else:
                    feat.SetField(shp_name, val)
            layer.CreateFeature(feat)
            n_ok += 1

        _write_cpg(out_dir, name)
        ds = None
        print(f"  {name}: {n_ok} features -> {out_dir}")
        return n_ok

    def _convert_polygons(self, csv_path, out_dir, name, geom_col="Shape"):
        """Convert a Polygon CSV to Shapefile."""
        if not os.path.exists(csv_path):
            print(f"  SKIP (not found): {csv_path}")
            return 0

        with open(csv_path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames
            rows = list(reader)

        if not rows:
            print(f"  SKIP (empty): {os.path.basename(csv_path)}")
            return 0

        fields = _build_fields(headers, geom_col)
        ogr_fields = [(f[0], f[1], f[2], f[3]) for f in fields]
        ds, layer = _make_shapefile(out_dir, name, ogr.wkbPolygon, ogr_fields)

        n_ok = 0
        for row in rows:
            gtype, coords = _parse_geojson(row.get(geom_col, ""))
            if gtype != "Polygon" or not coords:
                continue
            feat = ogr.Feature(layer.GetLayerDefn())
            poly = ogr.Geometry(ogr.wkbPolygon)
            ring = ogr.Geometry(ogr.wkbLinearRing)
            for c in coords[0]:  # outer ring
                ring.AddPoint(c[0], c[1])
            poly.AddGeometry(ring)
            feat.SetGeometry(poly)
            for shp_name, ftype, _, _, csv_col in fields:
                val = row.get(csv_col, "").strip()
                if not val:
                    continue
                if ftype == ogr.OFTInteger:
                    feat.SetField(shp_name, int(_safe_float(val)))
                elif ftype == ogr.OFTReal:
                    feat.SetField(shp_name, _safe_float(val))
                else:
                    feat.SetField(shp_name, val)
            layer.CreateFeature(feat)
            n_ok += 1

        _write_cpg(out_dir, name)
        ds = None
        print(f"  {name}: {n_ok} features -> {out_dir}")
        return n_ok

    # ── Component conversion methods ──────────────────────────────────────

    def convert_canals(self):
        """Canals CSV -> LineString Shapefile."""
        return self._convert_lines(
            os.path.join(self.src_dir, "mang_luoi_song_ho_kenh_muong", "canals.csv"),
            os.path.join(self.dst_dir, "mang_luoi_song_ho_kenh_muong", "canals"),
            "canals")

    def convert_rivers(self):
        """Rivers CSV -> LineString Shapefile."""
        return self._convert_lines(
            os.path.join(self.src_dir, "mang_luoi_song_ho_kenh_muong", "rivers.csv"),
            os.path.join(self.dst_dir, "mang_luoi_song_ho_kenh_muong", "rivers"),
            "rivers")

    def convert_weirs(self):
        """Weirs CSV -> Point Shapefile."""
        return self._convert_points(
            os.path.join(self.src_dir, "thoat_nuoc", "weir.csv"),
            os.path.join(self.dst_dir, "thoat_nuoc", "weirs"),
            "weirs")

    def convert_lakes(self):
        """Lakes CSV -> Point Shapefile."""
        return self._convert_points(
            os.path.join(self.src_dir, "mang_luoi_song_ho_kenh_muong", "lakes.csv"),
            os.path.join(self.dst_dir, "mang_luoi_song_ho_kenh_muong", "lakes"),
            "lakes")

    def convert_sewers(self):
        """Sewers CSV -> LineString Shapefile."""
        return self._convert_lines(
            os.path.join(self.src_dir, "thoat_nuoc", "sewers.csv"),
            os.path.join(self.dst_dir, "thoat_nuoc", "sewers"),
            "sewers")

    def convert_manholes(self):
        """Manholes CSV -> Point Shapefile."""
        return self._convert_points(
            os.path.join(self.src_dir, "thoat_nuoc", "manholes.csv"),
            os.path.join(self.dst_dir, "thoat_nuoc", "manholes"),
            "manholes")

    def convert_pumps(self):
        """Pumps CSV -> Point Shapefile."""
        return self._convert_points(
            os.path.join(self.src_dir, "thoat_nuoc", "pumps.csv"),
            os.path.join(self.dst_dir, "thoat_nuoc", "pumps"),
            "pumps")

    def convert_orifices(self):
        """Orifices CSV -> Point Shapefile."""
        return self._convert_points(
            os.path.join(self.src_dir, "thoat_nuoc", "orifices.csv"),
            os.path.join(self.dst_dir, "thoat_nuoc", "orifices"),
            "orifices")

    def convert_outfalls(self):
        """Outfalls CSV -> Point Shapefile."""
        return self._convert_points(
            os.path.join(self.src_dir, "thoat_nuoc", "outfalls.csv"),
            os.path.join(self.dst_dir, "thoat_nuoc", "outfalls"),
            "outfalls")

    def convert_raingages(self):
        """Rain gages CSV -> Point Shapefile."""
        return self._convert_points(
            os.path.join(self.src_dir, "thuy_van", "raingages.csv"),
            os.path.join(self.dst_dir, "thuy_van", "raingages"),
            "raingages")

    def convert_subcatchments(self):
        """Subcatchments CSV -> Polygon Shapefile."""
        return self._convert_polygons(
            os.path.join(self.src_dir, "dia_hinh_khong_gian", "subcatchments.csv"),
            os.path.join(self.dst_dir, "dia_hinh_khong_gian", "subcatchments"),
            "subcatchments")

    def convert_discharge(self):
        """Discharge CSV -> Point Shapefile."""
        return self._convert_points(
            os.path.join(self.src_dir, "nguon_thai", "discharge.csv"),
            os.path.join(self.dst_dir, "nguon_thai", "discharge"),
            "discharge")

    def convert_all(self):
        """Convert all components."""
        print(f"CSV -> Shapefile: {self.src_dir} -> {self.dst_dir}")
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
    parser = argparse.ArgumentParser(description="Convert CSV datasets to Shapefiles")
    parser.add_argument("--src", default=os.path.join(REPO_DIR, "sample_region"),
                        help="Source dataset directory")
    parser.add_argument("--dst", default=os.path.join(REPO_DIR, "sample_region_qgis"),
                        help="Destination Shapefile directory")
    args = parser.parse_args()

    converter = CsvToShp(args.src, args.dst)
    converter.convert_all()


if __name__ == "__main__":
    main()
