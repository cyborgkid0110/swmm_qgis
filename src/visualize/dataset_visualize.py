"""
Render each valid raster in the dataset as an image and save to PNG.
Run with: python dataset_visualize.py
Requires: gdal (osgeo), numpy, matplotlib — all included in qgis-env.
"""
import csv, math, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from osgeo import gdal

gdal.UseExceptions()

CSV_PATH = r"g:\workspace\github\swmm\dataset\dia_hinh_khong_gian\validation_report.csv"
OUT_PNG  = r"g:\workspace\github\swmm\result\visualization\raster_preview.png"

# ── load valid rasters from CSV ───────────────────────────────────────────────
with open(CSV_PATH, newline="", encoding="utf-8") as f:
    rows = [r for r in csv.DictReader(f)
            if r["kind"] == "raster" and r["load_ok"].strip().lower() == "true"]

# ── read raster band as masked numpy array ────────────────────────────────────
def read_band(path):
    ds = gdal.Open(path)
    band = ds.GetRasterBand(1)
    data = band.ReadAsArray().astype(float)

    # mask nodata
    nd = band.GetNoDataValue()
    if nd is not None and not math.isnan(nd):
        data = np.ma.masked_equal(data, nd)
    else:
        data = np.ma.masked_invalid(data)

    ds = None
    return data

# ── pick colourmap by filename heuristic ─────────────────────────────────────
def pick_cmap(filename):
    fn = filename.lower()
    if "hill" in fn or "shade" in fn or "hillshade" in fn:
        return "gray"
    return "terrain"   # DEM / elevation

# ── figure layout ─────────────────────────────────────────────────────────────
n = len(rows)
ncols = min(n, 3)
nrows = math.ceil(n / ncols)

fig, axes = plt.subplots(nrows, ncols,
                         figsize=(7 * ncols, 6 * nrows),
                         squeeze=False)
fig.patch.set_facecolor("#1a1a2e")

for idx, r in enumerate(rows):
    ax = axes[idx // ncols][idx % ncols]
    fp = r["file"]
    fn = os.path.basename(fp)
    cmap = pick_cmap(fn)

    try:
        data = read_band(fp)

        # percentile stretch for better contrast (2–98 %)
        vmin = float(np.nanpercentile(data.compressed(), 2))
        vmax = float(np.nanpercentile(data.compressed(), 98))

        im = ax.imshow(data, cmap=cmap, vmin=vmin, vmax=vmax,
                       aspect="equal", interpolation="bilinear")

        cbar = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02)
        cbar.ax.tick_params(colors="white", labelsize=8)

        crs  = r["crs"] or "unknown CRS"
        w, h = r["width"], r["height"]
        px   = r["pixel_x"]
        px_label = f"{float(px):.4f} {'m' if float(px) > 1 else '°'}" if px else "?"
        mn, mx = r["min_band1"], r["max_band1"]

        title  = fn
        subtitle = (f"CRS: {crs}  |  {int(float(w)):,}×{int(float(h)):,} px  |  "
                    f"pixel: {px_label}\nMin: {float(mn):.1f}  Max: {float(mx):.1f}")

        ax.set_title(title, color="white", fontsize=11, fontweight="bold", pad=6)
        ax.text(0.5, -0.06, subtitle, transform=ax.transAxes,
                ha="center", va="top", fontsize=8, color="#aaaaaa")

    except Exception as e:
        ax.set_facecolor("#2c2c2c")
        ax.text(0.5, 0.5, f"Error reading:\n{fn}\n\n{e}",
                transform=ax.transAxes, ha="center", va="center",
                color="red", fontsize=9)
        ax.set_title(fn, color="white", fontsize=10)

    ax.axis("off")

# hide unused axes
for idx in range(n, nrows * ncols):
    axes[idx // ncols][idx % ncols].set_visible(False)

fig.suptitle("Raster Preview — dia_hinh_khong_gian",
             color="white", fontsize=14, fontweight="bold", y=1.01)

plt.tight_layout(rect=[0, 0, 1, 1])
plt.savefig(OUT_PNG, dpi=450, bbox_inches="tight",
            facecolor=fig.get_facecolor())
plt.close()
print(f"Saved: {OUT_PNG}")
