"""
Visualize urban drainage structures (pumps + outlets + orifices).
Run with: python drainage_visualize.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
from osgeo import ogr

ogr.UseExceptions()

PUMPS_SHP    = r"g:\workspace\github\swmm\dataset\thoat_nuoc\pumps\pumps.shp"
OUTLETS_SHP  = r"g:\workspace\github\swmm\dataset\thoat_nuoc\outlets\outlets.shp"
ORIFICES_SHP = r"g:\workspace\github\swmm\dataset\thoat_nuoc\orifices\orifices.shp"
OUT_PNG      = r"g:\workspace\github\swmm\result\visualization\drainage_preview.png"


def _san(text):
    if not text:
        return ""
    return text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")


def read_points(shp_path, label):
    ds  = ogr.Open(shp_path)
    lyr = ds.GetLayer(0)
    defn = lyr.GetLayerDefn()
    pts = []
    for feat in lyr:
        geom = feat.GetGeometryRef()
        if geom is None:
            continue
        d = {"lon": geom.GetX(), "lat": geom.GetY()}
        for i in range(defn.GetFieldCount()):
            fd = defn.GetFieldDefn(i)
            val = feat.GetField(i)
            if isinstance(val, str):
                val = _san(val)
            d[fd.GetName()] = val
        pts.append(d)
    ds = None
    print(f"  {label}: {len(pts)} features")
    return pts


# -- load data -----------------------------------------------------------------
print("Loading drainage shapefiles...")
pumps    = read_points(PUMPS_SHP, "Pumps")
outlets  = read_points(OUTLETS_SHP, "Outlets")
orifices = read_points(ORIFICES_SHP, "Orifices")

# -- figure: 3 panels ---------------------------------------------------------
fig, (ax_p, ax_o, ax_r) = plt.subplots(1, 3, figsize=(24, 8))
fig.patch.set_facecolor("#0d1117")

for ax in [ax_p, ax_o, ax_r]:
    ax.set_facecolor("#0d1117")
    ax.set_aspect("equal")
    ax.tick_params(colors="#888888", labelsize=7)
    for sp in ax.spines.values():
        sp.set_edgecolor("#333333")
    ax.set_xlabel("Longitude", color="#aaaaaa", fontsize=8)
    ax.set_ylabel("Latitude",  color="#aaaaaa", fontsize=8)

# -- pumps panel ---------------------------------------------------------------
if pumps:
    lons = [p["lon"] for p in pumps]
    lats = [p["lat"] for p in pumps]
    ax_p.scatter(lons, lats, c="#9b59b6", s=100, alpha=0.85,
                 edgecolors="white", linewidths=0.6, zorder=3, marker="^")
    labeled = set()
    for p in pumps:
        name = p.get("Name", "")
        if name and name not in labeled and len(labeled) < 10:
            ax_p.annotate(name[:30], (p["lon"], p["lat"]),
                          textcoords="offset points", xytext=(6, 4),
                          fontsize=5.5, color="#cccccc", alpha=0.9)
            labeled.add(name)
    pad = 0.01
    ax_p.set_xlim(min(lons) - pad, max(lons) + pad)
    ax_p.set_ylim(min(lats) - pad, max(lats) + pad)

ax_p.set_title(f"Pumping Stations - {len(pumps)} features",
               color="white", fontsize=11, fontweight="bold", pad=8)
ax_p.text(0.02, 0.98, "CRS: EPSG:4326\nHCMC / Southern Vietnam",
          transform=ax_p.transAxes, va="top", color="#aaaaaa",
          fontsize=7, bbox=dict(facecolor="#00000088", edgecolor="none", pad=3))

# -- outlets panel -------------------------------------------------------------
if outlets:
    lons = [p["lon"] for p in outlets]
    lats = [p["lat"] for p in outlets]

    colors = []
    for p in outlets:
        o = p.get("Openings") or 0
        if o == 0:
            colors.append("#95a5a6")
        elif o <= 2:
            colors.append("#3498db")
        elif o <= 4:
            colors.append("#f39c12")
        else:
            colors.append("#e74c3c")

    ax_o.scatter(lons, lats, c=colors, s=60, alpha=0.85,
                 edgecolors="white", linewidths=0.5, zorder=3)
    labeled = set()
    for p in outlets:
        name = p.get("Name", "")
        if name and name not in labeled and len(labeled) < 10:
            ax_o.annotate(name[:30], (p["lon"], p["lat"]),
                          textcoords="offset points", xytext=(6, 4),
                          fontsize=5, color="#cccccc", alpha=0.9)
            labeled.add(name)
    pad = 0.005
    ax_o.set_xlim(min(lons) - pad, max(lons) + pad)
    ax_o.set_ylim(min(lats) - pad, max(lats) + pad)

    handles = [
        mlines.Line2D([], [], marker="o", color="#3498db", linestyle="None",
                      markersize=6, label="1-2 openings"),
        mlines.Line2D([], [], marker="o", color="#f39c12", linestyle="None",
                      markersize=6, label="3-4 openings"),
        mlines.Line2D([], [], marker="o", color="#e74c3c", linestyle="None",
                      markersize=6, label="5+ openings"),
        mlines.Line2D([], [], marker="o", color="#95a5a6", linestyle="None",
                      markersize=6, label="Unknown"),
    ]
    ax_o.legend(handles=handles, loc="lower left",
                facecolor="#1a1a2e", edgecolor="#444", labelcolor="white",
                fontsize=6, framealpha=0.9)

ax_o.set_title(f"Outlets / Outfalls - {len(outlets)} features",
               color="white", fontsize=11, fontweight="bold", pad=8)
ax_o.text(0.02, 0.98, "CRS: EPSG:4326\nHCMC tidal flood control",
          transform=ax_o.transAxes, va="top", color="#aaaaaa",
          fontsize=7, bbox=dict(facecolor="#00000088", edgecolor="none", pad=3))

# -- orifices panel ------------------------------------------------------------
if orifices:
    lons = [p["lon"] for p in orifices]
    lats = [p["lat"] for p in orifices]
    ax_r.scatter(lons, lats, c="#e74c3c", s=120, alpha=0.9,
                 edgecolors="white", linewidths=0.8, zorder=3, marker="D")
    for p in orifices:
        name = p.get("Name", "")
        openings = p.get("Openings") or "?"
        label = f"{name}\n({openings} openings)"
        ax_r.annotate(label, (p["lon"], p["lat"]),
                      textcoords="offset points", xytext=(10, 6),
                      fontsize=6, color="#ffffff",
                      arrowprops=dict(arrowstyle="->", color="#666666", lw=0.5))
    pad = 0.01
    ax_r.set_xlim(min(lons) - pad, max(lons) + pad)
    ax_r.set_ylim(min(lats) - pad, max(lats) + pad)

ax_r.set_title(f"Orifices / Tidal Gates - {len(orifices)} features",
               color="white", fontsize=11, fontweight="bold", pad=8)
ax_r.text(0.02, 0.98, "CRS: EPSG:4326\nHCMC tidal prevention",
          transform=ax_r.transAxes, va="top", color="#aaaaaa",
          fontsize=7, bbox=dict(facecolor="#00000088", edgecolor="none", pad=3))

fig.suptitle("Urban Drainage Structures (Standardized)",
             color="white", fontsize=14, fontweight="bold", y=1.01)

plt.tight_layout(pad=1.5)
plt.savefig(OUT_PNG, dpi=450, bbox_inches="tight",
            facecolor=fig.get_facecolor())
plt.close()
print(f"\nSaved: {OUT_PNG}")
