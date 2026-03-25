"""
Visualize sewer network + manholes shapefiles.
Run with: python sewer_visualize.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
from osgeo import ogr

ogr.UseExceptions()

SEWER_SHP   = r"g:\workspace\github\swmm\dataset\thoat_nuoc\sewers\sewers.shp"
MANHOLE_SHP = r"g:\workspace\github\swmm\dataset\thoat_nuoc\manholes\manholes.shp"
OUT_PNG     = r"g:\workspace\github\swmm\result\visualization\sewer_preview.png"


def _san(text):
    if not text:
        return ""
    return text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")


# -- read sewers ---------------------------------------------------------------
print("Loading sewer shapefile...")
ds  = ogr.Open(SEWER_SHP)
lyr = ds.GetLayer(0)

sewers = []
for feat in lyr:
    geom = feat.GetGeometryRef()
    if geom is None:
        continue
    pts = geom.GetPoints()
    if not pts:
        continue

    diam = feat.GetField("Diam_mm") or 0
    xs = feat.GetField("XSType") or ""

    sewers.append({
        "xs": [p[0] for p in pts],
        "ys": [p[1] for p in pts],
        "name": _san(feat.GetField("Name") or ""),
        "diam": diam,
        "xstype": _san(xs),
        "from": _san(feat.GetField("FromNode") or ""),
        "to": _san(feat.GetField("ToNode") or ""),
    })

ds = None
print(f"  Loaded {len(sewers)} sewer segments")

# -- read manholes --------------------------------------------------------------
print("Loading manhole shapefile...")
ds  = ogr.Open(MANHOLE_SHP)
lyr = ds.GetLayer(0)

manholes = []
for feat in lyr:
    geom = feat.GetGeometryRef()
    if geom is None:
        continue
    manholes.append({
        "lon": geom.GetX(),
        "lat": geom.GetY(),
        "name": _san(feat.GetField("Name") or ""),
        "rim": feat.GetField("RimElev_m") or 0,
        "inv": feat.GetField("InvElev_m") or 0,
    })

ds = None
print(f"  Loaded {len(manholes)} manholes")

# -- plot ----------------------------------------------------------------------
fig, ax = plt.subplots(1, 1, figsize=(14, 12))
fig.patch.set_facecolor("#0d1117")
ax.set_facecolor("#0d1117")
ax.set_aspect("equal")
ax.tick_params(colors="#888888", labelsize=8)
for sp in ax.spines.values():
    sp.set_edgecolor("#333333")

# sewers coloured by diameter
def sewer_color(diam):
    if diam >= 1000:
        return "#e74c3c"    # large trunk = red
    elif diam >= 600:
        return "#f39c12"    # medium = orange
    else:
        return "#3498db"    # small = blue

for s in sewers:
    color = sewer_color(s["diam"])
    lw = max(1.0, s["diam"] / 400)
    ax.plot(s["xs"], s["ys"], color=color, linewidth=lw, alpha=0.8, zorder=2)

# manholes
if manholes:
    ml = [m["lon"] for m in manholes]
    mt = [m["lat"] for m in manholes]
    ax.scatter(ml, mt, c="#2ecc71", s=60, alpha=0.9,
               edgecolors="white", linewidths=0.6, zorder=3, marker="s")

    for m in manholes:
        ax.annotate(m["name"], (m["lon"], m["lat"]),
                    textcoords="offset points", xytext=(5, 5),
                    fontsize=6, color="#cccccc", alpha=0.9)

# collect all coords for extent
all_x = [x for s in sewers for x in s["xs"]] + [m["lon"] for m in manholes]
all_y = [y for s in sewers for y in s["ys"]] + [m["lat"] for m in manholes]
pad = 0.002
ax.set_xlim(min(all_x) - pad, max(all_x) + pad)
ax.set_ylim(min(all_y) - pad, max(all_y) + pad)

ax.set_xlabel("Longitude", color="#aaaaaa", fontsize=9)
ax.set_ylabel("Latitude",  color="#aaaaaa", fontsize=9)
ax.set_title(f"Sewer Network (Sample) - {len(sewers)} conduits, {len(manholes)} manholes",
             color="white", fontsize=13, fontweight="bold", pad=10)

# legend
handles = [
    mlines.Line2D([], [], color="#3498db", linewidth=1.5, label="D < 600mm"),
    mlines.Line2D([], [], color="#f39c12", linewidth=2.0, label="D 600-1000mm"),
    mlines.Line2D([], [], color="#e74c3c", linewidth=3.0, label="D >= 1000mm"),
    mlines.Line2D([], [], marker="s", color="#2ecc71", linestyle="None",
                  markersize=7, markeredgecolor="white", markeredgewidth=0.3,
                  label="Manhole"),
]
ax.legend(handles=handles, loc="upper left",
          facecolor="#1a1a2e", edgecolor="#444", labelcolor="white",
          fontsize=8, framealpha=0.9)

# info box
ax.text(0.02, 0.02,
        f"CRS: EPSG:4326\nConduits: {len(sewers)}\nManholes: {len(manholes)}\nRegion: Ha Noi (sample)",
        transform=ax.transAxes, va="bottom", color="#aaaaaa",
        fontsize=8, bbox=dict(facecolor="#00000088", edgecolor="none", pad=4))

plt.tight_layout()
plt.savefig(OUT_PNG, dpi=450, bbox_inches="tight",
            facecolor=fig.get_facecolor())
plt.close()
print(f"Saved: {OUT_PNG}")
