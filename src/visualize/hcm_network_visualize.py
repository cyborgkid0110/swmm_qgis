"""
Visualize HCM canal network + hydraulic structures (weirs) on the same map
with OpenStreetMap basemap background.
Run with: conda run -n qgis-env python src/visualize/hcm_network_visualize.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
from osgeo import ogr
import contextily as cx

ogr.UseExceptions()

import csv
import json

CANAL_SHP   = r"g:\workspace\github\swmm\dataset\mang_luoi_song_ho_kenh_muong\canals\canals.shp"
WEIRS_CSV   = r"g:\workspace\github\swmm\dataset\thoat_nuoc\weir.csv"
OUT_PNG     = r"g:\workspace\github\swmm\result\visualization\hcm_canals_weirs.png"


def _sanitize(text):
    if not text:
        return ""
    return text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")


# == Load canals ===============================================================
print("Loading canals...")
ds = ogr.Open(CANAL_SHP)
lyr = ds.GetLayer(0)

canals = []
for feat in lyr:
    geom = feat.GetGeometryRef()
    if geom is None:
        continue
    parts = []
    if geom.GetGeometryCount() > 0:
        for i in range(geom.GetGeometryCount()):
            sub = geom.GetGeometryRef(i)
            pts = sub.GetPoints()
            if pts:
                parts.append(pts)
    else:
        pts = geom.GetPoints()
        if pts:
            parts.append(pts)
    purpose = _sanitize(feat.GetField("Purpose") or "")
    canals.append({"parts": parts, "purpose": purpose})
ds = None
print(f"  {len(canals)} canal features")


# == Load weirs (from CSV for correct Vietnamese encoding) ===================
print("Loading weirs...")
weirs = []
with open(WEIRS_CSV, encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        try:
            g = json.loads(row.get("Shape", ""))
            if g["type"] != "Point":
                continue
            weirs.append({
                "lon": g["coordinates"][0],
                "lat": g["coordinates"][1],
                "type": row.get("Type", ""),
            })
        except Exception:
            continue
print(f"  {len(weirs)} weirs features")


# == Colour helpers ============================================================
def canal_color(purpose):
    p = purpose.lower()
    if "tuoi" in p:
        return "#3498db"   # irrigation = blue
    elif "tieu" in p:
        return "#2ecc71"   # drainage = green
    return "#f39c12"       # other = orange


def weirs_color(stype):
    """Categorize by Type field (Vietnamese, from CSV with proper encoding).

    Major types:
      Cống điều tiết (1125) - regulation gate
      Cống đầu kênh  (1039) - canal head gate
      Cống qua đường  (594) - road crossing
      Cống tiêu       (252) - drainage gate
      Cống cuối kênh   (62) - canal end gate
      Cống kiểm soát   (62) - control gate
      Cống ly tâm      (40) - centrifugal gate
    """
    s = stype.lower()
    if "u ti" in s:          # "điều tiết" → regulation
        return "#e74c3c"     # red
    elif "u k" in s:         # "đầu kênh" or "cuối kênh" → canal head/end
        return "#3498db"     # blue
    elif "qua" in s:         # "qua đường" → road crossing
        return "#f39c12"     # orange
    elif "tieu" in s or "tiêu" in s:  # "tiêu" → drainage
        return "#2ecc71"     # green
    elif "soát" in s or "soat" in s:  # "kiểm soát" → control
        return "#9b59b6"     # purple
    elif "ly" in s:          # "ly tâm" → centrifugal
        return "#fd79a8"     # pink
    elif not s:
        return "#636e72"     # empty/unknown = dark grey
    return "#dfe6e9"         # other = light grey


# == Plot ======================================================================
print("Rendering...")
fig, ax = plt.subplots(1, 1, figsize=(24, 20))
fig.patch.set_facecolor("#ffffff")
ax.set_facecolor("#ffffff")
ax.set_aspect("equal")
ax.tick_params(colors="#444444", labelsize=8)
for sp in ax.spines.values():
    sp.set_edgecolor("#999999")

# -- Draw canals (bottom layer) ------------------------------------------------
for c in canals:
    color = canal_color(c["purpose"])
    for pts in c["parts"]:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        ax.plot(xs, ys, color=color, linewidth=0.4, alpha=0.8, zorder=2)

# -- Draw weirs (top layer, small points) ------------------------------------
cd_lons = [p["lon"] for p in weirs]
cd_lats = [p["lat"] for p in weirs]
cd_colors = [weirs_color(p["type"]) for p in weirs]

ax.scatter(cd_lons, cd_lats, c=cd_colors, s=2, alpha=0.8,
           edgecolors="none", zorder=5)

# -- Basemap background (OpenStreetMap) ----------------------------------------
print("Fetching basemap tiles...")
# Set extent first so contextily knows which tiles to fetch
all_lons = cd_lons + [p[0] for c in canals for pts in c["parts"] for p in pts]
all_lats = cd_lats + [p[1] for c in canals for pts in c["parts"] for p in pts]
pad = 0.01
ax.set_xlim(min(all_lons) - pad, max(all_lons) + pad)
ax.set_ylim(min(all_lats) - pad, max(all_lats) + pad)

cx.add_basemap(
    ax,
    crs="EPSG:4326",
    source=cx.providers.CartoDB.Positron,
    zoom=20,
    zorder=0,
)
print("  Basemap added")

# -- Labels & legend -----------------------------------------------------------
ax.set_xlabel("Longitude", color="#333333", fontsize=10)
ax.set_ylabel("Latitude",  color="#333333", fontsize=10)
ax.set_title(
    f"HCM Canal Network ({len(canals):,}) + Hydraulic Structures ({len(weirs):,})",
    color="#111111", fontsize=15, fontweight="bold", pad=12,
)

handles = [
    # canals
    mlines.Line2D([], [], color="#3498db", linewidth=1.5,
                  label=f"Canal - Irrigation ({sum(1 for c in canals if 'tuoi' in c['purpose'].lower())})"),
    mlines.Line2D([], [], color="#2ecc71", linewidth=1.5,
                  label=f"Canal - Drainage ({sum(1 for c in canals if 'tieu' in c['purpose'].lower())})"),
    mlines.Line2D([], [], color="#f39c12", linewidth=1.5,
                  label="Canal - Other"),
    # weirs (by Type)
    mlines.Line2D([], [], marker="o", color="#e74c3c", linestyle="None",
                  markersize=4, label="Regulation gate"),
    mlines.Line2D([], [], marker="o", color="#3498db", linestyle="None",
                  markersize=4, label="Canal head/end gate"),
    mlines.Line2D([], [], marker="o", color="#f39c12", linestyle="None",
                  markersize=4, label="Road crossing"),
    mlines.Line2D([], [], marker="o", color="#2ecc71", linestyle="None",
                  markersize=4, label="Drainage gate"),
    mlines.Line2D([], [], marker="o", color="#9b59b6", linestyle="None",
                  markersize=4, label="Control gate"),
    mlines.Line2D([], [], marker="o", color="#fd79a8", linestyle="None",
                  markersize=4, label="Centrifugal gate"),
    mlines.Line2D([], [], marker="o", color="#636e72", linestyle="None",
                  markersize=4, label="Unknown type"),
]
ax.legend(handles=handles, loc="upper left",
          facecolor="#ffffffdd", edgecolor="#999", labelcolor="#222",
          fontsize=9, framealpha=0.9)

# info box
ax.text(0.02, 0.02,
        f"CRS: EPSG:4326\n"
        f"Canals: {len(canals):,} LineStrings\n"
        f"Structures: {len(weirs):,} Points\n"
        f"Basemap: CartoDB Positron",
        transform=ax.transAxes, va="bottom", color="#333333",
        fontsize=9, bbox=dict(facecolor="#ffffffcc", edgecolor="#999", pad=5))

plt.tight_layout()
plt.savefig(OUT_PNG, dpi=600, bbox_inches="tight",
            facecolor=fig.get_facecolor())
plt.close()
print(f"Saved: {OUT_PNG}")
