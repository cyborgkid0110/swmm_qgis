"""
Visualize canal network shapefile.
Run with: python canal_visualize.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
from osgeo import ogr

ogr.UseExceptions()

SHP_PATH = r"g:\workspace\github\swmm\dataset\mang_luoi_song_ho_kenh_muong\canals\canals.shp"
OUT_PNG  = r"g:\workspace\github\swmm\result\visualization\canals_preview.png"


def _sanitize(text):
    if not text:
        return ""
    return text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")


# -- read shapefile ------------------------------------------------------------
print("Loading canal shapefile...")
ds  = ogr.Open(SHP_PATH)
lyr = ds.GetLayer(0)

# group by purpose for colouring
purpose_colors = {
    "Tuoi":    "#3498db",   # irrigation
    "Tieu":    "#2ecc71",   # drainage
    "default": "#f39c12",
}

canals = []
for feat in lyr:
    geom = feat.GetGeometryRef()
    if geom is None:
        continue

    # flatten: could be LineString or MultiLineString
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

    purpose   = _sanitize(feat.GetField("Purpose") or "")
    grade     = _sanitize(feat.GetField("Grade") or "")
    name      = _sanitize(feat.GetField("Name") or "")
    length    = feat.GetField("Length_m") or 0
    from_node = _sanitize(feat.GetField("FromNode") or "")
    to_node   = _sanitize(feat.GetField("ToNode") or "")
    canal_type = _sanitize(feat.GetField("Type") or "")

    canals.append({
        "parts": parts,
        "purpose": purpose,
        "grade": grade,
        "name": name,
        "length": length,
        "from_node": from_node,
        "to_node": to_node,
        "type": canal_type,
    })

ds = None
print(f"  Loaded {len(canals)} canal features")

# -- classify by purpose -------------------------------------------------------
def get_color(purpose):
    p = purpose.lower()
    if "tuoi" in p or "tuo" in p:
        return "#3498db"     # irrigation = blue
    elif "tieu" in p:
        return "#2ecc71"     # drainage = green
    elif "tuoi" in p and "tieu" in p:
        return "#9b59b6"     # both = purple
    else:
        return "#f39c12"     # other/unknown = orange


# -- plot ----------------------------------------------------------------------
fig, ax = plt.subplots(1, 1, figsize=(16, 12))
fig.patch.set_facecolor("#0d1117")
ax.set_facecolor("#0d1117")
ax.set_aspect("equal")
ax.tick_params(colors="#888888", labelsize=8)
for sp in ax.spines.values():
    sp.set_edgecolor("#333333")

for c in canals:
    color = get_color(c["purpose"])
    lw = 0.3
    for pts in c["parts"]:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        ax.plot(xs, ys, color=color, linewidth=lw, alpha=0.7)

ax.set_xlabel("Longitude", color="#aaaaaa", fontsize=9)
ax.set_ylabel("Latitude",  color="#aaaaaa", fontsize=9)
ax.set_title(f"Canal Network (Standardized) - {len(canals)} features",
             color="white", fontsize=13, fontweight="bold", pad=10)

# legend
handles = [
    mlines.Line2D([], [], color="#3498db", linewidth=1.5, label="Irrigation (Tuoi)"),
    mlines.Line2D([], [], color="#2ecc71", linewidth=1.5, label="Drainage (Tieu)"),
    mlines.Line2D([], [], color="#f39c12", linewidth=1.5, label="Other/Unknown"),
]
ax.legend(handles=handles, loc="upper left",
          facecolor="#1a1a2e", edgecolor="#444", labelcolor="white",
          fontsize=9, framealpha=0.9)

# info box
ax.text(0.02, 0.02,
        f"CRS: EPSG:4326\nFeatures: {len(canals)}\nDataset: mang_luoi_song_ho_kenh_muong",
        transform=ax.transAxes, va="bottom", color="#aaaaaa",
        fontsize=8, bbox=dict(facecolor="#00000088", edgecolor="none", pad=4))

plt.tight_layout()
plt.savefig(OUT_PNG, dpi=450, bbox_inches="tight",
            facecolor=fig.get_facecolor())
plt.close()
print(f"Saved: {OUT_PNG}")
