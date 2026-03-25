"""
Visualize lake/detention pond shapefile.
Run with: python lake_visualize.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
from osgeo import ogr

ogr.UseExceptions()

SHP_PATH = r"g:\workspace\github\swmm\dataset\mang_luoi_song_ho_kenh_muong\lakes\lakes.shp"
OUT_PNG  = r"g:\workspace\github\swmm\result\visualization\lakes_preview.png"


def _san(text):
    if not text:
        return ""
    return text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")


# -- read shapefile ------------------------------------------------------------
print("Loading lake shapefile...")
ds  = ogr.Open(SHP_PATH)
lyr = ds.GetLayer(0)

lakes = []
for feat in lyr:
    geom = feat.GetGeometryRef()
    if geom is None:
        continue
    lakes.append({
        "lon": geom.GetX(),
        "lat": geom.GetY(),
        "name": _san(feat.GetField("Name") or ""),
        "area": feat.GetField("Area_ha") or 0,
        "vol": feat.GetField("Vol_m3") or 0,
        "bed": feat.GetField("BedElev_m") or 0,
    })

ds = None
print(f"  Loaded {len(lakes)} features")

# -- plot ----------------------------------------------------------------------
fig, ax = plt.subplots(1, 1, figsize=(12, 10))
fig.patch.set_facecolor("#0d1117")
ax.set_facecolor("#0d1117")
ax.set_aspect("equal")
ax.tick_params(colors="#888888", labelsize=8)
for sp in ax.spines.values():
    sp.set_edgecolor("#333333")

lons = [lk["lon"] for lk in lakes]
lats = [lk["lat"] for lk in lakes]
areas = [lk["area"] for lk in lakes]
# scale marker size by area (min 80, max 600)
max_area = max(areas) if areas else 1
sizes = [max(80, min(600, 80 + 520 * (a / max_area))) for a in areas]

ax.scatter(lons, lats, c="#3498db", s=sizes, alpha=0.7,
           edgecolors="white", linewidths=0.8, zorder=3)

# label all lakes
for lk in lakes:
    label = f"{lk['name']}\n{lk['area']:.0f} ha"
    ax.annotate(label, (lk["lon"], lk["lat"]),
                textcoords="offset points", xytext=(12, 8),
                fontsize=8, color="#ffffff",
                arrowprops=dict(arrowstyle="->", color="#666666", lw=0.5))

pad = 0.01
ax.set_xlim(min(lons) - pad, max(lons) + pad)
ax.set_ylim(min(lats) - pad, max(lats) + pad)

ax.set_xlabel("Longitude", color="#aaaaaa", fontsize=9)
ax.set_ylabel("Latitude",  color="#aaaaaa", fontsize=9)
ax.set_title(f"Lakes / Detention Ponds (Sample) - {len(lakes)} features",
             color="white", fontsize=13, fontweight="bold", pad=10)

# info box
ax.text(0.02, 0.02,
        f"CRS: EPSG:4326\nFeatures: {len(lakes)}\nRegion: Ha Noi",
        transform=ax.transAxes, va="bottom", color="#aaaaaa",
        fontsize=8, bbox=dict(facecolor="#00000088", edgecolor="none", pad=4))

plt.tight_layout()
plt.savefig(OUT_PNG, dpi=450, bbox_inches="tight",
            facecolor=fig.get_facecolor())
plt.close()
print(f"Saved: {OUT_PNG}")
