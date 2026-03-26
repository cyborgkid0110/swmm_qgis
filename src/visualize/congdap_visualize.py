"""
Visualize hydraulic structures (weirs) shapefile.
Run with: python congdap_visualize.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
from osgeo import ogr

ogr.UseExceptions()

SHP_PATH = r"g:\workspace\github\swmm\dataset\thoat_nuoc\weirs\weirs.shp"
OUT_PNG  = r"g:\workspace\github\swmm\result\visualization\congdap_preview.png"


def _sanitize(text):
    if not text:
        return ""
    return text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")


# -- read shapefile ------------------------------------------------------------
print("Loading weirs shapefile...")
ds  = ogr.Open(SHP_PATH)
lyr = ds.GetLayer(0)
defn = lyr.GetLayerDefn()

points = []
for feat in lyr:
    geom = feat.GetGeometryRef()
    if geom is None:
        continue
    d = {
        "lon": geom.GetX(),
        "lat": geom.GetY(),
        "name": _sanitize(feat.GetField("Name") or ""),
        "type": _sanitize(feat.GetField("Type") or ""),
        "purpose": _sanitize(feat.GetField("Purpose") or ""),
        "grade": _sanitize(feat.GetField("Grade") or ""),
        "openings": feat.GetField("Openings") or 0,
        "irrig_sys": _sanitize(feat.GetField("IrrigSys") if feat.GetFieldIndex("IrrigSys") >= 0 else ""),
    }
    points.append(d)

ds = None
print(f"  Loaded {len(points)} features")

# -- classify by structure type ------------------------------------------------
def get_color(stype):
    s = stype.lower()
    if "van" in s:
        return "#e74c3c"      # sluice gate = red
    elif "tran" in s:
        return "#f39c12"      # weir/spillway = orange
    elif "hop" in s or "tron" in s:
        return "#3498db"      # box/pipe culvert = blue
    elif "dap" in s:
        return "#9b59b6"      # dam = purple
    else:
        return "#2ecc71"      # other = green

# count types
type_counts = {}
for p in points:
    t = p["type"] if p["type"] else "(unknown)"
    type_counts[t] = type_counts.get(t, 0) + 1

print("\n  Structure types:")
for t, c in sorted(type_counts.items(), key=lambda x: -x[1])[:10]:
    print(f"    {t:<40s} {c:>5d}")

# -- plot ----------------------------------------------------------------------
fig, ax = plt.subplots(1, 1, figsize=(14, 12))
fig.patch.set_facecolor("#0d1117")
ax.set_facecolor("#0d1117")
ax.set_aspect("equal")
ax.tick_params(colors="#888888", labelsize=8)
for sp in ax.spines.values():
    sp.set_edgecolor("#333333")

lons = [p["lon"] for p in points]
lats = [p["lat"] for p in points]
colors = [get_color(p["type"]) for p in points]

ax.scatter(lons, lats, c=colors, s=8, alpha=0.6,
           edgecolors="none", zorder=3)

ax.set_xlabel("Longitude", color="#aaaaaa", fontsize=9)
ax.set_ylabel("Latitude",  color="#aaaaaa", fontsize=9)
ax.set_title(f"Hydraulic Structures (Standardized) - {len(points)} features",
             color="white", fontsize=13, fontweight="bold", pad=10)

# legend
handles = [
    mlines.Line2D([], [], marker="o", color="#3498db", linestyle="None",
                  markersize=6, label="Culvert (hop/tron)"),
    mlines.Line2D([], [], marker="o", color="#e74c3c", linestyle="None",
                  markersize=6, label="Sluice gate (van)"),
    mlines.Line2D([], [], marker="o", color="#f39c12", linestyle="None",
                  markersize=6, label="Weir/spillway (tran)"),
    mlines.Line2D([], [], marker="o", color="#9b59b6", linestyle="None",
                  markersize=6, label="Dam (dap)"),
    mlines.Line2D([], [], marker="o", color="#2ecc71", linestyle="None",
                  markersize=6, label="Other"),
]
ax.legend(handles=handles, loc="upper left",
          facecolor="#1a1a2e", edgecolor="#444", labelcolor="white",
          fontsize=8, framealpha=0.9)

# info box
ax.text(0.02, 0.02,
        f"CRS: EPSG:4326\nFeatures: {len(points)}\nRegion: HCMC / Southern Vietnam",
        transform=ax.transAxes, va="bottom", color="#aaaaaa",
        fontsize=8, bbox=dict(facecolor="#00000088", edgecolor="none", pad=4))

pad = 0.01
ax.set_xlim(min(lons) - pad, max(lons) + pad)
ax.set_ylim(min(lats) - pad, max(lats) + pad)

plt.tight_layout()
plt.savefig(OUT_PNG, dpi=450, bbox_inches="tight",
            facecolor=fig.get_facecolor())
plt.close()
print(f"\nSaved: {OUT_PNG}")
