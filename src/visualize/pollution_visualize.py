"""
Visualize pollution discharge shapefiles (2022 + 2023).
Run with: python pollution_visualize.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
from osgeo import ogr

ogr.UseExceptions()

SHP_2022 = r"g:\workspace\github\swmm\dataset\nguon_thai\discharge2022\discharge2022.shp"
SHP_2023 = r"g:\workspace\github\swmm\dataset\nguon_thai\discharge2023\discharge2023.shp"
OUT_PNG  = r"g:\workspace\github\swmm\result\visualization\pollution_preview.png"


def _san(text):
    if not text:
        return ""
    return text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")


def read_points(shp_path, label):
    ds  = ogr.Open(shp_path)
    lyr = ds.GetLayer(0)
    pts = []
    for feat in lyr:
        geom = feat.GetGeometryRef()
        if geom is None:
            continue
        pts.append({
            "lon": geom.GetX(), "lat": geom.GetY(),
            "name": _san(feat.GetField("Name") or ""),
            "discharger": _san(feat.GetField("Discharger") or ""),
        })
    ds = None
    print(f"  {label}: {len(pts)} features")
    return pts


# -- load data -----------------------------------------------------------------
print("Loading pollution discharge shapefiles...")
pts_2022 = read_points(SHP_2022, "2022")
pts_2023 = read_points(SHP_2023, "2023")

# -- plot: 2 panels -----------------------------------------------------------
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 9))
fig.patch.set_facecolor("#0d1117")

for ax in [ax1, ax2]:
    ax.set_facecolor("#0d1117")
    ax.set_aspect("equal")
    ax.tick_params(colors="#888888", labelsize=7)
    for sp in ax.spines.values():
        sp.set_edgecolor("#333333")
    ax.set_xlabel("Longitude", color="#aaaaaa", fontsize=8)
    ax.set_ylabel("Latitude",  color="#aaaaaa", fontsize=8)

# -- left: 2022 ---------------------------------------------------------------
if pts_2022:
    lons = [p["lon"] for p in pts_2022]
    lats = [p["lat"] for p in pts_2022]
    ax1.scatter(lons, lats, c="#e74c3c", s=80, alpha=0.8,
                edgecolors="white", linewidths=0.5, zorder=3)
    pad = 0.01
    ax1.set_xlim(min(lons) - pad, max(lons) + pad)
    ax1.set_ylim(min(lats) - pad, max(lats) + pad)

    labeled = set()
    for p in pts_2022:
        n = p["discharger"] or p["name"]
        if n and n not in labeled and len(labeled) < 8:
            ax1.annotate(n[:40], (p["lon"], p["lat"]),
                         textcoords="offset points", xytext=(6, 4),
                         fontsize=5, color="#cccccc", alpha=0.8)
            labeled.add(n)

ax1.set_title(f"Discharge Sources 2022 - {len(pts_2022)} features",
              color="white", fontsize=11, fontweight="bold", pad=8)
ax1.text(0.02, 0.98, "CRS: EPSG:4326\nHCMC region",
         transform=ax1.transAxes, va="top", color="#aaaaaa",
         fontsize=8, bbox=dict(facecolor="#00000088", edgecolor="none", pad=3))

# -- right: 2023 --------------------------------------------------------------
if pts_2023:
    lons = [p["lon"] for p in pts_2023]
    lats = [p["lat"] for p in pts_2023]
    ax2.scatter(lons, lats, c="#f39c12", s=80, alpha=0.8,
                edgecolors="white", linewidths=0.5, zorder=3)
    pad = 0.01
    ax2.set_xlim(min(lons) - pad, max(lons) + pad)
    ax2.set_ylim(min(lats) - pad, max(lats) + pad)

    labeled = set()
    for p in pts_2023:
        n = p["discharger"] or p["name"]
        if n and n not in labeled and len(labeled) < 8:
            ax2.annotate(n[:40], (p["lon"], p["lat"]),
                         textcoords="offset points", xytext=(6, 4),
                         fontsize=5, color="#cccccc", alpha=0.8)
            labeled.add(n)

ax2.set_title(f"Discharge Sources 2023 - {len(pts_2023)} features",
              color="white", fontsize=11, fontweight="bold", pad=8)
ax2.text(0.02, 0.98, "CRS: EPSG:4326\nHCMC region",
         transform=ax2.transAxes, va="top", color="#aaaaaa",
         fontsize=8, bbox=dict(facecolor="#00000088", edgecolor="none", pad=3))

fig.suptitle("Pollution Discharge Sources (Standardized)",
             color="white", fontsize=14, fontweight="bold", y=1.01)

plt.tight_layout(pad=1.5)
plt.savefig(OUT_PNG, dpi=450, bbox_inches="tight",
            facecolor=fig.get_facecolor())
plt.close()
print(f"\nSaved: {OUT_PNG}")
