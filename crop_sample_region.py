"""
Crop all standardized datasets to a sample region bounding box.

Creates a `sample_region/` folder with the same structure as `dataset/`,
containing only features within the specified bbox.

Usage:
    conda run -n qgis-env python crop_sample_region.py
"""

import csv
import json
import os

REPO_DIR = os.path.abspath(os.path.dirname(__file__))
DATASET_DIR = os.path.join(REPO_DIR, "dataset")
OUTPUT_DIR = os.path.join(REPO_DIR, "sample_region")

# Sample region bbox: HCM sub-area
# lat 11.09 - 11.16, lon 106.46 - 106.53
BBOX = (106.46, 11.09, 106.53, 11.16)  # (min_lon, min_lat, max_lon, max_lat)


def in_bbox(lon, lat):
    min_lon, min_lat, max_lon, max_lat = BBOX
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def parse_geojson(s):
    """Parse GeoJSON string → (type, coordinates) or (None, None)."""
    try:
        g = json.loads(s)
        return g["type"], g["coordinates"]
    except Exception:
        return None, None


def clip_linestring(coords):
    """Clip a LineString to bbox, returning list of clipped coordinate segments.

    Keeps only consecutive runs of points that are within the bbox.
    Each run becomes a separate LineString (list of coords).
    Segments that cross the bbox boundary are included if at least one
    endpoint is inside.

    Returns list of coordinate lists, each with >= 2 points.
    """
    if len(coords) < 2:
        return []

    # Build runs of consecutive in-bbox points
    segments = []
    current_run = []
    for i, c in enumerate(coords):
        if in_bbox(c[0], c[1]):
            # If starting a new run and previous point was outside,
            # include the previous point as the entry point
            if not current_run and i > 0:
                current_run.append(coords[i - 1])
            current_run.append(c)
        else:
            if current_run:
                # Include this point as the exit point
                current_run.append(c)
                if len(current_run) >= 2:
                    segments.append(current_run)
                current_run = []

    # Close any open run
    if len(current_run) >= 2:
        segments.append(current_run)

    return segments


