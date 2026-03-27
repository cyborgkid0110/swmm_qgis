"""
SWMM Conversion Module

Converts all standardized sewer/drainage datasets to a SWMM .inp file
via the generate_swmm_inp QGIS plugin.

Usage:
    conda run -n qgis-env python src/conversion/conversion.py
"""

import csv
import json
import os
import sys

# ---------- paths ----------------------------------------------------------
REPO_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGIN_DIR = os.path.join(REPO_DIR, "generate_swmm_inp")

# ---------- QGIS init -----------------------------------------------------
sys.path.append(os.path.join(os.environ.get("CONDA_PREFIX", ""), "Library", "python"))

from qgis.core import (
    QgsApplication,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant

QgsApplication.setPrefixPath(os.environ.get("QGIS_PREFIX_PATH", ""), True)
qgs = QgsApplication([], False)
qgs.initQgis()

sys.path.insert(0, os.path.dirname(PLUGIN_DIR))


class Conversion:
    """Convert standardized drainage datasets to SWMM .inp file.

    Component → SWMM section mapping:
        manholes.csv   → [JUNCTIONS]
        lakes.csv      → [STORAGE]
        (auto-created) → [OUTFALLS] (OF01)
        sewers.csv     → [CONDUITS]
        pumps.csv      → [PUMPS]
        orifices.csv   → [ORIFICES]
        weir.csv       → [WEIRS]
        rivers.csv     → [CONDUITS] (decomposed: N pts → N junctions + N-1 conduits)
        canals.csv     → [CONDUITS] (decomposed: N pts → N junctions + N-1 conduits)
        raingages.csv  → [RAINGAGES] + [TIMESERIES]
        subcatchments.csv → [SUBCATCHMENTS] + [SUBAREAS] + [INFILTRATION]
        discharge.csv  → skipped (INFLOWS table, not spatial)
        dams.csv       → skipped (different geographic region)
    """

    ROUGHNESS = {"BTCT": 0.013, "PVC": 0.011, "HDPE": 0.012}
    DEFAULT_ROUGHNESS = 0.013
    LINK_OFFSET = 0.0000125  # ~1.4 m longitude offset for auto-generated ToNode

    def __init__(self, dataset_dir, result_dir, bbox=None, dem_path=None):
        """
        Args:
            dataset_dir: Root dataset directory.
            result_dir: Output directory for .inp files.
            bbox: Optional (min_lon, min_lat, max_lon, max_lat) spatial filter.
                  Only features within this bounding box are included.
            dem_path: Optional path to DEM GeoTIFF (EPSG:4326) for elevation
                      lookup. When provided, junction/storage/outfall elevations
                      are refined: Elevation = DEM_surface - MaxDepth.
        """
        self.dataset_dir = dataset_dir
        self.result_dir = result_dir
        self.bbox = bbox  # (min_lon, min_lat, max_lon, max_lat) or None
        self.dem_path = dem_path
        os.makedirs(result_dir, exist_ok=True)
        self._dem_ds = None
        self._dem_band = None
        self._dem_gt = None
        self._dem_nodata = None

        thoat_nuoc = os.path.join(dataset_dir, "thoat_nuoc")
        mlshkm = os.path.join(dataset_dir, "mang_luoi_song_ho_kenh_muong")

        self.manholes_csv = os.path.join(thoat_nuoc, "manholes.csv")
        self.sewers_csv = os.path.join(thoat_nuoc, "sewers.csv")
        self.pumps_csv = os.path.join(thoat_nuoc, "pumps.csv")
        self.orifices_csv = os.path.join(thoat_nuoc, "orifices.csv")
        self.outfalls_csv = os.path.join(thoat_nuoc, "outfalls.csv")
        self.weirs_csv = os.path.join(thoat_nuoc, "weir.csv")
        self.lakes_csv = os.path.join(mlshkm, "lakes.csv")
        self.rivers_csv = os.path.join(mlshkm, "rivers.csv")
        self.canals_csv = os.path.join(mlshkm, "canals.csv")

        thuy_van = os.path.join(dataset_dir, "thuy_van")
        dh_kg = os.path.join(dataset_dir, "dia_hinh_khong_gian")
        self.raingages_csv = os.path.join(thuy_van, "raingages.csv")
        self.subcatchments_csv = os.path.join(dh_kg, "subcatchments.csv")

    # =========================================================
    # Static helpers
    # =========================================================

    @staticmethod
    def _read_csv(path):
        with open(path, encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))

    @staticmethod
    def _parse_geojson(s):
        """Parse GeoJSON string → (type, coordinates) or (None, None)."""
        try:
            g = json.loads(s)
            return g["type"], g["coordinates"]
        except Exception:
            return None, None

    @staticmethod
    def _swmm_name(name, max_len=25):
        """Sanitize name for SWMM: ASCII only, safe chars only, max 25 chars.

        SWMM has a 25-character internal name limit (MAXID).
        Args:
            name: raw name string.
            max_len: truncate to this length (use 20 when an ID suffix will be appended).
        """
        import re
        s = str(name).encode("ascii", errors="ignore").decode("ascii")
        s = s.replace(" ", "_")
        # Remove chars that break SWMM's space-delimited parser (parens, commas, etc.)
        s = re.sub(r"[^A-Za-z0-9_\-\.]", "_", s)
        # Collapse repeated underscores and strip leading/trailing underscores
        s = re.sub(r"_+", "_", s).strip("_") or "X"
        return s[:max_len]

    @staticmethod
    def _safe_float(val, default=0.0):
        """Parse float, handling Vietnamese format: '+7,33', '0,5', '+7,1 ; +8,52'."""
        try:
            s = str(val).strip()
            if not s:
                return default
            # Compound values: take first value before semicolon
            if ";" in s:
                s = s.split(";")[0].strip()
            s = s.lstrip("+").replace(",", ".")
            return float(s)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _haversine(lon1, lat1, lon2, lat2):
        """Great-circle distance in metres between two WGS-84 points."""
        from math import radians, cos, sin, asin, sqrt
        lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        return 6371000 * 2 * asin(sqrt(a))

    @staticmethod
    def _point_to_segment_distance(px, py, ax, ay, bx, by):
        """Distance from point P to segment AB in meters, plus projection.

        Uses flat-earth approximation (cos(lat) scaling) — adequate for
        distances under 1 km.

        Returns:
            (distance_m, proj_lon, proj_lat, fraction) where fraction is
            0.0-1.0 position along segment (clamped).
        """
        from math import radians, cos, sin, asin, sqrt

        # Convert to local metric coordinates (flat-earth)
        mid_lat = radians((py + ay + by) / 3.0)
        m_per_deg_lon = 111320.0 * cos(mid_lat)
        m_per_deg_lat = 110540.0

        # Segment AB in metres
        ax_m = ax * m_per_deg_lon
        ay_m = ay * m_per_deg_lat
        bx_m = bx * m_per_deg_lon
        by_m = by * m_per_deg_lat
        px_m = px * m_per_deg_lon
        py_m = py * m_per_deg_lat

        dx = bx_m - ax_m
        dy = by_m - ay_m
        seg_len_sq = dx * dx + dy * dy

        if seg_len_sq < 1e-12:
            # Degenerate segment
            dist = sqrt((px_m - ax_m) ** 2 + (py_m - ay_m) ** 2)
            return dist, ax, ay, 0.0

        t = max(0.0, min(1.0, ((px_m - ax_m) * dx + (py_m - ay_m) * dy) / seg_len_sq))
        proj_x_m = ax_m + t * dx
        proj_y_m = ay_m + t * dy

        dist = sqrt((px_m - proj_x_m) ** 2 + (py_m - proj_y_m) ** 2)
        proj_lon = proj_x_m / m_per_deg_lon
        proj_lat = proj_y_m / m_per_deg_lat

        return dist, proj_lon, proj_lat, t

    # =========================================================
    # DEM elevation lookup
    # =========================================================

    def _load_dem(self):
        """Open DEM raster and cache band/geotransform for point sampling."""
        if not self.dem_path or not os.path.exists(self.dem_path):
            return
        from osgeo import gdal
        ds = gdal.Open(self.dem_path)
        if not ds:
            print(f"  WARNING: cannot open DEM {self.dem_path}")
            return
        self._dem_ds = ds
        self._dem_gt = ds.GetGeoTransform()
        self._dem_band = ds.GetRasterBand(1)
        self._dem_nodata = self._dem_band.GetNoDataValue()
        print(f"  DEM loaded: {ds.RasterXSize}x{ds.RasterYSize} pixels")

    def _sample_dem(self, lon, lat):
        """Return ground-surface elevation (m) at (lon, lat), or None."""
        if self._dem_band is None:
            return None
        import math
        gt = self._dem_gt
        px = int((lon - gt[0]) / gt[1])
        py = int((lat - gt[3]) / gt[5])
        if px < 0 or py < 0 or px >= self._dem_ds.RasterXSize or py >= self._dem_ds.RasterYSize:
            return None
        val = self._dem_band.ReadAsArray(px, py, 1, 1)
        if val is None:
            return None
        elev = float(val[0, 0])
        if self._dem_nodata is not None and not math.isnan(self._dem_nodata) and elev == self._dem_nodata:
            return None
        if math.isnan(elev):
            return None
        return elev

    def _refine_elevations(self, junctions_layer, storage_layer, outfalls_layer):
        """Refine node elevations using DEM surface data.

        For JUNCTIONS/STORAGE: Elevation = DEM_surface - MaxDepth
        For OUTFALLS: Elevation = DEM_surface

        Skips nodes where DEM returns no-data.
        """
        if self._dem_band is None:
            return

        print("\n[DEM elevation refinement]")
        stats = {}

        for layer, depth_field, elev_field in [
            (junctions_layer, "MaxDepth", "Elevation"),
            (storage_layer, "MaxDepth", "Elevation"),
            (outfalls_layer, None, "Elevation"),
        ]:
            if layer is None or layer.featureCount() == 0:
                continue
            refined = 0
            layer.startEditing()
            for feat in layer.getFeatures():
                pt = feat.geometry().asPoint()
                dem_elev = self._sample_dem(pt.x(), pt.y())
                if dem_elev is None:
                    continue
                if depth_field:
                    max_depth = feat.attribute(depth_field) or 0.0
                    invert = dem_elev - max_depth
                else:
                    invert = dem_elev
                feat.setAttribute(elev_field, round(invert, 3))
                layer.updateFeature(feat)
                refined += 1
            layer.commitChanges()
            lname = layer.name()
            stats[lname] = (refined, layer.featureCount())
            print(f"  {lname}: {refined}/{layer.featureCount()} refined")

        total_r = sum(v[0] for v in stats.values())
        total_n = sum(v[1] for v in stats.values())
        print(f"  Total: {total_r}/{total_n} nodes refined from DEM")

    def _point_in_bbox(self, lon, lat):
        """Check if a point falls within the configured bounding box."""
        if self.bbox is None:
            return True
        min_lon, min_lat, max_lon, max_lat = self.bbox
        return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat

    def _linestring_in_bbox(self, coords):
        """Check if any point of a LineString falls within the bounding box."""
        if self.bbox is None:
            return True
        return any(self._point_in_bbox(c[0], c[1]) for c in coords)

    # =========================================================
    # Coordinate-based junction registry & manhole index
    # =========================================================

    def _build_manhole_index(self):
        """Build coordinate → manhole-data mapping from manholes CSV.

        Returns dict: {(round(lon,6), round(lat,6)): {name, elevation, max_depth, sewer_line}}
        """
        index = {}
        if not os.path.exists(self.manholes_csv):
            return index
        rows = self._read_csv(self.manholes_csv)
        for row in rows:
            gtype, coords = self._parse_geojson(row.get("Shape", ""))
            if gtype != "Point":
                continue
            lon, lat = coords[0], coords[1]
            if not self._point_in_bbox(lon, lat):
                continue
            inv_elev = self._safe_float(row.get("InvElev_m"), 5.0)
            rim_elev = self._safe_float(row.get("RimElev_m"), inv_elev + 3.0)
            key = (round(lon, 6), round(lat, 6))
            index[key] = {
                "name": self._swmm_name(row["Name"]),
                "elevation": inv_elev,
                "max_depth": rim_elev - inv_elev,
                "sewer_line": row.get("SewerLine", "").strip(),
            }
        return index

    def _build_lake_index(self):
        """Build name → (lon, lat, data) mapping from lakes CSV.

        Returns dict: {name_lower: {name, lon, lat, bed_elev, bank_elev, area_ha}}
        """
        index = {}
        if not os.path.exists(self.lakes_csv):
            return index
        rows = self._read_csv(self.lakes_csv)
        for row in rows:
            gtype, coords = self._parse_geojson(row.get("Shape", ""))
            if gtype != "Point":
                continue
            lon, lat = coords[0], coords[1]
            if not self._point_in_bbox(lon, lat):
                continue
            name = row.get("Name", "").strip()
            if not name:
                continue
            index[name.lower()] = {
                "name": self._swmm_name(name),
                "lon": lon,
                "lat": lat,
                "bed_elev": self._safe_float(row.get("BedElev_m"), 3.0),
                "bank_elev": self._safe_float(row.get("BankElev_m"), 6.0),
                "area_ha": self._safe_float(row.get("Area_ha"), 1.0),
            }
        return index

    def _build_outfall_index(self):
        """Build name → (lon, lat) mapping from outfalls CSV.

        Returns dict: {name_lower: {name, lon, lat, sewer_line}}
        """
        index = {}
        if not os.path.exists(self.outfalls_csv):
            return index
        rows = self._read_csv(self.outfalls_csv)
        for row in rows:
            gtype, coords = self._parse_geojson(row.get("Shape", ""))
            if gtype != "Point":
                continue
            lon, lat = coords[0], coords[1]
            if not self._point_in_bbox(lon, lat):
                continue
            name = row.get("Name", "").strip()
            if not name:
                continue
            index[name.lower()] = {
                "name": self._swmm_name(name),
                "lon": lon,
                "lat": lat,
                "sewer_line": row.get("SewerLine", "").strip(),
            }
        return index

    @staticmethod
    def _find_nearest_junction_on_route(coord_registry, lon, lat, route_name):
        """Find nearest junction on a specific route in coord_registry.

        Only considers junctions whose 'route' field matches route_name.
        Returns (junction_name, dist_m) or (None, inf).
        """
        import math
        best_name = None
        best_dist = float("inf")
        R = 6371000
        lat1 = math.radians(lat)
        lon1 = math.radians(lon)
        route_lower = route_name.lower().strip() if route_name else ""
        for (jlon, jlat), info in coord_registry.items():
            j_route = info.get("route", "").lower().strip()
            if route_lower and j_route and route_lower != j_route:
                continue
            lat2 = math.radians(jlat)
            lon2 = math.radians(jlon)
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            a = (math.sin(dlat / 2) ** 2
                 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2)
            d = 2 * R * math.asin(math.sqrt(a))
            if d < best_dist:
                best_dist = d
                best_name = info["name"]
        return best_name, best_dist

    def _build_congdap_spatial_index(self, congdap_csv, canal_csv,
                                     snap_tolerance_m=10.0):
        """Match congdap points to nearest canal segments by proximity.

        For each congdap point, finds the nearest canal LineString segment
        within snap_tolerance_m. Matched congdap are integrated inline into
        canal decomposition; unmatched ones become standalone weirs.

        Args:
            congdap_csv: Path to congdap CSV file.
            canal_csv: Path to canal CSV file.
            snap_tolerance_m: Maximum snap distance in metres.

        Returns:
            (congdap_index, matched_ids, unmatched_rows) where:
            - congdap_index: {(canal_fid, seg_idx): [matches sorted by fraction]}
              Each match is a dict with keys: congdap_row, proj_lon, proj_lat, fraction
            - matched_ids: set of matched congdap ID strings
            - unmatched_rows: list of unmatched congdap CSV rows
        """
        from math import radians, cos
        from collections import defaultdict

        congdap_index = defaultdict(list)
        matched_ids = set()
        unmatched_rows = []

        if not os.path.exists(congdap_csv) or not os.path.exists(canal_csv):
            return dict(congdap_index), matched_ids, unmatched_rows

        congdap_rows = self._read_csv(congdap_csv)
        canal_rows = self._read_csv(canal_csv)

        # Pre-parse canal LineStrings (bbox-filtered) → list of (fid, coords)
        canal_features = []
        for row_idx, row in enumerate(canal_rows):
            gtype, coords = self._parse_geojson(row.get("RouteShape", ""))
            if gtype != "LineString" or len(coords) < 2:
                continue
            if not self._linestring_in_bbox(coords):
                continue
            fid = row_idx + 1  # 1-based, matches _decompose_linestrings
            canal_features.append((fid, coords))

        # Approximate tolerance in degrees for bounding-box pre-filter
        tol_lat = snap_tolerance_m / 110540.0

        for cd_row in congdap_rows:
            gtype, coords = self._parse_geojson(cd_row.get("Shape", ""))
            if gtype != "Point":
                continue
            px, py = coords[0], coords[1]
            if not self._point_in_bbox(px, py):
                continue

            tol_lon = snap_tolerance_m / (111320.0 * cos(radians(py)))

            best_dist = float("inf")
            best_match = None

            for fid, canal_coords in canal_features:
                for si in range(len(canal_coords) - 1):
                    ax, ay = canal_coords[si][0], canal_coords[si][1]
                    bx, by = canal_coords[si + 1][0], canal_coords[si + 1][1]

                    # Bounding-box pre-filter on segment
                    seg_min_lon = min(ax, bx) - tol_lon
                    seg_max_lon = max(ax, bx) + tol_lon
                    seg_min_lat = min(ay, by) - tol_lat
                    seg_max_lat = max(ay, by) + tol_lat
                    if px < seg_min_lon or px > seg_max_lon:
                        continue
                    if py < seg_min_lat or py > seg_max_lat:
                        continue

                    dist, proj_lon, proj_lat, frac = self._point_to_segment_distance(
                        px, py, ax, ay, bx, by)

                    if dist < best_dist:
                        best_dist = dist
                        best_match = {
                            "congdap_row": cd_row,
                            "proj_lon": proj_lon,
                            "proj_lat": proj_lat,
                            "fraction": frac,
                            "canal_fid": fid,
                            "segment_idx": si,
                        }

            if best_match and best_dist <= snap_tolerance_m:
                key = (best_match["canal_fid"], best_match["segment_idx"])
                congdap_index[key].append(best_match)
                matched_ids.add(cd_row.get("ID", ""))
            else:
                unmatched_rows.append(cd_row)

        # Sort matches per segment by fraction (upstream → downstream)
        for key in congdap_index:
            congdap_index[key].sort(key=lambda m: m["fraction"])

        return dict(congdap_index), matched_ids, unmatched_rows

    @staticmethod
    def _get_or_create_junction(coord_registry, lon, lat, name_candidate,
                                elevation=0.0, max_depth=3.0):
        """Get existing or register new junction at (lon, lat).

        Uses coordinate-based deduplication (~0.11m precision).
        Returns junction name.
        """
        key = (round(lon, 6), round(lat, 6))
        if key in coord_registry:
            return coord_registry[key]["name"]
        coord_registry[key] = {
            "name": name_candidate,
            "elevation": elevation,
            "max_depth": max_depth,
        }
        return name_candidate

    @staticmethod
    def _find_nearest_junction(coord_registry, lon, lat):
        """Find the nearest junction in coord_registry to (lon, lat).

        Uses Haversine-approximated distance. Returns (junction_name, dist_m)
        or (None, inf) if registry is empty.
        """
        import math
        best_name = None
        best_dist = float("inf")
        R = 6371000  # Earth radius in metres
        lat1 = math.radians(lat)
        lon1 = math.radians(lon)
        for (jlon, jlat), info in coord_registry.items():
            lat2 = math.radians(jlat)
            lon2 = math.radians(jlon)
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            a = (math.sin(dlat / 2) ** 2
                 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2)
            d = 2 * R * math.asin(math.sqrt(a))
            if d < best_dist:
                best_dist = d
                best_name = info["name"]
        return best_name, best_dist

    # =========================================================
    # QGIS layer factories
    # =========================================================

    @staticmethod
    def _point_layer(name, fields):
        layer = QgsVectorLayer("Point?crs=epsg:4326", name, "memory")
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()
        return layer

    @staticmethod
    def _line_layer(name, fields):
        layer = QgsVectorLayer("LineString?crs=epsg:4326", name, "memory")
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()
        return layer

    def _junction_fields(self):
        return [
            QgsField("Name", QVariant.String, len=150),
            QgsField("Elevation", QVariant.Double),
            QgsField("MaxDepth", QVariant.Double),
            QgsField("InitDepth", QVariant.Double),
            QgsField("SurDepth", QVariant.Double),
            QgsField("Aponded", QVariant.Double),
        ]

    def _conduit_fields(self):
        return [
            QgsField("Name", QVariant.String, len=150),
            QgsField("FromNode", QVariant.String, len=150),
            QgsField("ToNode", QVariant.String, len=150),
            QgsField("Length", QVariant.Double),
            QgsField("Roughness", QVariant.Double),
            QgsField("InOffset", QVariant.Double),
            QgsField("OutOffset", QVariant.Double),
            QgsField("InitFlow", QVariant.Double),
            QgsField("MaxFlow", QVariant.Double),
            QgsField("XsectShape", QVariant.String, len=30),
            QgsField("Geom1", QVariant.Double),
            QgsField("Geom2", QVariant.Double),
            QgsField("Geom3", QVariant.Double),
            QgsField("Geom4", QVariant.Double),
            QgsField("Barrels", QVariant.Int),
            QgsField("Culvert", QVariant.String, len=20),
            QgsField("Shp_Trnsct", QVariant.String, len=20),
            QgsField("Kentry", QVariant.Double),
            QgsField("Kexit", QVariant.Double),
            QgsField("Kavg", QVariant.Double),
            QgsField("FlapGate", QVariant.String, len=10),
            QgsField("Seepage", QVariant.Double),
        ]

    def _link_from_point(self, lon, lat):
        """Short LineString from a Point for point-based link components."""
        return QgsGeometry.fromPolylineXY([
            QgsPointXY(lon, lat),
            QgsPointXY(lon + self.LINK_OFFSET, lat),
        ])

    def _weir_fields(self):
        """SWMM WEIRS layer field definitions."""
        return [
            QgsField("Name", QVariant.String, len=150),
            QgsField("FromNode", QVariant.String, len=150),
            QgsField("ToNode", QVariant.String, len=150),
            QgsField("Type", QVariant.String, len=20),
            QgsField("CrestHeigh", QVariant.Double),
            QgsField("Qcoeff", QVariant.Double),
            QgsField("FlapGate", QVariant.String, len=10),
            QgsField("EndContrac", QVariant.Double),
            QgsField("EndCoeff", QVariant.Double),
            QgsField("Surcharge", QVariant.String, len=10),
            QgsField("RoadWidth", QVariant.Double),
            QgsField("RoadSurf", QVariant.String, len=30),
            QgsField("CoeffCurve", QVariant.String, len=30),
            QgsField("Height", QVariant.Double),
            QgsField("Length", QVariant.Double),
            QgsField("SideSlope", QVariant.Double),
        ]

    def _build_weir_feature(self, layer, row, from_node, to_node, lon, lat):
        """Create a single SWMM WEIRS QgsFeature from a congdap CSV row.

        Args:
            layer: QgsVectorLayer whose fields define the feature schema.
            row: congdap CSV row dict.
            from_node: upstream junction name.
            to_node: downstream junction name.
            lon, lat: coordinates for the weir geometry.

        Returns:
            QgsFeature ready to add to the weir layer.
        """
        rid = row.get("ID", "")
        height = self._safe_float(row.get("Height_m"), 0.0)
        length = self._safe_float(row.get("Length_m"), 0.0)
        crest_elv = self._safe_float(row.get("CrestElv"), 0.0)
        feat = QgsFeature(layer.fields())
        feat.setGeometry(self._link_from_point(lon, lat))
        feat.setAttribute("Name", self._swmm_name(row["Name"], max_len=20) + f"_{rid}")
        feat.setAttribute("FromNode", from_node)
        feat.setAttribute("ToNode", to_node)
        feat.setAttribute("Type", "TRANSVERSE")
        feat.setAttribute("CrestHeigh", crest_elv)
        feat.setAttribute("Qcoeff", 1.84)
        feat.setAttribute("FlapGate", "NO")
        feat.setAttribute("EndContrac", 0.0)
        feat.setAttribute("EndCoeff", 0.0)
        feat.setAttribute("Surcharge", "NO")
        feat.setAttribute("RoadWidth", 0.0)
        feat.setAttribute("RoadSurf", "")
        feat.setAttribute("CoeffCurve", "")
        feat.setAttribute("Height", height if height > 0 else 0.5)
        feat.setAttribute("Length", length if length > 0 else 10.0)
        feat.setAttribute("SideSlope", 0.0)
        return feat

    # =========================================================
    # Node layer creators
    # =========================================================

    def create_junctions(self, csv_path=None):
        """Manholes → SWMM JUNCTIONS. Returns (layer, auto_junctions=[])."""
        csv_path = csv_path or self.manholes_csv
        rows = self._read_csv(csv_path)
        layer = self._point_layer("junctions", self._junction_fields())
        pr = layer.dataProvider()
        feats = []
        for row in rows:
            gtype, coords = self._parse_geojson(row.get("Shape", ""))
            if gtype != "Point":
                continue
            if not self._point_in_bbox(coords[0], coords[1]):
                continue
            inv_elev = self._safe_float(row.get("InvElev_m"), 5.0)
            rim_elev = self._safe_float(row.get("RimElev_m"), inv_elev + 3.0)
            feat = QgsFeature(layer.fields())
            feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(coords[0], coords[1])))
            feat.setAttribute("Name", self._swmm_name(row["Name"]))
            feat.setAttribute("Elevation", inv_elev)
            feat.setAttribute("MaxDepth", rim_elev - inv_elev)
            feat.setAttribute("InitDepth", 0.0)
            feat.setAttribute("SurDepth", 0.0)
            feat.setAttribute("Aponded", 0.0)
            feats.append(feat)
        pr.addFeatures(feats)
        layer.updateExtents()
        print(f"  JUNCTIONS: {layer.featureCount()} features")
        return layer, []

    def create_storage(self, csv_path=None):
        """Lakes → SWMM STORAGE (FUNCTIONAL type). Returns (layer, auto_junctions=[])."""
        csv_path = csv_path or self.lakes_csv
        rows = self._read_csv(csv_path)
        fields = [
            QgsField("Name", QVariant.String, len=150),
            QgsField("Elevation", QVariant.Double),
            QgsField("MaxDepth", QVariant.Double),
            QgsField("InitDepth", QVariant.Double),
            QgsField("Type", QVariant.String, len=30),
            QgsField("Curve", QVariant.String, len=30),
            QgsField("Coeff", QVariant.Double),
            QgsField("Exponent", QVariant.Double),
            QgsField("Constant", QVariant.Double),
            QgsField("MajorAxis", QVariant.Double),
            QgsField("MinorAxis", QVariant.Double),
            QgsField("SideSlope", QVariant.Double),
            QgsField("SurfHeight", QVariant.Double),
            QgsField("SurDepth", QVariant.Double),
            QgsField("Fevap", QVariant.Double),
            QgsField("Psi", QVariant.Double),
            QgsField("Ksat", QVariant.Double),
            QgsField("IMD", QVariant.Double),
        ]
        layer = self._point_layer("storages", fields)
        pr = layer.dataProvider()
        feats = []
        for row in rows:
            gtype, coords = self._parse_geojson(row.get("Shape", ""))
            if gtype != "Point":
                continue
            if not self._point_in_bbox(coords[0], coords[1]):
                continue
            bed_elev = self._safe_float(row.get("BedElev_m"), 3.0)
            bank_elev = self._safe_float(row.get("BankElev_m"), bed_elev + 3.0)
            wet_lvl = self._safe_float(row.get("WetLvl_m"), bed_elev + 1.0)
            area_ha = self._safe_float(row.get("Area_ha"), 1.0)
            feat = QgsFeature(layer.fields())
            feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(coords[0], coords[1])))
            feat.setAttribute("Name", self._swmm_name(row["Name"]))
            feat.setAttribute("Elevation", bed_elev)
            feat.setAttribute("MaxDepth", bank_elev - bed_elev)
            feat.setAttribute("InitDepth", max(0.0, wet_lvl - bed_elev))
            feat.setAttribute("Type", "FUNCTIONAL")
            feat.setAttribute("Curve", "")
            feat.setAttribute("Coeff", 0.0)
            feat.setAttribute("Exponent", 0.0)
            feat.setAttribute("Constant", area_ha * 10000.0)  # flat-bottom approx (m²)
            feat.setAttribute("MajorAxis", 0.0)
            feat.setAttribute("MinorAxis", 0.0)
            feat.setAttribute("SideSlope", 0.0)
            feat.setAttribute("SurfHeight", 0.0)
            feat.setAttribute("SurDepth", 0.0)
            feat.setAttribute("Fevap", 0.0)
            feat.setAttribute("Psi", 0.0)
            feat.setAttribute("Ksat", 0.0)
            feat.setAttribute("IMD", 0.0)
            feats.append(feat)
        pr.addFeatures(feats)
        layer.updateExtents()
        print(f"  STORAGE: {layer.featureCount()} features")
        return layer, []

    def create_outfalls(self, csv_path=None, coord_registry=None):
        """Create SWMM OUTFALLS layer from outfalls CSV.

        Args:
            csv_path: Path to outfalls CSV. Defaults to self.outfalls_csv.
            coord_registry: Junction coordinate registry. If provided and the
                outfall has a SewerLine attribute, the outfall replaces the
                nearest canal/sewer endpoint junction on that route: the
                outfall is placed at the junction's exact coordinates, the
                junction name is overwritten to the outfall name, and the old
                junction name is returned so it can be excluded from the
                JUNCTIONS layer.

        Returns:
            (layer, outfall_replaces) where outfall_replaces is a set of
            junction names that were replaced by outfalls (should be excluded
            from auto-junction creation).
        """
        csv_path = csv_path or self.outfalls_csv
        fields = [
            QgsField("Name", QVariant.String, len=150),
            QgsField("Elevation", QVariant.Double),
            QgsField("Type", QVariant.String, len=30),
            QgsField("FixedStage", QVariant.Double),
            QgsField("Curve_TS", QVariant.String, len=80),
            QgsField("FlapGate", QVariant.String, len=10),
            QgsField("RouteTo", QVariant.String, len=80),
        ]
        layer = self._point_layer("outfalls", fields)
        pr = layer.dataProvider()
        feats = []
        outfall_replaces = set()

        rows = self._read_csv(csv_path)
        for row in rows:
            gtype, coords = self._parse_geojson(row.get("Shape", ""))
            if gtype != "Point":
                continue
            lon, lat = coords[0], coords[1]
            if not self._point_in_bbox(lon, lat):
                continue

            name = row.get("Name", f"OF{row.get('ID', '0')}")
            swmm_name = self._swmm_name(name)
            elev = self._safe_float(row.get("Elev_m", "0"))
            typ = row.get("Type", "FREE").strip() or "FREE"
            fixed = self._safe_float(row.get("FixedStage", ""))
            flap = row.get("FlapGate", "NO").strip() or "NO"

            # Snap to nearest junction on SewerLine route.
            # The outfall adopts the junction's name so conduit references
            # (which already use that name) remain valid.
            place_lon, place_lat = lon, lat
            sewer_line = row.get("SewerLine", "").strip()
            if coord_registry and sewer_line:
                jname, dist = self._find_nearest_junction_on_route(
                    coord_registry, lon, lat, sewer_line)
                if jname:
                    for (jlon, jlat), info in coord_registry.items():
                        if info["name"] == jname:
                            place_lon, place_lat = jlon, jlat
                            break
                    outfall_replaces.add(jname)
                    swmm_name = jname  # adopt junction name
                    print(f"    {name}: replaces junction '{jname}' on "
                          f"route '{sewer_line}' (dist={dist:.1f}m)")
            # No SewerLine: outfall stays at its own CSV position

            feat = QgsFeature(layer.fields())
            feat.setGeometry(QgsGeometry.fromPointXY(
                QgsPointXY(place_lon, place_lat)))
            feat.setAttribute("Name", swmm_name)
            feat.setAttribute("Elevation", elev)
            feat.setAttribute("Type", typ)
            feat.setAttribute("FixedStage", fixed)
            feat.setAttribute("FlapGate", flap)
            feats.append(feat)

        pr.addFeatures(feats)
        layer.updateExtents()
        print(f"  OUTFALLS: {layer.featureCount()} features")
        return layer, outfall_replaces

    # =========================================================
    # Link layer creators
    # =========================================================

    def create_conduits(self, csv_path=None, coord_registry=None):
        """Sewers → SWMM CONDUITS with junction decomposition.

        Decomposes each sewer LineString into segments connected by junctions.
        At each endpoint/vertex, uses coord_registry for deduplication so that
        manholes, outfalls, and other sewers sharing the same position share
        the same junction node.

        Returns (layer, auto_junctions).
        """
        if coord_registry is None:
            coord_registry = {}
        csv_path = csv_path or self.sewers_csv
        rows = self._read_csv(csv_path)
        layer = self._line_layer("conduits", self._conduit_fields())
        pr = layer.dataProvider()
        feats = []
        auto_junctions = []

        for row in rows:
            gtype, coords = self._parse_geojson(row.get("RouteShape", ""))
            if gtype != "LineString" or len(coords) < 2:
                continue
            if not self._linestring_in_bbox(coords):
                continue

            sewer_name = row.get("Name", "").strip()
            from_node_csv = row.get("FromNode", "").strip()
            to_node_csv = row.get("ToNode", "").strip()

            # Parse cross-section
            xs_type = row.get("XSType", "CIRCULAR")
            diam_mm = row.get("Diam_mm", "")
            size_mm = row.get("Size_mm", "")
            if xs_type == "CIRCULAR" and diam_mm:
                geom1 = self._safe_float(diam_mm) / 1000.0
                geom2 = 0.0
            elif xs_type == "RECT_CLOSED" and size_mm:
                parts = str(size_mm).split("x")
                geom1 = self._safe_float(parts[0]) / 1000.0
                geom2 = self._safe_float(parts[1]) / 1000.0 if len(parts) > 1 else geom1
            else:
                geom1 = 0.4
                geom2 = 0.0
            roughness = self.ROUGHNESS.get(row.get("Material", ""), self.DEFAULT_ROUGHNESS)

            # Register junctions at each vertex, using coord_registry dedup
            junc_names = []
            for i, c in enumerate(coords):
                lon, lat = c[0], c[1]
                # For first/last vertex, prefer CSV FromNode/ToNode names
                if i == 0 and from_node_csv:
                    candidate = self._swmm_name(from_node_csv)
                elif i == len(coords) - 1 and to_node_csv:
                    candidate = self._swmm_name(to_node_csv)
                else:
                    candidate = self._swmm_name(f"SJ_{sewer_name}_{i}")
                jname = self._get_or_create_junction(
                    coord_registry, lon, lat, candidate,
                    elevation=0.0, max_depth=3.0)
                # Tag with sewer route for subcatchment outlet matching
                key = (round(lon, 6), round(lat, 6))
                if "route" not in coord_registry[key]:
                    coord_registry[key]["route"] = sewer_name
                junc_names.append(jname)
                auto_junctions.append((jname, lon, lat,
                                       coord_registry[key]["elevation"],
                                       coord_registry[key]["max_depth"]))

            # Create conduit segments between consecutive junctions
            for i in range(len(coords) - 1):
                lon1, lat1 = coords[i][0], coords[i][1]
                lon2, lat2 = coords[i + 1][0], coords[i + 1][1]
                seg_len = self._haversine(lon1, lat1, lon2, lat2)
                if seg_len < 0.01:
                    continue
                seg_name = self._swmm_name(f"{sewer_name}_S{i}")
                feat = self._make_conduit_feature(
                    layer, seg_name, junc_names[i], junc_names[i + 1],
                    lon1, lat1, lon2, lat2, seg_len,
                    roughness, xs_type, geom1, geom2, 0.0)
                feats.append(feat)

        pr.addFeatures(feats)
        layer.updateExtents()
        print(f"  CONDUITS (sewers): {layer.featureCount()} segments")
        return layer, auto_junctions

    def create_pumps(self, csv_path=None, coord_registry=None,
                     lake_index=None):
        """Pumps → SWMM PUMPS links.

        Pump is modelled as a link from Source (lake) to nearest sewer junction.
        - FromNode: lake position (looked up by Source attribute)
        - ToNode: pump position (snapped to nearest sewer junction)

        Falls back to auto-generated junctions if Source lake not found.

        Returns (layer, auto_junctions).
        """
        if coord_registry is None:
            coord_registry = {}
        if lake_index is None:
            lake_index = {}
        csv_path = csv_path or self.pumps_csv
        rows = self._read_csv(csv_path)
        fields = [
            QgsField("Name", QVariant.String, len=150),
            QgsField("FromNode", QVariant.String, len=150),
            QgsField("ToNode", QVariant.String, len=150),
            QgsField("PumpCurve", QVariant.String, len=80),
            QgsField("Status", QVariant.String, len=10),
            QgsField("Startup", QVariant.Double),
            QgsField("Shutoff", QVariant.Double),
        ]
        layer = self._line_layer("pumps", fields)
        pr = layer.dataProvider()
        feats = []
        auto_junctions = []
        for row in rows:
            gtype, coords = self._parse_geojson(row.get("Shape", ""))
            if gtype != "Point":
                continue
            lon, lat = coords[0], coords[1]
            if not self._point_in_bbox(lon, lat):
                continue

            pump_id = row.get("ID", "0")
            source_name = row.get("Source", "").strip()

            # FromNode: lake position if Source specified
            lake_info = lake_index.get(source_name.lower()) if source_name else None
            if lake_info:
                from_node = self._get_or_create_junction(
                    coord_registry, lake_info["lon"], lake_info["lat"],
                    f"LK_{lake_info['name']}",
                    elevation=lake_info["bed_elev"],
                    max_depth=lake_info["bank_elev"] - lake_info["bed_elev"])
                from_lon, from_lat = lake_info["lon"], lake_info["lat"]
                fkey = (round(from_lon, 6), round(from_lat, 6))
                auto_junctions.append((from_node, from_lon, from_lat,
                                       coord_registry[fkey]["elevation"],
                                       coord_registry[fkey]["max_depth"]))
                print(f"    Pump {row.get('Name','?')}: Source={source_name} -> {from_node}")
            else:
                from_node = self._swmm_name(f"PN{pump_id}_in")
                from_lon, from_lat = lon, lat
                auto_junctions.append((from_node, lon, lat, 0.0, 3.0))

            # ToNode: pump position, snapped to nearest existing junction
            to_jname = self._get_or_create_junction(
                coord_registry, lon, lat, f"PN{pump_id}_out",
                elevation=0.0, max_depth=3.0)
            tkey = (round(lon, 6), round(lat, 6))
            auto_junctions.append((to_jname, lon, lat,
                                   coord_registry[tkey]["elevation"],
                                   coord_registry[tkey]["max_depth"]))

            # Geometry: line from lake to pump
            feat = QgsFeature(layer.fields())
            feat.setGeometry(QgsGeometry.fromPolylineXY([
                QgsPointXY(from_lon, from_lat),
                QgsPointXY(lon, lat),
            ]))
            feat.setAttribute("Name", self._swmm_name(row["Name"], max_len=20) + f"_{pump_id}")
            feat.setAttribute("FromNode", from_node)
            feat.setAttribute("ToNode", to_jname)
            feat.setAttribute("PumpCurve", None)
            feat.setAttribute("Status", "ON")
            feat.setAttribute("Startup", 0.0)
            feat.setAttribute("Shutoff", 0.0)
            feats.append(feat)

        pr.addFeatures(feats)
        layer.updateExtents()
        print(f"  PUMPS: {layer.featureCount()} features")
        return layer, auto_junctions

    def create_orifices(self, csv_path=None, coord_registry=None,
                        lake_index=None):
        """Orifices → SWMM ORIFICES links with Receiver-based target resolution.

        FromNode: orifice position (snapped to nearest existing junction).
        ToNode: resolved from Receiver attribute:
            - If Receiver matches a lake name → lake's junction
            - Otherwise → nearest canal/river junction matching Receiver name

        Returns (layer, auto_junctions).
        """
        if coord_registry is None:
            coord_registry = {}
        if lake_index is None:
            lake_index = {}
        csv_path = csv_path or self.orifices_csv
        rows = self._read_csv(csv_path)
        fields = [
            QgsField("Name", QVariant.String, len=150),
            QgsField("FromNode", QVariant.String, len=150),
            QgsField("ToNode", QVariant.String, len=150),
            QgsField("Type", QVariant.String, len=20),
            QgsField("InOffset", QVariant.Double),
            QgsField("Qcoeff", QVariant.Double),
            QgsField("FlapGate", QVariant.String, len=10),
            QgsField("CloseTime", QVariant.Double),
            QgsField("XsectShape", QVariant.String, len=30),
            QgsField("Height", QVariant.Double),
            QgsField("Width", QVariant.Double),
        ]
        layer = self._line_layer("orifices", fields)
        pr = layer.dataProvider()
        feats = []
        auto_junctions = []
        for row in rows:
            gtype, coords = self._parse_geojson(row.get("Shape", ""))
            if gtype != "Point":
                continue
            lon, lat = coords[0], coords[1]
            if not self._point_in_bbox(lon, lat):
                continue

            orifice_id = row.get("ID", "0")
            receiver = row.get("Receiver", "").strip()

            # Resolve Receiver target first (determines FromNode strategy)
            to_lon, to_lat = lon + self.LINK_OFFSET, lat  # fallback
            to_node = f"OR{orifice_id}_dn"
            is_lake_target = False

            if receiver:
                lake_info = lake_index.get(receiver.lower())
                if lake_info:
                    # Receiver is a lake — use lake's junction
                    to_node = self._get_or_create_junction(
                        coord_registry, lake_info["lon"], lake_info["lat"],
                        f"LK_{lake_info['name']}",
                        elevation=lake_info["bed_elev"],
                        max_depth=lake_info["bank_elev"] - lake_info["bed_elev"])
                    to_lon, to_lat = lake_info["lon"], lake_info["lat"]
                    is_lake_target = True
                    print(f"    Orifice {row.get('Name','?')}: -> Lake {receiver}")
                else:
                    # Receiver is a canal/river — find nearest junction with matching route
                    jname, dist = self._find_nearest_junction_on_route(
                        coord_registry, lon, lat, receiver)
                    if jname and dist < 500:  # within 500m
                        to_node = jname
                        for (jlon, jlat), info in coord_registry.items():
                            if info["name"] == jname:
                                to_lon, to_lat = jlon, jlat
                                break
                        print(f"    Orifice {row.get('Name','?')}: -> {receiver} junction {jname} ({dist:.0f}m)")
                    else:
                        # Fallback: nearest any junction
                        jname, dist = self._find_nearest_junction(coord_registry, lon, lat)
                        if jname:
                            to_node = jname
                            for (jlon, jlat), info in coord_registry.items():
                                if info["name"] == jname:
                                    to_lon, to_lat = jlon, jlat
                                    break
                        print(f"    Orifice {row.get('Name','?')}: -> nearest {to_node} ({dist:.0f}m)")

            # FromNode: orifice position
            # For lake targets: snap to nearest existing junction (sewer endpoint)
            # For canal/river targets: always create own junction at an offset
            #   position so the orifice doesn't merge into an existing
            #   sewer/canal junction and disrupt the canal topology.
            #   Topology: sewer_end --- orifice link ---> canal_junction
            from_lon, from_lat = lon, lat
            if is_lake_target:
                from_node = self._get_or_create_junction(
                    coord_registry, lon, lat, f"OR{orifice_id}_up",
                    elevation=0.0, max_depth=3.0)
            else:
                # Force a unique junction for this orifice by using an offset
                # so it does not collide with any existing sewer/canal junction
                from_lon = lon - self.LINK_OFFSET
                from_node_name = self._swmm_name(
                    row.get("Name", f"OR{orifice_id}"))
                from_node = self._get_or_create_junction(
                    coord_registry, from_lon, from_lat, from_node_name,
                    elevation=0.0, max_depth=3.0)

            fkey = (round(from_lon, 6), round(from_lat, 6))
            auto_junctions.append((from_node, from_lon, from_lat,
                                   coord_registry[fkey]["elevation"],
                                   coord_registry[fkey]["max_depth"]))

            tkey = (round(to_lon, 6), round(to_lat, 6))
            if tkey not in coord_registry:
                coord_registry[tkey] = {"name": to_node, "elevation": 0.0, "max_depth": 3.0}
            auto_junctions.append((to_node, to_lon, to_lat,
                                   coord_registry[tkey]["elevation"],
                                   coord_registry[tkey]["max_depth"]))

            height = self._safe_float(row.get("Height_m"), 0.0)
            width = self._safe_float(row.get("Width_m"), 0.0)
            if height <= 0:
                height = 1.0
            if width <= 0:
                width = 1.0

            feat = QgsFeature(layer.fields())
            feat.setGeometry(QgsGeometry.fromPolylineXY([
                QgsPointXY(lon, lat),
                QgsPointXY(to_lon, to_lat),
            ]))
            feat.setAttribute("Name", self._swmm_name(row["Name"], max_len=20) + f"_{orifice_id}")
            feat.setAttribute("FromNode", from_node)
            feat.setAttribute("ToNode", to_node)
            feat.setAttribute("Type", "BOTTOM")
            feat.setAttribute("InOffset", self._safe_float(row.get("InvElev_m"), 0.0))
            feat.setAttribute("Qcoeff", self._safe_float(row.get("DischCoef"), 0.65))
            feat.setAttribute("FlapGate", "NO")
            feat.setAttribute("CloseTime", 0.0)
            feat.setAttribute("XsectShape", "RECT_CLOSED")
            feat.setAttribute("Height", height)
            feat.setAttribute("Width", width)
            feats.append(feat)

        pr.addFeatures(feats)
        layer.updateExtents()
        print(f"  ORIFICES: {layer.featureCount()} features")
        return layer, auto_junctions

    def create_weirs(self, csv_path=None, exclude_ids=None):
        """Congdap hydraulic structures → SWMM WEIRS links (standalone only).

        Args:
            csv_path: Path to congdap CSV.
            exclude_ids: Set of congdap ID strings already integrated inline
                into canal decomposition. These are skipped.

        Returns (layer, auto_junctions).
        """
        csv_path = csv_path or self.weirs_csv
        rows = self._read_csv(csv_path)
        layer = self._line_layer("standalone_weirs", self._weir_fields())
        pr = layer.dataProvider()
        feats = []
        auto_junctions = []
        for row in rows:
            gtype, coords = self._parse_geojson(row.get("Shape", ""))
            if gtype != "Point":
                continue
            lon, lat = coords[0], coords[1]
            if not self._point_in_bbox(lon, lat):
                continue
            rid = row.get("ID", "")
            if exclude_ids and rid in exclude_ids:
                continue
            from_node = f"CD{rid}_up"
            to_node = f"CD{rid}_dn"
            feats.append(self._build_weir_feature(
                layer, row, from_node, to_node, lon, lat))
            auto_junctions.append((from_node, lon, lat, 0.0, 3.0))
            auto_junctions.append((to_node, lon + self.LINK_OFFSET, lat, 0.0, 3.0))
        pr.addFeatures(feats)
        layer.updateExtents()
        print(f"  Standalone WEIRS: {layer.featureCount()} features")
        return layer, auto_junctions

    def _make_conduit_feature(self, layer, seg_name, from_node, to_node,
                              lon1, lat1, lon2, lat2, seg_len,
                              roughness, xs_type, depth, width, slope):
        """Create a single SWMM CONDUIT QgsFeature."""
        feat = QgsFeature(layer.fields())
        feat.setGeometry(QgsGeometry.fromPolylineXY([
            QgsPointXY(lon1, lat1), QgsPointXY(lon2, lat2),
        ]))
        feat.setAttribute("Name", seg_name)
        feat.setAttribute("FromNode", from_node)
        feat.setAttribute("ToNode", to_node)
        feat.setAttribute("Length", seg_len)
        feat.setAttribute("Roughness", roughness)
        feat.setAttribute("InOffset", 0.0)
        feat.setAttribute("OutOffset", 0.0)
        feat.setAttribute("InitFlow", 0.0)
        feat.setAttribute("MaxFlow", 0.0)
        feat.setAttribute("XsectShape", xs_type)
        feat.setAttribute("Geom1", depth)
        feat.setAttribute("Geom2", width)
        feat.setAttribute("Geom3", slope)
        feat.setAttribute("Geom4", slope)
        feat.setAttribute("Barrels", 1)
        return feat

    def _decompose_linestrings(self, csv_path, prefix, layer_name, xs_type,
                               roughness, coord_registry,
                               default_width=1.0, default_depth=0.5,
                               default_slope=1.0,
                               congdap_index=None, weir_layer=None):
        """Decompose LineString features into junctions + conduit segments.

        Each point on the LineString becomes a junction (coordinate-deduplicated),
        each segment between consecutive points becomes a conduit.

        When congdap_index is provided, matched congdap points are inserted
        inline as weirs, splitting the canal conduit at the congdap location.

        Args:
            csv_path: Path to standardized CSV with RouteShape column.
            prefix: Name prefix ("CN" for canals, "RN" for rivers).
            layer_name: QGIS layer name.
            xs_type: SWMM cross-section type ("TRAPEZOIDAL").
            roughness: Manning's n value.
            coord_registry: Shared dict for coordinate-based junction dedup.
            default_width, default_depth, default_slope: Fallback dimensions.
            congdap_index: Optional {(fid, seg_idx): [matches]} from
                _build_congdap_spatial_index(). When set, matched congdap
                are inserted as inline weirs.
            weir_layer: Optional QgsVectorLayer for collecting inline weir
                features. Required when congdap_index is provided.

        Returns:
            (layer, auto_junction_entries, inline_weir_feats,
             inline_weir_auto_junctions) where:
            - layer: CONDUITS QgsVectorLayer
            - auto_junction_entries: list of (name, lon, lat, elev, depth)
            - inline_weir_feats: list of QgsFeatures for the weir layer
            - inline_weir_auto_junctions: list of (name, lon, lat, elev, depth)
              for weir junction nodes
        """
        rows = self._read_csv(csv_path)
        layer = self._line_layer(layer_name, self._conduit_fields())
        pr = layer.dataProvider()
        feats = []
        auto_junctions = []
        inline_weir_feats = []
        inline_weir_aj = []
        total_segments = 0
        total_inline_weirs = 0
        skipped_zero = 0

        for row_idx, row in enumerate(rows):
            gtype, coords = self._parse_geojson(row.get("RouteShape", ""))
            if gtype != "LineString" or len(coords) < 2:
                continue
            if not self._linestring_in_bbox(coords):
                continue

            fid = row_idx + 1  # 1-based unique index
            # Parse physical dimensions
            width = self._safe_float(row.get("Width_m"), default_width)
            if width <= 0:
                width = default_width
            bed_elev = self._safe_float(row.get("BedElev_m"), 0.0)
            bank_elev = self._safe_float(row.get("BankElev_m"), 0.0)
            slope = self._safe_float(row.get("SlopCoef"), default_slope)
            if slope <= 0:
                slope = default_slope

            # Compute depth
            if bank_elev > bed_elev:
                depth = bank_elev - bed_elev
            else:
                depth = max(0.1, default_depth if default_depth > 0 else width / 2.0)

            # Register junctions for each point
            route_name = row.get("Name", "").strip()
            junc_names = []
            for i, c in enumerate(coords):
                lon, lat = c[0], c[1]
                candidate = f"{prefix}J{fid}_{i}"

                # For first/last vertex (canal endpoints), snap to nearby
                # existing junctions within 5m to merge canal branches
                if (i == 0 or i == len(coords) - 1) and coord_registry:
                    snap_name, snap_dist = self._find_nearest_junction(
                        coord_registry, lon, lat)
                    if snap_name and snap_dist < 5.0:
                        for (jlon, jlat), info in coord_registry.items():
                            if info["name"] == snap_name:
                                lon, lat = jlon, jlat
                                candidate = snap_name
                                break

                jname = self._get_or_create_junction(
                    coord_registry, lon, lat, candidate,
                    elevation=bed_elev, max_depth=depth,
                )
                junc_names.append(jname)
                key = (round(lon, 6), round(lat, 6))
                # Tag with route name for subcatchment/orifice/pump matching
                if "route" not in coord_registry[key] and route_name:
                    coord_registry[key]["route"] = route_name
                auto_junctions.append((jname, lon, lat,
                                       coord_registry[key]["elevation"],
                                       coord_registry[key]["max_depth"]))

            # --- Vertex-congdap pre-processing ---
            # When a congdap projects to a segment endpoint (fraction near
            # 0 or 1), CD_up would deduplicate with the existing canal
            # vertex junction, creating a branch instead of inline weir.
            # Fix: insert the weir AT the vertex and override the exit so
            # the next segment starts from CD_dn.
            ENDPOINT_FRAC = 0.01
            exit_override = {}   # vertex_idx → (name, lon, lat)
            mid_matches = {}     # (fid, seg_idx) → [mid-segment matches]

            if congdap_index:
                for seg_idx in range(len(coords) - 1):
                    raw = congdap_index.get((fid, seg_idx), [])
                    mids = []
                    for m in raw:
                        frac = m["fraction"]
                        if frac >= (1.0 - ENDPOINT_FRAC):
                            vertex = seg_idx + 1
                        elif frac <= ENDPOINT_FRAC:
                            vertex = seg_idx
                        else:
                            mids.append(m)
                            continue

                        # Insert weir at this vertex
                        cd_row = m["congdap_row"]
                        rid = cd_row.get("ID", "")
                        cd_dn_name = f"CD{rid}_dn"
                        v_lon = coords[vertex][0]
                        v_lat = coords[vertex][1]

                        # Chain with previous override at same vertex
                        if vertex in exit_override:
                            up_name, up_lon, up_lat = exit_override[vertex]
                        else:
                            up_name = junc_names[vertex]
                            up_lon, up_lat = v_lon, v_lat

                        cd_dn_lon = up_lon + self.LINK_OFFSET
                        cd_dn = self._get_or_create_junction(
                            coord_registry, cd_dn_lon, v_lat, cd_dn_name,
                            elevation=bed_elev, max_depth=depth)

                        # Also register CD_dn at the original vertex coords
                        # so that other canals branching here will merge to
                        # CD_dn instead of creating a disconnected junction.
                        v_key = (round(v_lon, 6), round(v_lat, 6))
                        coord_registry[v_key] = {
                            "name": cd_dn,
                            "elevation": bed_elev,
                            "max_depth": depth,
                            "route": route_name,
                        }

                        inline_weir_aj.append(
                            (up_name, up_lon, up_lat, bed_elev, depth))
                        inline_weir_aj.append(
                            (cd_dn, cd_dn_lon, v_lat, bed_elev, depth))

                        inline_weir_feats.append(self._build_weir_feature(
                            weir_layer, cd_row, up_name, cd_dn,
                            up_lon, up_lat))
                        total_inline_weirs += 1

                        exit_override[vertex] = (cd_dn, cd_dn_lon, v_lat)

                    if mids:
                        mid_matches[(fid, seg_idx)] = mids

            # Create conduit for each segment
            for i in range(len(coords) - 1):
                # Use exit_override for start if vertex was overridden
                if i in exit_override:
                    start_name, lon1, lat1 = exit_override[i]
                else:
                    start_name = junc_names[i]
                    lon1, lat1 = coords[i][0], coords[i][1]

                lon2, lat2 = coords[i + 1][0], coords[i + 1][1]
                end_name = junc_names[i + 1]

                seg_len = self._haversine(lon1, lat1, lon2, lat2)
                if seg_len < 0.01:
                    skipped_zero += 1
                    continue

                matches = mid_matches.get((fid, i), [])

                if not matches:
                    # Normal case: single conduit for this segment
                    seg_name = f"{prefix}{fid}_S{i}"
                    feats.append(self._make_conduit_feature(
                        layer, seg_name, start_name, end_name,
                        lon1, lat1, lon2, lat2, seg_len,
                        roughness, xs_type, depth, width, slope))
                    total_segments += 1
                else:
                    # Split segment with mid-segment inline weirs
                    prev_lon, prev_lat, prev_name = lon1, lat1, start_name
                    sub_idx = 0

                    for match in matches:
                        cd_row = match["congdap_row"]
                        rid = cd_row.get("ID", "")
                        p_lon, p_lat = match["proj_lon"], match["proj_lat"]

                        cd_up_name = f"CD{rid}_up"
                        cd_dn_name = f"CD{rid}_dn"
                        cd_dn_lon = p_lon + self.LINK_OFFSET

                        cd_up = self._get_or_create_junction(
                            coord_registry, p_lon, p_lat, cd_up_name,
                            elevation=bed_elev, max_depth=depth)
                        cd_dn = self._get_or_create_junction(
                            coord_registry, cd_dn_lon, p_lat, cd_dn_name,
                            elevation=bed_elev, max_depth=depth)

                        inline_weir_aj.append(
                            (cd_up, p_lon, p_lat, bed_elev, depth))
                        inline_weir_aj.append(
                            (cd_dn, cd_dn_lon, p_lat, bed_elev, depth))

                        # Conduit: prev → CD_up (upstream half)
                        sub_len = self._haversine(
                            prev_lon, prev_lat, p_lon, p_lat)
                        if sub_len >= 0.01:
                            seg_name = f"{prefix}{fid}_S{i}_{sub_idx}"
                            feats.append(self._make_conduit_feature(
                                layer, seg_name, prev_name, cd_up,
                                prev_lon, prev_lat, p_lon, p_lat, sub_len,
                                roughness, xs_type, depth, width, slope))
                            total_segments += 1
                            sub_idx += 1

                        # Weir: CD_up → CD_dn
                        inline_weir_feats.append(self._build_weir_feature(
                            weir_layer, cd_row, cd_up, cd_dn, p_lon, p_lat))
                        total_inline_weirs += 1

                        prev_lon, prev_lat, prev_name = cd_dn_lon, p_lat, cd_dn

                    # Final conduit: last CD_dn → segment end
                    sub_len = self._haversine(prev_lon, prev_lat, lon2, lat2)
                    if sub_len >= 0.01:
                        seg_name = f"{prefix}{fid}_S{i}_{sub_idx}"
                        feats.append(self._make_conduit_feature(
                            layer, seg_name, prev_name, end_name,
                            prev_lon, prev_lat, lon2, lat2, sub_len,
                            roughness, xs_type, depth, width, slope))
                        total_segments += 1

        pr.addFeatures(feats)
        layer.updateExtents()
        parts = [f"{layer_name}: {total_segments} conduit segments"]
        if total_inline_weirs > 0:
            parts.append(f"{total_inline_weirs} inline weirs")
        if skipped_zero > 0:
            parts.append(f"{skipped_zero} zero-length skipped")
        print(f"  {', '.join(parts)}")
        return layer, auto_junctions, inline_weir_feats, inline_weir_aj

    def create_river_conduits(self, csv_path=None, coord_registry=None):
        """Rivers → decomposed SWMM CONDUITS (TRAPEZOIDAL).

        Returns (layer, auto_junctions, [], []) — no inline weirs for rivers.
        """
        if coord_registry is None:
            coord_registry = {}
        return self._decompose_linestrings(
            csv_path=csv_path or self.rivers_csv,
            prefix="RN",
            layer_name="river_conduits",
            xs_type="TRAPEZOIDAL",
            roughness=0.035,
            coord_registry=coord_registry,
            default_width=5.0,
            default_depth=2.0,
            default_slope=1.0,
        )

    def create_canal_conduits(self, csv_path=None, coord_registry=None,
                              congdap_index=None, weir_layer=None):
        """Canals → decomposed SWMM CONDUITS (TRAPEZOIDAL) with inline weirs.

        Returns (layer, auto_junctions, inline_weir_feats, inline_weir_aj).
        """
        if coord_registry is None:
            coord_registry = {}
        return self._decompose_linestrings(
            csv_path=csv_path or self.canals_csv,
            prefix="CN",
            layer_name="canal_conduits",
            xs_type="TRAPEZOIDAL",
            roughness=0.025,
            coord_registry=coord_registry,
            default_width=1.0,
            default_depth=0.5,
            default_slope=1.0,
            congdap_index=congdap_index,
            weir_layer=weir_layer,
        )

    # =========================================================
    # Rain gages & subcatchments
    # =========================================================

    def create_raingages(self, csv_path=None):
        """Raingages → SWMM RAINGAGES (Point). Returns layer."""
        csv_path = csv_path or self.raingages_csv
        if not os.path.exists(csv_path):
            print("  RAINGAGES: 0 features (file not found)")
            return self._point_layer("raingages", [
                QgsField("Name", QVariant.String, len=150),
            ])
        rows = self._read_csv(csv_path)
        fields = [
            QgsField("Name", QVariant.String, len=150),
            QgsField("Format", QVariant.String, len=20),
            QgsField("Interval", QVariant.String, len=10),
            QgsField("SCF", QVariant.Double),
            QgsField("DataSource", QVariant.String, len=20),
            QgsField("SeriesName", QVariant.String, len=80),
            QgsField("StationID", QVariant.String, len=50),
            QgsField("RainUnits", QVariant.String, len=10),
            QgsField("FileName", QVariant.String, len=200),
        ]
        layer = self._point_layer("raingages", fields)
        pr = layer.dataProvider()
        feats = []
        for row in rows:
            gtype, coords = self._parse_geojson(row.get("Shape", ""))
            if gtype != "Point":
                continue
            if not self._point_in_bbox(coords[0], coords[1]):
                continue
            feat = QgsFeature(layer.fields())
            feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(coords[0], coords[1])))
            feat.setAttribute("Name", self._swmm_name(row["Name"]))
            feat.setAttribute("Format", row.get("Format", "VOLUME"))
            feat.setAttribute("Interval", row.get("Interval", "1:00"))
            feat.setAttribute("SCF", self._safe_float(row.get("SCF"), 1.0))
            feat.setAttribute("DataSource", row.get("DataSource", "TIMESERIES"))
            feat.setAttribute("SeriesName", row.get("SeriesName", ""))
            feat.setAttribute("StationID", row.get("StationID", ""))
            feat.setAttribute("RainUnits", row.get("RainUnits", "MM"))
            feat.setAttribute("FileName", "")
            feats.append(feat)
        pr.addFeatures(feats)
        layer.updateExtents()
        print(f"  RAINGAGES: {layer.featureCount()} features")
        return layer

    def create_subcatchments(self, csv_path=None, coord_registry=None):
        """Subcatchments → SWMM SUBCATCHMENTS (Polygon). Returns layer.

        Args:
            csv_path: Path to subcatchments CSV.
            coord_registry: Junction coordinate registry from canal/sewer
                decomposition. Used to find the nearest junction for each
                subcatchment's outlet coordinates (OutletLon, OutletLat).
                If None, falls back to polygon centroid lookup.
        """
        csv_path = csv_path or self.subcatchments_csv
        if not os.path.exists(csv_path):
            print("  SUBCATCHMENTS: 0 features (file not found)")
            return QgsVectorLayer("Polygon?crs=epsg:4326", "subcatchments", "memory")
        rows = self._read_csv(csv_path)
        fields = [
            QgsField("Name", QVariant.String, len=150),
            QgsField("RainGage", QVariant.String, len=150),
            QgsField("Outlet", QVariant.String, len=150),
            QgsField("Area", QVariant.Double),
            QgsField("Imperv", QVariant.Double),
            QgsField("Width", QVariant.Double),
            QgsField("Slope", QVariant.Double),
            QgsField("CurbLen", QVariant.Double),
            QgsField("SnowPack", QVariant.String, len=30),
            # SUBAREAS fields
            QgsField("N_Imperv", QVariant.Double),
            QgsField("N_Perv", QVariant.Double),
            QgsField("S_Imperv", QVariant.Double),
            QgsField("S_Perv", QVariant.Double),
            QgsField("PctZero", QVariant.Double),
            QgsField("RouteTo", QVariant.String, len=20),
            QgsField("PctRouted", QVariant.Double),
            # INFILTRATION fields (Modified Green-Ampt)
            QgsField("InfMethod", QVariant.String, len=30),
            QgsField("SuctHead", QVariant.Double),
            QgsField("Conductiv", QVariant.Double),
            QgsField("InitDef", QVariant.Double),
            # Additional infiltration fields (Horton/Curve Number)
            QgsField("MaxRate", QVariant.Double),
            QgsField("MinRate", QVariant.Double),
            QgsField("Decay", QVariant.Double),
            QgsField("DryTime", QVariant.Double),
            QgsField("MaxInf", QVariant.Double),
            QgsField("CurveNum", QVariant.Double),
        ]
        layer = QgsVectorLayer("Polygon?crs=epsg:4326", "subcatchments", "memory")
        layer.dataProvider().addAttributes(fields)
        layer.updateFields()
        pr = layer.dataProvider()
        feats = []
        for row in rows:
            gtype, coords = self._parse_geojson(row.get("Shape", ""))
            if gtype != "Polygon" or not coords:
                continue
            # Check bbox: include if any vertex is in bbox
            ring = coords[0]
            if self.bbox is not None:
                if not any(self._point_in_bbox(c[0], c[1]) for c in ring):
                    continue

            # Determine SWMM outlet junction by nearest-junction lookup
            # If SewerRoute is specified, restrict search to junctions on that route
            outlet_name = ""
            o_lon = self._safe_float(row.get("OutletLon"), None)
            o_lat = self._safe_float(row.get("OutletLat"), None)
            sewer_route = row.get("SewerRoute", "").strip()
            if o_lon is not None and o_lat is not None and coord_registry:
                if sewer_route:
                    jname, dist = self._find_nearest_junction_on_route(
                        coord_registry, o_lon, o_lat, sewer_route)
                    if jname:
                        outlet_name = jname
                        print(f"    {row.get('Name','?')}: outlet={jname} "
                              f"on route '{sewer_route}' (dist={dist:.1f}m)")
                    else:
                        # Fallback: no junction found on route, try any junction
                        jname, dist = self._find_nearest_junction(
                            coord_registry, o_lon, o_lat)
                        if jname:
                            outlet_name = jname
                            print(f"    {row.get('Name','?')}: outlet={jname} "
                                  f"(fallback, dist={dist:.1f}m)")
                else:
                    jname, dist = self._find_nearest_junction(
                        coord_registry, o_lon, o_lat)
                    if jname:
                        outlet_name = jname
                        print(f"    {row.get('Name','?')}: outlet={jname} "
                              f"(dist={dist:.1f}m)")

            feat = QgsFeature(layer.fields())
            qring = [QgsPointXY(c[0], c[1]) for c in ring]
            feat.setGeometry(QgsGeometry.fromPolygonXY([qring]))
            feat.setAttribute("Name", self._swmm_name(row["Name"]))
            feat.setAttribute("RainGage", self._swmm_name(row.get("RainGage", "")))
            feat.setAttribute("Outlet", outlet_name)
            feat.setAttribute("Area", self._safe_float(row.get("Area_ha"), 1.0))
            feat.setAttribute("Imperv", self._safe_float(row.get("Imperv_pct"), 25.0))
            feat.setAttribute("Width", self._safe_float(row.get("Width_m"), 100.0))
            feat.setAttribute("Slope", self._safe_float(row.get("Slope_pct"), 2.0))
            feat.setAttribute("CurbLen", self._safe_float(row.get("CurbLen_m"), 0.0))
            feat.setAttribute("SnowPack", "")
            feat.setAttribute("N_Imperv", self._safe_float(row.get("N_Imperv"), 0.015))
            feat.setAttribute("N_Perv", self._safe_float(row.get("N_Perv"), 0.15))
            feat.setAttribute("S_Imperv", self._safe_float(row.get("S_Imperv_mm"), 1.5))
            feat.setAttribute("S_Perv", self._safe_float(row.get("S_Perv_mm"), 5.0))
            feat.setAttribute("PctZero", self._safe_float(row.get("PctZero"), 25.0))
            feat.setAttribute("RouteTo", row.get("RouteTo", "OUTLET"))
            feat.setAttribute("PctRouted", self._safe_float(row.get("PctRouted"), 100.0))
            feat.setAttribute("InfMethod", row.get("InfMethod", "MODIFIED_GREEN_AMPT"))
            feat.setAttribute("SuctHead", self._safe_float(row.get("SuctHead_mm"), 150.0))
            feat.setAttribute("Conductiv", self._safe_float(row.get("Conductiv_mmh"), 25.0))
            feat.setAttribute("InitDef", self._safe_float(row.get("InitDef"), 0.25))
            feat.setAttribute("MaxRate", 0.0)
            feat.setAttribute("MinRate", 0.0)
            feat.setAttribute("Decay", 0.0)
            feat.setAttribute("DryTime", 0.0)
            feat.setAttribute("MaxInf", 0.0)
            feat.setAttribute("CurveNum", 0.0)
            feats.append(feat)
        pr.addFeatures(feats)
        layer.updateExtents()
        print(f"  SUBCATCHMENTS: {layer.featureCount()} features")
        return layer

    def create_timeseries_table(self, out_path=None):
        """Create TIMESERIES Excel table for rain data."""
        import openpyxl
        out_path = out_path or os.path.join(self.result_dir, "swmm_timeseries.xlsx")
        # Read raingage CSV to find referenced series names
        series_names = set()
        if os.path.exists(self.raingages_csv):
            rows = self._read_csv(self.raingages_csv)
            for row in rows:
                gtype, coords = self._parse_geojson(row.get("Shape", ""))
                if gtype != "Point":
                    continue
                if not self._point_in_bbox(coords[0], coords[1]):
                    continue
                sn = row.get("SeriesName", "")
                if sn:
                    series_names.add(sn)

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "TIMESERIES"
        ws.append(["Name", "Date", "Time", "Value", "File_Name"])

        # Generate a simple 24-hour storm event for each series
        # Matching simulation period: 01/01/2025 00:00 to 01/02/2025 00:00
        import datetime
        start = datetime.datetime(2025, 1, 1, 0, 0)
        # 24-hour storm pattern (mm/hr): light→peak→taper
        hourly_rain = [
            0.0, 0.0, 0.0, 0.0, 0.0, 0.5,   # 00-05
            1.0, 2.0, 5.0, 8.0, 12.0, 15.0,  # 06-11
            10.0, 6.0, 3.0, 2.0, 1.0, 0.5,   # 12-17
            0.2, 0.0, 0.0, 0.0, 0.0, 0.0,    # 18-23
        ]
        for sn in sorted(series_names) if series_names else ["TS_default"]:
            for hour, rain_val in enumerate(hourly_rain):
                dt = start + datetime.timedelta(hours=hour)
                ws.append([
                    sn,
                    dt.strftime("%m/%d/%Y"),
                    dt.strftime("%H:%M"),
                    rain_val,
                    "",
                ])

        wb.save(out_path)
        print(f"  TIMESERIES saved: {os.path.basename(out_path)} "
              f"({len(series_names)} series)")
        return out_path

    # =========================================================
    # Table helpers
    # =========================================================

    def create_options_table(self, out_path=None):
        """Create OPTIONS Excel table for SWMM simulation parameters."""
        import openpyxl
        out_path = out_path or os.path.join(self.result_dir, "swmm_options.xlsx")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Options"
        ws.append(["Option", "Value"])
        options = [
            ("FLOW_UNITS", "CMS"),
            ("INFILTRATION", "MODIFIED_GREEN_AMPT"),
            ("FLOW_ROUTING", "DYNWAVE"),
            ("LINK_OFFSETS", "DEPTH"),
            ("MIN_SLOPE", "0"),
            ("ALLOW_PONDING", "YES"),
            ("SKIP_STEADY_STATE", "NO"),
            ("START_DATE", "01/01/2025"),
            ("START_TIME", "00:00:00"),
            ("REPORT_START_DATE", "01/01/2025"),
            ("REPORT_START_TIME", "00:00:00"),
            ("END_DATE", "01/02/2025"),
            ("END_TIME", "00:00:00"),
            ("DRY_DAYS", "0"),
            ("REPORT_STEP", "00:05:00"),
            ("WET_STEP", "00:01:00"),
            ("DRY_STEP", "01:00:00"),
            ("ROUTING_STEP", "30"),
            ("INERTIAL_DAMPING", "PARTIAL"),
            ("NORMAL_FLOW_LIMITED", "BOTH"),
            ("FORCE_MAIN_EQUATION", "D-W"),
            ("VARIABLE_STEP", "0.75"),
            ("LENGTHENING_STEP", "0"),
            ("MIN_SURFAREA", "1.167"),
            ("MAX_TRIALS", "8"),
            ("HEAD_TOLERANCE", "0.0015"),
            ("SYS_FLOW_TOL", "5"),
            ("LAT_FLOW_TOL", "5"),
            ("THREADS", "1"),
        ]
        for opt, val in options:
            ws.append([opt, val])
        wb.save(out_path)
        print(f"  OPTIONS saved: {os.path.basename(out_path)}")
        return out_path

    # =========================================================
    # Auto-junction merge
    # =========================================================

    def _add_auto_junctions(self, junctions_layer, auto_junction_entries,
                            exclude_names=None):
        """Merge auto-generated nodes into JUNCTIONS layer (deduplicated by name).

        Args:
            junctions_layer: JUNCTIONS QgsVectorLayer.
            auto_junction_entries: list of (name, lon, lat, elevation, max_depth).
            exclude_names: set of junction names to skip (e.g. replaced by outfalls).
        """
        if exclude_names is None:
            exclude_names = set()
        existing = {f.attribute("Name") for f in junctions_layer.getFeatures()}
        seen = set(existing) | exclude_names
        pr = junctions_layer.dataProvider()
        feats = []
        for name, lon, lat, elevation, max_depth in auto_junction_entries:
            if name in seen:
                continue
            seen.add(name)
            feat = QgsFeature(junctions_layer.fields())
            feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon, lat)))
            feat.setAttribute("Name", name)
            feat.setAttribute("Elevation", elevation)
            feat.setAttribute("MaxDepth", max_depth)
            feat.setAttribute("InitDepth", 0.0)
            feat.setAttribute("SurDepth", 0.0)
            feat.setAttribute("Aponded", 0.0)
            feats.append(feat)
        if feats:
            pr.addFeatures(feats)
            junctions_layer.updateExtents()
        skipped = len(exclude_names)
        msg = f"  Auto-junctions added: {len(feats)} new ({len(seen)} total)"
        if skipped:
            msg += f" ({skipped} excluded as outfalls)"
        print(msg)

    # =========================================================
    # Main orchestration
    # =========================================================

    def run(self, inp_file=None):
        """Run full conversion: all standardized datasets → SWMM .inp file.

        Decomposes canal and river LineStrings into junction+conduit networks.
        All components are always included.

        Args:
            inp_file: Output path (defaults to result_dir/hanoi_sewer_sample.inp).

        Returns:
            Path to the generated .inp file.
        """
        inp_file = inp_file or os.path.join(self.result_dir, "hanoi_sewer_sample.inp")

        print("=" * 60)
        print("SWMM Conversion - All Standardized Datasets")
        print("=" * 60)

        # --- Load DEM for elevation lookup ---
        if self.dem_path:
            print("\n[DEM]")
            self._load_dem()

        # --- Build coordinate registry pre-seeded with manhole data ---
        print("\n[Coordinate registry]")
        manhole_index = self._build_manhole_index()
        coord_registry = {}
        for key, mh in manhole_index.items():
            coord_registry[key] = mh.copy()
        print(f"  Pre-seeded with {len(coord_registry)} manhole coordinates")

        all_auto = []

        # --- Node layers ---
        print("\n[Node layers]")
        junctions_layer, _ = self.create_junctions()
        storage_layer, _ = self.create_storage()

        # --- Link layers ---
        print("\n[Link layers]")
        conduits_layer, _ = self.create_conduits()
        pumps_layer, pj = self.create_pumps()
        orifices_layer, orj = self.create_orifices()
        all_auto += pj + orj

        # --- Congdap spatial index ---
        print("\n[Congdap spatial index]")
        congdap_index, matched_cd_ids, _unmatched = \
            self._build_congdap_spatial_index(self.weirs_csv, self.canals_csv)
        print(f"  Matched: {len(matched_cd_ids)} congdap → canal segments")
        print(f"  Unmatched: {len(_unmatched)} standalone weirs")

        # --- Decomposed canal/river conduits (canals with inline weirs) ---
        print("\n[Decomposed LineString conduits]")
        weirs_layer = self._line_layer("weirs", self._weir_fields())

        canal_layer, cj, inline_weir_feats, inline_weir_aj = \
            self.create_canal_conduits(
                coord_registry=coord_registry,
                congdap_index=congdap_index,
                weir_layer=weirs_layer)
        all_auto += cj + inline_weir_aj

        if inline_weir_feats:
            weirs_layer.dataProvider().addFeatures(inline_weir_feats)
            weirs_layer.updateExtents()

        conduits_layer.dataProvider().addFeatures(list(canal_layer.getFeatures()))
        conduits_layer.updateExtents()
        print(f"  Merged canals into CONDUITS → {conduits_layer.featureCount()} total")

        # Standalone weirs (unmatched congdap only)
        standalone_weir_layer, wj = self.create_weirs(exclude_ids=matched_cd_ids)
        all_auto += wj
        weirs_layer.dataProvider().addFeatures(list(standalone_weir_layer.getFeatures()))
        weirs_layer.updateExtents()
        print(f"  Total WEIRS: {weirs_layer.featureCount()} "
              f"({len(inline_weir_feats)} inline + "
              f"{standalone_weir_layer.featureCount()} standalone)")

        river_layer, rj, _, _ = self.create_river_conduits(coord_registry=coord_registry)
        all_auto += rj
        conduits_layer.dataProvider().addFeatures(list(river_layer.getFeatures()))
        conduits_layer.updateExtents()
        print(f"  Merged rivers into CONDUITS → {conduits_layer.featureCount()} total")

        # --- Outfalls ---
        print("\n[Outfall]")
        outfalls_layer, outfall_replaces = self.create_outfalls(
            coord_registry=coord_registry)

        # --- Merge auto-junctions ---
        print("\n[Merging auto-junctions]")
        self._add_auto_junctions(junctions_layer, all_auto,
                                 exclude_names=outfall_replaces)

        # --- DEM elevation refinement ---
        self._refine_elevations(junctions_layer, storage_layer, outfalls_layer)

        # --- OPTIONS table ---
        print("\n[Options table]")
        options_path = self.create_options_table()

        # --- QGIS project setup ---
        print("\n[QGIS project]")
        project = QgsProject.instance()
        for lyr in [junctions_layer, outfalls_layer, storage_layer,
                    conduits_layer, pumps_layer,
                    orifices_layer, weirs_layer]:
            project.addMapLayer(lyr)
        print("  Layers added to project")

        # --- Processing framework ---
        print("\n[Processing framework]")
        import processing
        from processing.core.Processing import Processing
        Processing.initialize()

        from generate_swmm_inp.generate_swmm_provider import GenerateSwmmProvider
        provider = GenerateSwmmProvider()
        QgsApplication.processingRegistry().addProvider(provider)
        print("  Plugin provider registered")

        # --- Run export ---
        print("\n[GenerateSwmmInpFile]")
        processing.run(
            "GenSwmmInp:GenerateSwmmInpFile",
            {
                "QGIS_OUT_INP_FILE": inp_file,
                "FILE_JUNCTIONS": junctions_layer,
                "FILE_OUTFALLS": outfalls_layer,
                "FILE_STORAGES": storage_layer,
                "FILE_CONDUITS": conduits_layer,
                "FILE_PUMPS": pumps_layer,
                "FILE_OUTLETS": self._line_layer("outlets", []),  # empty placeholder
                "FILE_ORIFICES": orifices_layer,
                "FILE_WEIRS": weirs_layer,
                "FILE_OPTIONS": options_path,
                "USE_Z_VALS": False,
            },
        )

        print("\n" + "=" * 60)
        if os.path.exists(inp_file):
            size = os.path.getsize(inp_file)
            print(f"SUCCESS: {inp_file}")
            print(f"   File size: {size:,} bytes")
        else:
            print("ERROR: .inp file was not created")
        print("=" * 60)

        return inp_file


def main():
    repo_dir = REPO_DIR
    conv = Conversion(
        dataset_dir=os.path.join(repo_dir, "dataset"),
        result_dir=os.path.join(repo_dir, "result", "swmm_output"),
        dem_path=os.path.join(repo_dir, "dataset", "dia_hinh_khong_gian",
                              "dem", "dem_compress.tif"),
    )
    conv.run()
    qgs.exitQgis()


if __name__ == "__main__":
    main()
