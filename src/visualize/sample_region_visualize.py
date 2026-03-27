"""
Visualize sample region: canals + rivers + weirs + pumps + raingages + subcatchments
+ sewers + manholes + orifices + outfalls + lakes + discharge sources
on satellite basemap.
Run with: conda run -n qgis-env python src/visualize/sample_region_visualize.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
import matplotlib.patches as mpatches
import contextily as cx
from matplotlib.patches import Circle

import csv
import json
import os

REPO_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SAMPLE_DIR = os.path.join(REPO_DIR, "sample_region")

CANALS_CSV     = os.path.join(SAMPLE_DIR, "mang_luoi_song_ho_kenh_muong", "canals.csv")
RIVERS_CSV     = os.path.join(SAMPLE_DIR, "mang_luoi_song_ho_kenh_muong", "rivers.csv")
LAKES_CSV      = os.path.join(SAMPLE_DIR, "mang_luoi_song_ho_kenh_muong", "lakes.csv")
WEIRS_CSV      = os.path.join(SAMPLE_DIR, "thoat_nuoc", "weir.csv")
PUMPS_CSV      = os.path.join(SAMPLE_DIR, "thoat_nuoc", "pumps.csv")
SEWERS_CSV     = os.path.join(SAMPLE_DIR, "thoat_nuoc", "sewers.csv")
MANHOLES_CSV   = os.path.join(SAMPLE_DIR, "thoat_nuoc", "manholes.csv")
ORIFICES_CSV   = os.path.join(SAMPLE_DIR, "thoat_nuoc", "orifices.csv")
OUTFALLS_CSV   = os.path.join(SAMPLE_DIR, "thoat_nuoc", "outfalls.csv")
RAINGAGES_CSV  = os.path.join(SAMPLE_DIR, "thuy_van", "raingages.csv")
SUBCATCH_CSV   = os.path.join(SAMPLE_DIR, "dia_hinh_khong_gian", "subcatchments.csv")
DISCHARGE_CSV  = os.path.join(SAMPLE_DIR, "nguon_thai", "discharge.csv")
OUT_PNG        = os.path.join(REPO_DIR, "result", "visualization", "sample_region.png")


def parse_geojson(s):
    try:
        g = json.loads(s)
        return g["type"], g["coordinates"]
    except Exception:
        return None, None


def load_linestrings(csv_path, shape_col="RouteShape"):
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
    features = []
    if not os.path.exists(csv_path):
        return features
    with open(csv_path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            gtype, coords = parse_geojson(row.get(shape_col, ""))
            if gtype == "Polygon" and coords:
                features.append((coords[0], row))
    return features


# == Load data =================================================================
print("Loading sample region data...")
canals       = load_linestrings(CANALS_CSV)
rivers       = load_linestrings(RIVERS_CSV)
sewers       = load_linestrings(SEWERS_CSV)
lakes        = load_points(LAKES_CSV)
weirs        = load_points(WEIRS_CSV)
pumps        = load_points(PUMPS_CSV)
manholes     = load_points(MANHOLES_CSV)
orifices     = load_points(ORIFICES_CSV)
outfalls     = load_points(OUTFALLS_CSV)
raingages    = load_points(RAINGAGES_CSV)
discharge    = load_points(DISCHARGE_CSV)
subcatchments = load_polygons(SUBCATCH_CSV)

print(f"  Canals: {len(canals)}, Rivers: {len(rivers)}, Sewers: {len(sewers)}")
print(f"  Lakes: {len(lakes)}, Weirs: {len(weirs)}, Pumps: {len(pumps)}")
print(f"  Manholes: {len(manholes)}, Orifices: {len(orifices)}, Outfalls: {len(outfalls)}")
print(f"  Raingages: {len(raingages)}, Discharge: {len(discharge)}, Subcatchments: {len(subcatchments)}")


# == Colour helpers ============================================================
def canal_color(row):
    p = (row.get("Purpose") or "").lower()
    if "tuoi" in p:
        return "#00bfff"
    elif "tieu" in p:
        return "#00ff88"
    return "#ffaa00"


def weir_color(row):
    s = (row.get("Type") or "").lower()
    if "u ti" in s:
        return "#ff4444"
    elif "u k" in s:
        return "#44aaff"
    elif "qua" in s:
        return "#ffaa00"
    elif "tieu" in s or "tiêu" in s:
        return "#00ff88"
    elif "soát" in s or "soat" in s:
        return "#cc66ff"
    elif "ly" in s:
        return "#ff88cc"
    elif not s:
        return "#aaaaaa"
    return "#dddddd"


# == Plot ======================================================================
print("Rendering...")
fig, ax = plt.subplots(1, 1, figsize=(18, 16))
fig.patch.set_facecolor("#1a1a2e")
ax.set_facecolor("#1a1a2e")
ax.set_aspect("equal")
ax.tick_params(colors="#cccccc", labelsize=8)
for sp in ax.spines.values():
    sp.set_edgecolor("#555555")

all_lons = []
all_lats = []

# -- Draw subcatchments (bottom, semi-transparent polygons) --------------------
sc_colors = ["#ff6b6b", "#4ecdc4", "#ffe66d"]
for i, (ring, row) in enumerate(subcatchments):
    xs = [c[0] for c in ring]
    ys = [c[1] for c in ring]
    color = sc_colors[i % len(sc_colors)]
    ax.fill(xs, ys, color=color, alpha=0.15, zorder=2)
    ax.plot(xs, ys, color=color, linewidth=1.8, alpha=0.6, zorder=2, linestyle="--")
    cx_pt = sum(xs) / len(xs)
    cy_pt = sum(ys) / len(ys)
    name = row.get("Name", "")
    ax.text(cx_pt, cy_pt, name, color=color, fontsize=6, fontweight="bold",
            ha="center", va="center", zorder=8,
            bbox=dict(facecolor="#1a1a2ecc", edgecolor=color, pad=2, linewidth=0.5))
    all_lons.extend(xs)
    all_lats.extend(ys)

# -- Draw rivers ---------------------------------------------------------------
for coords, row in rivers:
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    ax.plot(xs, ys, color="#4488ff", linewidth=3.0, alpha=0.9, zorder=3)
    all_lons.extend(xs)
    all_lats.extend(ys)

# -- Draw canals ---------------------------------------------------------------
for coords, row in canals:
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    color = canal_color(row)
    ax.plot(xs, ys, color=color, linewidth=1.5, alpha=0.9, zorder=4)
    all_lons.extend(xs)
    all_lats.extend(ys)

# -- Draw sewers (dashed dark red, thinner) ------------------------------------
for coords, row in sewers:
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    ax.plot(xs, ys, color="#cc3333", linewidth=2.2, alpha=0.95, zorder=5,
            linestyle="--")
    all_lons.extend(xs)
    all_lats.extend(ys)

# -- Draw weirs ----------------------------------------------------------------
if weirs:
    wd_lons = [p[0] for p in weirs]
    wd_lats = [p[1] for p in weirs]
    wd_colors = [weir_color(p[2]) for p in weirs]
    ax.scatter(wd_lons, wd_lats, c=wd_colors, s=18, alpha=0.85,
               edgecolors="white", linewidths=0.4, zorder=6)
    all_lons.extend(wd_lons)
    all_lats.extend(wd_lats)

# -- Draw lakes (filled circles) -----------------------------------------------
if lakes:
    for lon, lat, row in lakes:
        ax.scatter([lon], [lat], c="#3399ff", s=250, marker="o", alpha=0.9,
                   edgecolors="#aaddff", linewidths=1.5, zorder=7)
        name = row.get("Name", "")
        if name:
            ax.annotate(name, (lon, lat), xytext=(6, 6), textcoords="offset points",
                        color="#aaddff", fontsize=7, fontweight="bold", zorder=9)
        all_lons.append(lon)
        all_lats.append(lat)

# -- Draw manholes (small squares) ---------------------------------------------
if manholes:
    mh_lons = [p[0] for p in manholes]
    mh_lats = [p[1] for p in manholes]
    ax.scatter(mh_lons, mh_lats, c="#ff9900", s=35, marker="s", alpha=0.9,
               edgecolors="white", linewidths=0.5, zorder=8)
    all_lons.extend(mh_lons)
    all_lats.extend(mh_lats)

# -- Draw orifices (triangle markers) ------------------------------------------
if orifices:
    or_lons = [p[0] for p in orifices]
    or_lats = [p[1] for p in orifices]
    ax.scatter(or_lons, or_lats, c="#ff44ff", s=100, marker="^", alpha=1.0,
               edgecolors="white", linewidths=0.8, zorder=9)
    for lon, lat, row in orifices:
        name = row.get("Name", "")
        if name:
            ax.annotate(name, (lon, lat), xytext=(5, 5), textcoords="offset points",
                        color="#ff44ff", fontsize=6, zorder=9)
    all_lons.extend(or_lons)
    all_lats.extend(or_lats)

# -- Draw outfalls (inverted triangle, teal) -----------------------------------
if outfalls:
    of_lons = [p[0] for p in outfalls]
    of_lats = [p[1] for p in outfalls]
    ax.scatter(of_lons, of_lats, c="#00ffcc", s=140, marker="v", alpha=1.0,
               edgecolors="white", linewidths=0.8, zorder=9)
    for lon, lat, row in outfalls:
        name = row.get("Name", "")
        if name:
            ax.annotate(name, (lon, lat), xytext=(5, -12), textcoords="offset points",
                        color="#00ffcc", fontsize=6, zorder=9)
    all_lons.extend(of_lons)
    all_lats.extend(of_lats)

# -- Draw pumps (diamond markers) ---------------------------------------------
if pumps:
    pm_lons = [p[0] for p in pumps]
    pm_lats = [p[1] for p in pumps]
    ax.scatter(pm_lons, pm_lats, c="#ffff00", s=100, marker="D", alpha=1.0,
               edgecolors="white", linewidths=0.8, zorder=10)
    all_lons.extend(pm_lons)
    all_lats.extend(pm_lats)

# -- Draw discharge sources (X markers, red) -----------------------------------
if discharge:
    ds_lons = [p[0] for p in discharge]
    ds_lats = [p[1] for p in discharge]
    ax.scatter(ds_lons, ds_lats, c="#ff2200", s=100, marker="X", alpha=1.0,
               edgecolors="white", linewidths=0.6, zorder=10)
    all_lons.extend(ds_lons)
    all_lats.extend(ds_lats)

# -- Draw raingages (star markers) ---------------------------------------------
if raingages:
    rg_lons = [p[0] for p in raingages]
    rg_lats = [p[1] for p in raingages]
    ax.scatter(rg_lons, rg_lats, c="#00ffff", s=200, marker="*", alpha=1.0,
               edgecolors="white", linewidths=0.6, zorder=11)
    for lon, lat, row in raingages:
        name = row.get("Name", "")
        ax.annotate(name, (lon, lat), xytext=(5, 5), textcoords="offset points",
                    color="#00ffff", fontsize=7, fontweight="bold", zorder=11)
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

# Count canal sub-types
n_irr = sum(1 for _, r in canals if "tuoi" in (r.get("Purpose") or "").lower())
n_drn = sum(1 for _, r in canals if "tieu" in (r.get("Purpose") or "").lower())

ax.set_title(
    f"Sample Region — {len(canals)} Canals  |  {len(rivers)} Rivers  |  {len(sewers)} Sewers  |  "
    f"{len(weirs)} Structures  |  {len(pumps)} Pumps  |  {len(raingages)} Raingages  |  "
    f"{len(subcatchments)} Subcatchments",
    color="#ffffff", fontsize=11, fontweight="bold", pad=14,
)

handles = [
    # Network
    mlines.Line2D([], [], color="#4488ff", linewidth=2.0,
                  label=f"River ({len(rivers)})"),
    mlines.Line2D([], [], color="#00bfff", linewidth=1.5,
                  label=f"Canal — Irrigation ({n_irr})"),
    mlines.Line2D([], [], color="#00ff88", linewidth=1.5,
                  label=f"Canal — Drainage ({n_drn})"),
    mlines.Line2D([], [], color="#ffaa00", linewidth=1.5,
                  label=f"Canal — Other ({len(canals)-n_irr-n_drn})"),
    mlines.Line2D([], [], color="#cc3333", linewidth=1.2, linestyle="--",
                  label=f"Sewer ({len(sewers)})"),
    # Points
    mlines.Line2D([], [], marker="o", color="#3399ff", linestyle="None",
                  markersize=7, label=f"Lake ({len(lakes)})"),
    mlines.Line2D([], [], marker="s", color="#ff9900", linestyle="None",
                  markersize=5, label=f"Manhole ({len(manholes)})"),
    mlines.Line2D([], [], marker="^", color="#ff44ff", linestyle="None",
                  markersize=6, label=f"Orifice ({len(orifices)})"),
    mlines.Line2D([], [], marker="v", color="#00ffcc", linestyle="None",
                  markersize=6, label=f"Outfall ({len(outfalls)})"),
    mlines.Line2D([], [], marker="D", color="#ffff00", linestyle="None",
                  markersize=6, label=f"Pump station ({len(pumps)})"),
    # Weir subtypes
    mlines.Line2D([], [], marker="o", color="#ff4444", linestyle="None",
                  markersize=5, label="Regulation gate"),
    mlines.Line2D([], [], marker="o", color="#44aaff", linestyle="None",
                  markersize=5, label="Canal head/end gate"),
    mlines.Line2D([], [], marker="o", color="#ffaa00", linestyle="None",
                  markersize=5, label="Road crossing gate"),
    mlines.Line2D([], [], marker="o", color="#00ff88", linestyle="None",
                  markersize=5, label="Drainage gate"),
    mlines.Line2D([], [], marker="o", color="#cc66ff", linestyle="None",
                  markersize=5, label="Control gate"),
    # Other
    mlines.Line2D([], [], marker="*", color="#00ffff", linestyle="None",
                  markersize=9, label=f"Rain gage ({len(raingages)})"),
    mlines.Line2D([], [], marker="X", color="#ff2200", linestyle="None",
                  markersize=6, label=f"Discharge source ({len(discharge)})"),
    mlines.Line2D([], [], color="#ff6b6b", linewidth=1.0, linestyle="--",
                  label=f"Subcatchment ({len(subcatchments)})"),
]
ax.legend(handles=handles, loc="upper right",
          facecolor="#1a1a2edd", edgecolor="#555", labelcolor="#ffffff",
          fontsize=7.5, framealpha=0.9, ncol=2)

ax.text(0.01, 0.01,
        f"CRS: EPSG:4326\n"
        f"Basemap: Esri World Imagery",
        transform=ax.transAxes, va="bottom", color="#cccccc",
        fontsize=8, bbox=dict(facecolor="#1a1a2ecc", edgecolor="#555", pad=5))

plt.tight_layout()
plt.savefig(OUT_PNG, dpi=600, bbox_inches="tight",
            facecolor=fig.get_facecolor())
plt.close()
print(f"Saved: {OUT_PNG}")
