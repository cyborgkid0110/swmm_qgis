"""
Visualize river shapefile — colour and thickness by Strahler order.
Run with: python river_visualize.py
Requires: gdal (osgeo), matplotlib, numpy — all in qgis-env.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
import matplotlib.cm as cm
import numpy as np
from osgeo import ogr

SHP_PATH = r"g:\workspace\github\swmm\dataset\mang_luoi_song_ho_kenh_muong\rivers\rivers.shp"
OUT_PNG  = r"g:\workspace\github\swmm\result\visualization\rivers_preview.png"

# ── open layer ────────────────────────────────────────────────────────────────
ogr.UseExceptions()
ds  = ogr.Open(SHP_PATH)
lyr = ds.GetLayer(0)

extent   = lyr.GetExtent()          # (minX, maxX, minY, maxY)
n_feat   = lyr.GetFeatureCount()

# ── collect segments by Strahler ──────────────────────────────────────────────
# segments[order] = list of (xs, ys) arrays
segments = {}
names    = {}   # order -> set of named rivers

lyr.ResetReading()
for feat in lyr:
    s    = feat.GetField("Strahler") or 1
    name = feat.GetField("Name")
    geom = feat.GetGeometryRef()
    if geom is None:
        continue

    # handle both LineString and MultiLineString
    parts = ([geom.GetGeometryRef(i) for i in range(geom.GetGeometryCount())]
             if geom.GetGeometryCount() > 0 else [geom])

    if s not in segments:
        segments[s] = []
        names[s]    = set()

    for part in parts:
        pts = part.GetPoints()
        if not pts:
            continue
        segments[s].append(([p[0] for p in pts], [p[1] for p in pts]))

    if name:
        names[s].add(name)

ds = None

# ── style mapping ─────────────────────────────────────────────────────────────
max_order = max(segments.keys())

# Blue palette: low order = pale, high order = deep blue
cmap   = cm.get_cmap("Blues")
orders = sorted(segments.keys())

def order_style(s):
    """Return (color, linewidth, alpha) for a Strahler order."""
    t     = (s - 1) / (max_order - 1) if max_order > 1 else 1.0
    color = cmap(0.3 + 0.7 * t)       # avoid very pale end of Blues
    lw    = 0.3 + 1.8 * t
    alpha = 0.5 + 0.5 * t
    return color, lw, alpha

# ── figure ────────────────────────────────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(18, 10),
                          gridspec_kw={"width_ratios": [2.5, 1]})
fig.patch.set_facecolor("#0d1117")

ax_map, ax_info = axes

# -- map panel -----------------------------------------------------------------
ax_map.set_facecolor("#0d1117")
ax_map.set_aspect("equal")

for s in orders:
    color, lw, alpha = order_style(s)
    for xs, ys in segments[s]:
        ax_map.plot(xs, ys, color=color, linewidth=lw, alpha=alpha, solid_capstyle="round")

ax_map.set_xlim(extent[0], extent[1])
ax_map.set_ylim(extent[2], extent[3])
ax_map.tick_params(colors="#888888", labelsize=7)
for spine in ax_map.spines.values():
    spine.set_edgecolor("#333333")
ax_map.set_xlabel("Longitude (°)", color="#888888", fontsize=8)
ax_map.set_ylabel("Latitude (°)",  color="#888888", fontsize=8)
ax_map.set_title("River Network (Standardized)",
                  color="white", fontsize=12, fontweight="bold", pad=10)

# legend
legend_handles = []
for s in orders:
    color, lw, alpha = order_style(s)
    n = len(segments[s])
    handle = mlines.Line2D([], [], color=color, linewidth=max(lw, 1.0),
                           alpha=1.0, label=f"Order {s}  ({n} segments)")
    legend_handles.append(handle)

ax_map.legend(handles=legend_handles, loc="lower left",
              facecolor="#1a1a2e", edgecolor="#444", labelcolor="white",
              fontsize=8, title="Strahler Order",
              title_fontsize=9, framealpha=0.9)

# -- info panel ----------------------------------------------------------------
ax_info.set_facecolor("#0d1117")
ax_info.axis("off")

total_len_km = sum(
    sum(
        np.sqrt((xs[i+1]-xs[i])**2 + (ys[i+1]-ys[i])**2)
        for i in range(len(xs)-1)
    )
    for segs in segments.values()
    for xs, ys in segs
)
# length already stored in attribute — reopen just to sum it quickly
ds2  = ogr.Open(SHP_PATH)
lyr2 = ds2.GetLayer(0)
total_attr_len = sum(f.GetField("Length_m") or 0 for f in lyr2)
named_count    = sum(1 for f in lyr2.ResetReading() or [] if f and f.GetField("Name"))
ds2 = None

ds2  = ogr.Open(SHP_PATH)
lyr2 = ds2.GetLayer(0)
named_count = 0
lyr2.ResetReading()
for f in lyr2:
    if f.GetField("Name"):
        named_count += 1
ds2 = None

# stat blocks
stats = [
    ("CRS",             "EPSG:4326 (WGS 84)"),
    ("Total segments",  f"{n_feat:,}"),
    ("Named segments",  f"{named_count:,} / {n_feat:,}"),
    ("Total length",    f"{total_attr_len/1000:,.0f} km"),
    ("Strahler range",  f"{min(orders)} – {max(orders)}"),
    ("Extent lon",      f"{extent[0]:.2f}° – {extent[1]:.2f}°"),
    ("Extent lat",      f"{extent[2]:.2f}° – {extent[3]:.2f}°"),
]

ax_info.set_xlim(0, 1)
ax_info.set_ylim(0, 1)

y = 0.95
ax_info.text(0.05, y, "Dataset Info", color="white",
             fontsize=11, fontweight="bold", va="top")
y -= 0.08

for label, value in stats:
    ax_info.text(0.05, y,       label, color="#aaaaaa", fontsize=9, va="top")
    ax_info.text(0.05, y-0.04,  value, color="white",   fontsize=10,
                 fontweight="bold", va="top")
    y -= 0.11

# per-order table
y -= 0.04
ax_info.text(0.05, y, "Strahler breakdown", color="white",
             fontsize=10, fontweight="bold", va="top")
y -= 0.07

col_header = f"{'Order':<7} {'Segs':>6}  {'Named':>6}"
ax_info.text(0.05, y, col_header, color="#888888", fontsize=8,
             fontfamily="monospace", va="top")
y -= 0.05

ds3  = ogr.Open(SHP_PATH)
lyr3 = ds3.GetLayer(0)
order_named = {}
lyr3.ResetReading()
for f in lyr3:
    s = f.GetField("Strahler") or 1
    order_named.setdefault(s, 0)
    if f.GetField("Name"):
        order_named[s] += 1
ds3 = None

for s in orders:
    color, lw, _ = order_style(s)
    n      = len(segments[s])
    n_name = order_named.get(s, 0)
    row    = f"  {s:<5}  {n:>6}  {n_name:>6}"
    ax_info.text(0.05, y, row, color=color, fontsize=8,
                 fontfamily="monospace", va="top")
    y -= 0.05

plt.tight_layout(pad=1.5)
plt.savefig(OUT_PNG, dpi=450, bbox_inches="tight",
            facecolor=fig.get_facecolor())
plt.close()
print(f"Saved: {OUT_PNG}")
