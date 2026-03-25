"""
Visualise the mekong_dams shapefile: points coloured by Status, sized by Capacity.
Run with: python dams_visualize.py
"""
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
from osgeo import ogr

ogr.UseExceptions()

SHP_PATH = r"g:\workspace\github\swmm\dataset\mang_luoi_song_ho_kenh_muong\mekong_dams\mekong_dams.shp"
OUT_PNG  = r"g:\workspace\github\swmm\result\visualization\dams_preview.png"

# ── load features ─────────────────────────────────────────────────────────────
ds  = ogr.Open(SHP_PATH)
lyr = ds.GetLayer(0)

STATUS_COLORS = {
    "Operational":        "#2ecc71",
    "Planned":            "#3498db",
    "Under construction": "#f39c12",
    "Cancelled":          "#e74c3c",
    "Closed":             "#95a5a6",
}
DEFAULT_COLOR = "#cccccc"

points = []  # (lon, lat, color, size, name, status, cap)

for feat in lyr:
    geom = feat.GetGeometryRef()
    if geom is None:
        continue
    lon, lat = geom.GetX(), geom.GetY()

    status = feat.GetField("Status") or ""
    color  = STATUS_COLORS.get(status, DEFAULT_COLOR)
    cap    = feat.GetField("Cap_MW")
    name   = feat.GetField("Name") or ""

    # size by capacity (log scale, with floor for unknowns)
    if cap and cap > 0:
        sz = 4 + 18 * (np.log10(cap + 1) / np.log10(30000))
    else:
        sz = 3

    points.append((lon, lat, color, sz, name, status, cap))

ds = None

# ── figure: 2 panels ─────────────────────────────────────────────────────────
fig, (ax_map, ax_bar) = plt.subplots(
    1, 2, figsize=(20, 10), gridspec_kw={"width_ratios": [2.5, 1]})
fig.patch.set_facecolor("#0d1117")

# ── left: map ─────────────────────────────────────────────────────────────────
ax_map.set_facecolor("#0d1117")
ax_map.set_aspect("equal")

for lon, lat, color, sz, name, status, cap in points:
    ax_map.scatter(lon, lat, c=color, s=sz**2, alpha=0.7,
                   edgecolors="white", linewidths=0.15, zorder=2)

ax_map.tick_params(colors="#888888", labelsize=7)
for sp in ax_map.spines.values():
    sp.set_edgecolor("#333333")
ax_map.set_xlabel("Longitude (°)", color="#aaaaaa", fontsize=8)
ax_map.set_ylabel("Latitude (°)",  color="#aaaaaa", fontsize=8)
ax_map.set_title("Mekong Dams — Point Locations by Status & Capacity",
                  color="white", fontsize=12, fontweight="bold", pad=10)

# legend — status
handles = []
for status, color in STATUS_COLORS.items():
    n = sum(1 for p in points if p[5] == status)
    handles.append(mlines.Line2D([], [], marker="o", color=color,
                                  linestyle="None", markersize=7,
                                  markeredgecolor="white", markeredgewidth=0.3,
                                  label=f"{status} ({n})"))
ax_map.legend(handles=handles, loc="lower left",
              facecolor="#1a1a2e", edgecolor="#444", labelcolor="white",
              fontsize=8, title="Status", title_fontsize=9, framealpha=0.9)

# size legend annotation
ax_map.text(0.99, 0.02,
            "Circle size ~ log(Capacity MW)",
            transform=ax_map.transAxes, ha="right", va="bottom",
            color="#888888", fontsize=7,
            bbox=dict(facecolor="#00000088", edgecolor="none", pad=3))

# ── right: bar charts ────────────────────────────────────────────────────────
ax_bar.set_facecolor("#0d1117")

# top: count by country
countries = {}
for p in points:
    # we don't have country in the tuple — re-read quickly
    pass

# re-read for stats
ds2 = ogr.Open(SHP_PATH)
lyr2 = ds2.GetLayer(0)

