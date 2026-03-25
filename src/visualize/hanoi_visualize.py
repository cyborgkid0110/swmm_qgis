"""
Side-by-side visualisation of Ha Noi region:
  Left  — DEM raster (Ha Noi_DEM.tif)
  Right — River network clipped to the same extent
Run with: python hanoi_visualize.py
Requires: gdal (osgeo), numpy, matplotlib — all in qgis-env.
"""
import math
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
import matplotlib.cm as cm
from osgeo import gdal, ogr, osr

gdal.UseExceptions()
ogr.UseExceptions()

DEM_PATH = r"g:\workspace\github\swmm\dataset\dia_hinh_khong_gian\Ha Noi_DEM\Ha Noi_DEM.tif"
SHP_PATH = r"g:\workspace\github\swmm\dataset\mang_luoi_song_ho_kenh_muong\river\river.shp"
OUT_PNG  = r"g:\workspace\github\swmm\result\visualization\hanoi_preview.png"

# ── 1. Read DEM ───────────────────────────────────────────────────────────────
ds  = gdal.Open(DEM_PATH)
gt  = ds.GetGeoTransform()
W, H = ds.RasterXSize, ds.RasterYSize

band = ds.GetRasterBand(1)
dem  = band.ReadAsArray().astype(float)
nd   = band.GetNoDataValue()
if nd is not None and not math.isnan(nd):
    dem = np.ma.masked_equal(dem, nd)
else:
    dem = np.ma.masked_invalid(dem)

# UTM 32648 extent of the DEM
utm_minX = gt[0]
utm_maxY = gt[3]
utm_maxX = gt[0] + W * gt[1]
utm_minY = gt[3] + H * gt[5]

# Transform DEM extent → WGS84 for river clipping
src_srs = osr.SpatialReference(); src_srs.ImportFromEPSG(32648)
dst_srs = osr.SpatialReference(); dst_srs.ImportFromEPSG(4326)
src_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
dst_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
xform = osr.CoordinateTransformation(src_srs, dst_srs)

ll = xform.TransformPoint(utm_minX, utm_minY)   # (lon, lat, z)
ur = xform.TransformPoint(utm_maxX, utm_maxY)
lon_min, lat_min = ll[0], ll[1]
lon_max, lat_max = ur[0], ur[1]

ds = None

# ── 2. Load rivers clipped to Ha Noi bbox ────────────────────────────────────
shp_ds = ogr.Open(SHP_PATH)
lyr    = shp_ds.GetLayer(0)
lyr.SetSpatialFilterRect(lon_min, lat_min, lon_max, lat_max)

max_strahler = 6
segments = {}   # order -> [(xs, ys), ...]
order_named = {}

for feat in lyr:
    s    = feat.GetField("Strahler") or 1
    name = feat.GetField("Name")
    geom = feat.GetGeometryRef()
    if geom is None:
        continue

    parts = ([geom.GetGeometryRef(i) for i in range(geom.GetGeometryCount())]
             if geom.GetGeometryCount() > 0 else [geom])

    segments.setdefault(s, [])
    order_named.setdefault(s, 0)

    for part in parts:
        pts = part.GetPoints()
        if not pts:
            continue
        segments[s].append(([p[0] for p in pts], [p[1] for p in pts]))

    if name:
        order_named[s] += 1

shp_ds = None
orders = sorted(segments.keys())

# ── 3. Style helpers ──────────────────────────────────────────────────────────
river_cmap = cm.get_cmap("Blues")

def river_style(s):
    t     = (s - 1) / (max_strahler - 1)
    color = river_cmap(0.35 + 0.65 * t)
    lw    = 0.4 + 2.2 * t
    alpha = 0.55 + 0.45 * t
    return color, lw, alpha

# ── 4. Figure ─────────────────────────────────────────────────────────────────
fig, (ax_dem, ax_riv) = plt.subplots(1, 2, figsize=(18, 9))
fig.patch.set_facecolor("#0d1117")