def crop_csv(src_path, dst_path, shape_col, geom_type):
    """Read CSV, filter by bbox, write cropped CSV.

    For LineStrings, clips coordinates to bbox (splitting into multiple
    features if the original crosses in and out of the bbox).

    Args:
        src_path: Source CSV path.
        dst_path: Destination CSV path.
        shape_col: Column name containing GeoJSON geometry ("Shape" or "RouteShape").
        geom_type: Expected geometry type ("Point", "LineString", or "Polygon").

    Returns:
        (total, kept) counts.
    """
    if not os.path.exists(src_path):
        return 0, 0

    os.makedirs(os.path.dirname(dst_path), exist_ok=True)

    with open(src_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    kept = []
    for row in rows:
        gtype, coords = parse_geojson(row.get(shape_col, ""))
        if gtype is None:
            continue

        if geom_type == "Point" and gtype == "Point":
            if in_bbox(coords[0], coords[1]):
                kept.append(row)
        elif geom_type == "LineString" and gtype == "LineString":
            # Clip LineString to bbox — may produce multiple segments
            clipped = clip_linestring(coords)
            for seg_i, seg_coords in enumerate(clipped):
                new_row = dict(row)
                geojson = json.dumps({"type": "LineString", "coordinates": seg_coords})
                new_row[shape_col] = geojson
                # Update name to avoid duplicates when split
                if len(clipped) > 1 and "Name" in new_row:
                    new_row["Name"] = f"{row['Name']}_p{seg_i+1}"
                kept.append(new_row)
        elif geom_type == "Polygon" and gtype == "Polygon":
            # Include if any vertex of outer ring intersects bbox
            ring = coords[0] if coords else []
            if any(in_bbox(c[0], c[1]) for c in ring):
                kept.append(row)

    with open(dst_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(kept)

    return len(rows), len(kept)


def main():
    print("=" * 60)
    print("Cropping datasets to sample region")
    print(f"  BBOX: lon {BBOX[0]}-{BBOX[2]}, lat {BBOX[1]}-{BBOX[3]}")
    print(f"  Output: {OUTPUT_DIR}")
    print("=" * 60)

    # Define all datasets to crop: (subfolder, filename, shape_column, geom_type)
    datasets = [
        # Group 2: River/Lake/Canal Network
        ("mang_luoi_song_ho_kenh_muong", "canals.csv", "RouteShape", "LineString"),
        ("mang_luoi_song_ho_kenh_muong", "rivers.csv", "RouteShape", "LineString"),
        ("mang_luoi_song_ho_kenh_muong", "congdap.csv", "Shape", "Point"),
        ("mang_luoi_song_ho_kenh_muong", "lakes.csv", "Shape", "Point"),
        ("mang_luoi_song_ho_kenh_muong", "dams.csv", "Shape", "Point"),
        # Group 3: Urban Drainage
        ("thoat_nuoc", "manholes.csv", "Shape", "Point"),
        ("thoat_nuoc", "sewers.csv", "RouteShape", "LineString"),
        ("thoat_nuoc", "pumps.csv", "Shape", "Point"),
        ("thoat_nuoc", "outlets.csv", "Shape", "Point"),
        ("thoat_nuoc", "orifices.csv", "Shape", "Point"),
        # Group 4: Hydrology/Meteorology
        ("thuy_van", "raingages.csv", "Shape", "Point"),
        # Group 1: Topography (subcatchments)
        ("dia_hinh_khong_gian", "subcatchments.csv", "Shape", "Polygon"),
        # Group 5: Pollution Sources
        ("nguon_thai", "discharge.csv", "Shape", "Point"),
    ]

    # Create folder structure (mirror dataset/)
    folders = [
        "dia_hinh_khong_gian",
        "mang_luoi_song_ho_kenh_muong",
        "thoat_nuoc",
        "thuy_van",
        "nguon_thai",
    ]
    for folder in folders:
        os.makedirs(os.path.join(OUTPUT_DIR, folder), exist_ok=True)

    total_all = 0
    kept_all = 0

    for subfolder, filename, shape_col, geom_type in datasets:
        src = os.path.join(DATASET_DIR, subfolder, filename)
        dst = os.path.join(OUTPUT_DIR, subfolder, filename)
        total, kept = crop_csv(src, dst, shape_col, geom_type)
        total_all += total
        kept_all += kept
        status = f"{kept:>5} / {total:>5}" if total > 0 else "  N/A (file not found)"
        print(f"  {subfolder}/{filename:40s} {status}")

    print("-" * 60)
    print(f"  TOTAL: {kept_all:,} / {total_all:,} features kept ({kept_all/max(total_all,1)*100:.1f}%)")

    # Crop raster datasets (DEM, hillshade)
    print("\n[Raster datasets]")
    try:
        from osgeo import gdal
        gdal.UseExceptions()
        dem_src = os.path.join(DATASET_DIR, "dia_hinh_khong_gian", "dem")
        dem_dst = os.path.join(OUTPUT_DIR, "dia_hinh_khong_gian", "dem")
        os.makedirs(dem_dst, exist_ok=True)
        for name in ["dem_compress.tif", "hill_shade.tif"]:
            src = os.path.join(dem_src, name)
            dst = os.path.join(dem_dst, name)
            if not os.path.exists(src):
                print(f"  {name}: skipped (not found)")
                continue
            ds = gdal.Translate(
                dst, src,
                projWin=[BBOX[0], BBOX[3], BBOX[2], BBOX[1]],
                creationOptions=["COMPRESS=LZW"],
            )
            ds = None
            size = os.path.getsize(dst)
            print(f"  {name}: {size:,} bytes")
    except ImportError:
        print("  Skipped (GDAL not available)")

    print("=" * 60)


if __name__ == "__main__":
    main()