country_count = {}
country_cap   = {}
use_count     = {}
basin_count   = {}

for feat in lyr2:
    country = feat.GetField("Country") or "Unknown"
    cap     = feat.GetField("Cap_MW") or 0
    use     = feat.GetField("Purpose") or "Unknown"
    basin   = feat.GetField("Basin") or "Unknown"

    country_count[country] = country_count.get(country, 0) + 1
    country_cap[country]   = country_cap.get(country, 0) + cap
    use_count[use]         = use_count.get(use, 0) + 1
    basin_count[basin]     = basin_count.get(basin, 0) + 1

ds2 = None

# sort countries by count
cc_sorted = sorted(country_count.items(), key=lambda x: -x[1])
c_names   = [x[0] for x in cc_sorted]
c_counts  = [x[1] for x in cc_sorted]
c_caps    = [country_cap.get(c, 0) for c in c_names]

ax_bar.axis("off")

# ── draw stats as a summary panel ──
y = 0.95
ax_bar.set_xlim(0, 1)
ax_bar.set_ylim(0, 1)

ax_bar.text(0.05, y, "Dataset Summary", color="white",
            fontsize=12, fontweight="bold", va="top")
y -= 0.07
ax_bar.text(0.05, y, f"Total dams: {len(points):,}", color="white",
            fontsize=10, va="top")
y -= 0.06
total_cap = sum(p[6] or 0 for p in points)
ax_bar.text(0.05, y, f"Total capacity: {total_cap:,.0f} MW", color="white",
            fontsize=10, va="top")

y -= 0.09
ax_bar.text(0.05, y, "By Country", color="white",
            fontsize=10, fontweight="bold", va="top")
y -= 0.06

bar_colors = ["#2ecc71", "#3498db", "#f39c12", "#e74c3c", "#9b59b6", "#1abc9c"]
max_c = max(c_counts)
for i, (cn, cc) in enumerate(zip(c_names, c_counts)):
    cap_mw = c_caps[i]
    bar_w  = 0.55 * cc / max_c
    bc     = bar_colors[i % len(bar_colors)]

    ax_bar.barh(y - 0.01, bar_w, height=0.035, left=0.05,
                color=bc, alpha=0.8, zorder=2)
    ax_bar.text(0.06, y - 0.01, f"{cn}", color="white",
                fontsize=8, va="center", fontweight="bold", zorder=3)
    ax_bar.text(0.05 + bar_w + 0.02, y - 0.01,
                f"{cc}  ({cap_mw:,.0f} MW)",
                color="#aaaaaa", fontsize=8, va="center")
    y -= 0.055

y -= 0.06
ax_bar.text(0.05, y, "By Primary Use", color="white",
            fontsize=10, fontweight="bold", va="top")
y -= 0.06

use_sorted = sorted(use_count.items(), key=lambda x: -x[1])[:8]
max_u = max(x[1] for x in use_sorted)
for i, (use, uc) in enumerate(use_sorted):
    bar_w = 0.55 * uc / max_u
    bc    = bar_colors[i % len(bar_colors)]
    ax_bar.barh(y - 0.01, bar_w, height=0.035, left=0.05,
                color=bc, alpha=0.8, zorder=2)
    ax_bar.text(0.06, y - 0.01, use, color="white",
                fontsize=8, va="center", fontweight="bold", zorder=3)
    ax_bar.text(0.05 + bar_w + 0.02, y - 0.01, f"{uc}",
                color="#aaaaaa", fontsize=8, va="center")
    y -= 0.055

fig.suptitle("Mekong Dam Database — Shapefile Visualisation",
             color="white", fontsize=14, fontweight="bold", y=1.01)

plt.tight_layout(pad=1.5)
plt.savefig(OUT_PNG, dpi=450, bbox_inches="tight",
            facecolor=fig.get_facecolor())
plt.close()
print(f"Saved: {OUT_PNG}")