# ---------- Left: DEM --------------------------------------------------------
ax_dem.set_facecolor("#0d1117")

vmin = float(np.nanpercentile(dem.compressed(), 2))
vmax = float(np.nanpercentile(dem.compressed(), 98))

im = ax_dem.imshow(dem, cmap="terrain", vmin=vmin, vmax=vmax,
                   extent=[utm_minX, utm_maxX, utm_minY, utm_maxY],
                   aspect="equal", origin="upper", interpolation="bilinear")

cbar = fig.colorbar(im, ax=ax_dem, fraction=0.035, pad=0.02)
cbar.set_label("Elevation (m)", color="white", fontsize=9)
cbar.ax.tick_params(colors="white", labelsize=8)

ax_dem.set_title("Ha Noi — DEM (EPSG:32648)", color="white",
                  fontsize=11, fontweight="bold", pad=8)
ax_dem.set_xlabel("Easting (m)",  color="#aaaaaa", fontsize=8)
ax_dem.set_ylabel("Northing (m)", color="#aaaaaa", fontsize=8)
ax_dem.tick_params(colors="#888888", labelsize=7)
for sp in ax_dem.spines.values():
    sp.set_edgecolor("#333333")

# stats annotation
elev_min = float(dem.min())
elev_max = float(dem.max())
ax_dem.text(0.02, 0.98,
            f"Min: {elev_min:.0f} m\nMax: {elev_max:.0f} m\n"
            f"Size: {W:,} × {H:,} px\nPixel: ~{gt[1]:.1f} m",
            transform=ax_dem.transAxes, va="top", ha="left",
            color="white", fontsize=8,
            bbox=dict(facecolor="#00000088", edgecolor="none", pad=4))

# ---------- Right: Rivers ----------------------------------------------------
ax_riv.set_facecolor("#0d1117")
ax_riv.set_aspect("equal")

for s in orders:
    color, lw, alpha = river_style(s)
    for xs, ys in segments[s]:
        ax_riv.plot(xs, ys, color=color, linewidth=lw,
                    alpha=alpha, solid_capstyle="round")

ax_riv.set_xlim(lon_min, lon_max)
ax_riv.set_ylim(lat_min, lat_max)
ax_riv.set_title("Ha Noi — River Network (EPSG:4326)", color="white",
                  fontsize=11, fontweight="bold", pad=8)
ax_riv.set_xlabel("Longitude (°)", color="#aaaaaa", fontsize=8)
ax_riv.set_ylabel("Latitude (°)",  color="#aaaaaa", fontsize=8)
ax_riv.tick_params(colors="#888888", labelsize=7)
for sp in ax_riv.spines.values():
    sp.set_edgecolor("#333333")

# legend
legend_handles = []
for s in orders:
    color, lw, _ = river_style(s)
    n = len(segments[s])
    handle = mlines.Line2D([], [], color=color, linewidth=max(lw, 1.0),
                           label=f"Order {s}  ({n} segs)")
    legend_handles.append(handle)

ax_riv.legend(handles=legend_handles, loc="lower left",
              facecolor="#1a1a2e", edgecolor="#444", labelcolor="white",
              fontsize=8, title="Strahler Order", title_fontsize=9,
              framealpha=0.9)

# river stats
total_segs = sum(len(v) for v in segments.values())
ax_riv.text(0.02, 0.98,
            f"Segments: {total_segs}\nOrders: {min(orders)}–{max(orders)}",
            transform=ax_riv.transAxes, va="top", ha="left",
            color="white", fontsize=8,
            bbox=dict(facecolor="#00000088", edgecolor="none", pad=4))

# ---------- Title & save ------------------------------------------------------
fig.suptitle("Ha Noi Region — Spatial Dataset Overview",
             color="white", fontsize=14, fontweight="bold", y=1.01)

plt.tight_layout(pad=1.5)
plt.savefig(OUT_PNG, dpi=450, bbox_inches="tight",
            facecolor=fig.get_facecolor())
plt.close()
print(f"Saved: {OUT_PNG}")
