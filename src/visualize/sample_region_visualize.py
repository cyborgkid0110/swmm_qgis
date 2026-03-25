"""
Visualize sample region: canals + rivers + congdap + pumps + raingages + subcatchments
on satellite basemap.
Run with: conda run -n qgis-env python src/visualize/sample_region_visualize.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
import matplotlib.patches as mpatches
import contextily as cx
from matplotlib.collections import PatchCollection

import csv
import json
import os

REPO_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SAMPLE_DIR = os.path.join(REPO_DIR, "sample_region")

CANALS_CSV  = os.path.join(SAMPLE_DIR, "mang_luoi_song_ho_kenh_muong", "canals.csv")
RIVERS_CSV  = os.path.join(SAMPLE_DIR, "mang_luoi_song_ho_kenh_muong", "rivers.csv")
CONGDAP_CSV = os.path.join(SAMPLE_DIR, "mang_luoi_song_ho_kenh_muong", "congdap.csv")
PUMPS_CSV   = os.path.join(SAMPLE_DIR, "thoat_nuoc", "pumps.csv")
RAINGAGES_CSV = os.path.join(SAMPLE_DIR, "thuy_van", "raingages.csv")
SUBCATCH_CSV  = os.path.join(SAMPLE_DIR, "dia_hinh_khong_gian", "subcatchments.csv")
OUT_PNG     = os.path.join(REPO_DIR, "result", "visualization", "sample_region.png")


def parse_geojson(s):
    try:
        g = json.loads(s)
        return g["type"], g["coordinates"]
    except Exception:
        return None, None


def load_linestrings(csv_path, shape_col="RouteShape"):
    """Load LineString features from CSV. Returns list of (coords, row_dict)."""
    features = []
    if not os.path.exists(csv_path):
        return features
    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            gtype, coords = parse_geojson(row.get(shape_col, ""))
            if gtype == "LineString" and len(coords) >= 2:
                features.append((coords, row))
    return features


def load_points(csv_path, shape_col="Shape"):
    """Load Point features from CSV. Returns list of (lon, lat, row_dict)."""
    features = []
    if not os.path.exists(csv_path):
        return features
    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            gtype, coords = parse_geojson(row.get(shape_col, ""))
            if gtype == "Point":
                features.append((coords[0], coords[1], row))
    return features


def load_polygons(csv_path, shape_col="Shape"):
    """Load Polygon features from CSV. Returns list of (ring_coords, row_dict)."""
    features = []
    if not os.path.exists(csv_path):
        return features
    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            gtype, coords = parse_geojson(row.get(shape_col, ""))
            if gtype == "Polygon" and coords:
                features.append((coords[0], row))  # outer ring
    return features


# == Load data =================================================================
print("Loading sample region data...")
canals = load_linestrings(CANALS_CSV)
rivers = load_linestrings(RIVERS_CSV)
congdap = load_points(CONGDAP_CSV)
pumps = load_points(PUMPS_CSV)
raingages = load_points(RAINGAGES_CSV)
subcatchments = load_polygons(SUBCATCH_CSV)
print(f"  Canals: {len(canals)}, Rivers: {len(rivers)}, "
      f"Congdap: {len(congdap)}, Pumps: {len(pumps)}, "
      f"Raingages: {len(raingages)}, Subcatchments: {len(subcatchments)}")


# == Colour helpers ============================================================
def canal_color(row):
    p = (row.get("Purpose") or "").lower()
    if "tuoi" in p:
        return "#00bfff"   # irrigation = cyan-blue
    elif "tieu" in p:
        return "#00ff88"   # drainage = bright green
    return "#ffaa00"       # other = amber


def congdap_color(row):
    s = (row.get("Type") or "").lower()
    if "u ti" in s:
        return "#ff4444"     # regulation = red
    elif "u k" in s:
        return "#44aaff"     # canal head/end = blue
    elif "qua" in s:
        return "#ffaa00"     # road crossing = orange
    elif "tieu" in s or "tiêu" in s:
        return "#00ff88"     # drainage = green
    elif "soát" in s or "soat" in s:
        return "#cc66ff"     # control = purple
    elif "ly" in s:
        return "#ff88cc"     # centrifugal = pink
    elif not s:
        return "#aaaaaa"     # unknown = grey
    return "#dddddd"         # other = light grey


# == Plot ======================================================================
print("Rendering...")
fig, ax = plt.subplots(1, 1, figsize=(16, 14))
fig.patch.set_facecolor("#1a1a2e")
ax.set_facecolor("#1a1a2e")
ax.set_aspect("equal")
ax.tick_params(colors="#cccccc", labelsize=8)
for sp in ax.spines.values():
    sp.set_edgecolor("#555555")

# Collect all coordinates for extent
all_lons = []
all_lats = []

# -- Draw subcatchments (bottom, semi-transparent polygons) --------------------
sc_colors = ["#ff6b6b", "#4ecdc4", "#ffe66d"]  # distinct fill colors per subcatchment
for i, (ring, row) in enumerate(subcatchments):
    xs = [c[0] for c in ring]
    ys = [c[1] for c in ring]
    color = sc_colors[i % len(sc_colors)]
    ax.fill(xs, ys, color=color, alpha=0.20, zorder=2)
    ax.plot(xs, ys, color=color, linewidth=1.2, alpha=0.7, zorder=2,
            linestyle="--")
    # Label at centroid
    cx_pt = sum(xs) / len(xs)
    cy_pt = sum(ys) / len(ys)
    name = row.get("Name", "")
    ax.text(cx_pt, cy_pt, name, color=color, fontsize=6, fontweight="bold",
            ha="center", va="center", zorder=8,
            bbox=dict(facecolor="#1a1a2ecc", edgecolor=color, pad=2, linewidth=0.5))
    all_lons.extend(xs)
    all_lats.extend(ys)

# -- Draw rivers (bottom, thicker) --------------------------------------------
for coords, row in rivers:
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    ax.plot(xs, ys, color="#4488ff", linewidth=1.5, alpha=0.9, zorder=3)
    all_lons.extend(xs)
    all_lats.extend(ys)

# -- Draw canals ---------------------------------------------------------------
for coords, row in canals:
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    color = canal_color(row)
    ax.plot(xs, ys, color=color, linewidth=0.8, alpha=0.9, zorder=4)
    all_lons.extend(xs)
    all_lats.extend(ys)

# -- Draw congdap (points) ----------------------------------------------------
if congdap:
    cd_lons = [p[0] for p in congdap]
    cd_lats = [p[1] for p in congdap]
    cd_colors = [congdap_color(p[2]) for p in congdap]
    ax.scatter(cd_lons, cd_lats, c=cd_colors, s=6, alpha=0.9,
              edgecolors="white", linewidths=0.2, zorder=6)
    all_lons.extend(cd_lons)
    all_lats.extend(cd_lats)

# -- Draw pumps (diamond markers) ---------------------------------------------
if pumps:
    pm_lons = [p[0] for p in pumps]
    pm_lats = [p[1] for p in pumps]
    ax.scatter(pm_lons, pm_lats, c="#ffff00", s=30, marker="D", alpha=1.0,
              edgecolors="white", linewidths=0.5, zorder=7, label="Pump station")
    all_lons.extend(pm_lons)
    all_lats.extend(pm_lats)

# -- Draw raingages (star markers) ---------------------------------------------
if raingages:
    rg_lons = [p[0] for p in raingages]
    rg_lats = [p[1] for p in raingages]
    ax.scatter(rg_lons, rg_lats, c="#00ffff", s=60, marker="*", alpha=1.0,
              edgecolors="white", linewidths=0.5, zorder=9)
    # Label each rain gage
    for lon, lat, row in raingages:
        name = row.get("Name", "")
        ax.annotate(name, (lon, lat), xytext=(5, 5), textcoords="offset points",
                    color="#00ffff", fontsize=7, fontweight="bold", zorder=9)
    all_lons.extend(rg_lons)
    all_lats.extend(rg_lats)

# -- Set extent and add satellite basemap --------------------------------------
pad = 0.003
ax.set_xlim(min(all_lons) - pad, max(all_lons) + pad)
ax.set_ylim(min(all_lats) - pad, max(all_lats) + pad)

try:
    print("Fetching satellite tiles...")
    cx.add_basemap(
        ax,
        crs="EPSG:4326",
        source=cx.providers.Esri.WorldImagery,
        zoom=14,
        zorder=0,
    )
    print("  Satellite basemap added")
except Exception as e:
    print(f"  Basemap skipped: {e}")

# -- Labels & legend -----------------------------------------------------------
ax.set_xlabel("Longitude", color="#cccccc", fontsize=10)
ax.set_ylabel("Latitude", color="#cccccc", fontsize=10)
ax.set_title(
    f"Sample Region - {len(canals)} Canals, {len(rivers)} Rivers, "
    f"{len(congdap)} Structures, {len(pumps)} Pumps, "
    f"{len(raingages)} Raingages, {len(subcatchments)} Subcatchments",
    color="#ffffff", fontsize=12, fontweight="bold", pad=12,
)

handles = [
    # rivers
    mlines.Line2D([], [], color="#4488ff", linewidth=2.0, label=f"River ({len(rivers)})"),
    # canals
    mlines.Line2D([], [], color="#00bfff", linewidth=1.5,
                  label=f"Canal - Irrigation ({sum(1 for _, r in canals if 'tuoi' in (r.get('Purpose') or '').lower())})"),
    mlines.Line2D([], [], color="#00ff88", linewidth=1.5,
                  label=f"Canal - Drainage ({sum(1 for _, r in canals if 'tieu' in (r.get('Purpose') or '').lower())})"),
    mlines.Line2D([], [], color="#ffaa00", linewidth=1.5,
                  label="Canal - Other"),
    # congdap
    mlines.Line2D([], [], marker="o", color="#ff4444", linestyle="None",
                  markersize=5, label="Regulation gate"),
    mlines.Line2D([], [], marker="o", color="#44aaff", linestyle="None",
                  markersize=5, label="Canal head/end gate"),
    mlines.Line2D([], [], marker="o", color="#ffaa00", linestyle="None",
                  markersize=5, label="Road crossing"),
    mlines.Line2D([], [], marker="o", color="#00ff88", linestyle="None",
                  markersize=5, label="Drainage gate"),
    mlines.Line2D([], [], marker="o", color="#cc66ff", linestyle="None",
                  markersize=5, label="Control gate"),
    # pumps
    mlines.Line2D([], [], marker="D", color="#ffff00", linestyle="None",
                  markersize=6, label=f"Pump station ({len(pumps)})"),
    # raingages
    mlines.Line2D([], [], marker="*", color="#00ffff", linestyle="None",
                  markersize=8, label=f"Rain gage ({len(raingages)})"),
    # subcatchments
    mlines.Line2D([], [], color="#ff6b6b", linewidth=1.5, linestyle="--",
                  label=f"Subcatchment ({len(subcatchments)})"),
]
ax.legend(handles=handles, loc="upper right",
          facecolor="#1a1a2edd", edgecolor="#555", labelcolor="#ffffff",
          fontsize=8, framealpha=0.9)

# info box
ax.text(0.02, 0.02,
        f"CRS: EPSG:4326\n"
        f"BBOX: 106.46-106.53, 11.09-11.16\n"
        f"Basemap: Esri World Imagery",
        transform=ax.transAxes, va="bottom", color="#cccccc",
        fontsize=8, bbox=dict(facecolor="#1a1a2ecc", edgecolor="#555", pad=5))

plt.tight_layout()
plt.savefig(OUT_PNG, dpi=600, bbox_inches="tight",
            facecolor=fig.get_facecolor())
plt.close()
print(f"Saved: {OUT_PNG}")
