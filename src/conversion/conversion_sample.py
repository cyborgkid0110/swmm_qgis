"""
SWMM Conversion - Sample Region

Generates SWMM .inp file from cropped sample_region/ datasets.
Region: HCM sub-area (lon 106.44-106.54, lat 10.6-11.2).

Usage:
    conda run -n qgis-env python src/conversion/conversion_sample.py
"""

import os
import sys

REPO_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLUGIN_DIR = os.path.join(REPO_DIR, "generate_swmm_inp")

# ---------- QGIS init -------------------------------------------------------
sys.path.append(os.path.join(os.environ.get("CONDA_PREFIX", ""), "Library", "python"))

from qgis.core import QgsApplication, QgsProject

QgsApplication.setPrefixPath(os.environ.get("QGIS_PREFIX_PATH", ""), True)
qgs = QgsApplication([], False)
qgs.initQgis()

sys.path.insert(0, os.path.dirname(PLUGIN_DIR))

try:
    from .conversion import Conversion
except ImportError:
    from conversion import Conversion

# Sample region bbox (same as used in crop_sample_region.py)
SAMPLE_BBOX = (106.46, 11.09, 106.53, 11.16)


def run_sample():
    dataset_dir = os.path.join(REPO_DIR, "sample_region")
    result_dir = os.path.join(REPO_DIR, "result", "swmm_output")
    inp_file = os.path.join(result_dir, "sample_region.inp")

    dem_path = os.path.join(dataset_dir, "dia_hinh_khong_gian",
                            "dem", "dem_compress.tif")
    # No bbox filter needed — data is already cropped
    conv = Conversion(dataset_dir=dataset_dir, result_dir=result_dir,
                      dem_path=dem_path)

    print("=" * 60)
    print("SWMM Conversion - Sample Region")
    print(f"  BBOX: {SAMPLE_BBOX}")
    print(f"  Dataset: {dataset_dir}")
    print("=" * 60)

    # --- Load DEM ---
    if conv.dem_path:
        print("\n[DEM]")
        conv._load_dem()

    # --- Build coordinate registry pre-seeded with manholes ---
    print("\n[Coordinate registry]")
    manhole_index = conv._build_manhole_index()
    coord_registry = {}
    for key, mh in manhole_index.items():
        coord_registry[key] = mh.copy()
    print(f"  Pre-seeded with {len(coord_registry)} manhole coordinates")

    # --- Build lake and outfall lookup indices ---
    lake_index = conv._build_lake_index()
    outfall_index = conv._build_outfall_index()
    print(f"  Lake index: {len(lake_index)} lakes")
    print(f"  Outfall index: {len(outfall_index)} outfalls")

    all_auto = []

    # --- Node layers ---
    print("\n[Node layers]")
    junctions_layer, _ = conv.create_junctions()
    storage_layer, _ = conv.create_storage()

    # --- Sewer conduits first (establishes sewer junctions in coord_registry) ---
    print("\n[Sewer conduits]")
    conduits_layer, sewer_aj = conv.create_conduits(coord_registry=coord_registry)
    all_auto += sewer_aj

    # --- Congdap spatial index ---
    print("\n[Congdap spatial index]")
    congdap_index, matched_cd_ids, _unmatched = \
        conv._build_congdap_spatial_index(conv.weirs_csv, conv.canals_csv)
    print(f"  Matched: {len(matched_cd_ids)} congdap -> canal segments")
    print(f"  Unmatched: {len(_unmatched)} standalone weirs")

    # --- Decomposed canal/river conduits (canals with inline weirs) ---
    print("\n[Decomposed LineString conduits]")
    weirs_layer = conv._line_layer("weirs", conv._weir_fields())

    canal_layer, cj, inline_weir_feats, inline_weir_aj = \
        conv.create_canal_conduits(
            coord_registry=coord_registry,
            congdap_index=congdap_index,
            weir_layer=weirs_layer)
    all_auto += cj + inline_weir_aj

    if inline_weir_feats:
        weirs_layer.dataProvider().addFeatures(inline_weir_feats)
        weirs_layer.updateExtents()

    conduits_layer.dataProvider().addFeatures(list(canal_layer.getFeatures()))
    conduits_layer.updateExtents()
    print(f"  Merged canals into CONDUITS -> {conduits_layer.featureCount()} total")

    # Standalone weirs (unmatched congdap only)
    standalone_weir_layer, wj = conv.create_weirs(exclude_ids=matched_cd_ids)
    all_auto += wj
    weirs_layer.dataProvider().addFeatures(list(standalone_weir_layer.getFeatures()))
    weirs_layer.updateExtents()
    print(f"  Total WEIRS: {weirs_layer.featureCount()} "
          f"({len(inline_weir_feats)} inline + "
          f"{standalone_weir_layer.featureCount()} standalone)")

    river_layer, rj, _, _ = conv.create_river_conduits(coord_registry=coord_registry)
    all_auto += rj
    conduits_layer.dataProvider().addFeatures(list(river_layer.getFeatures()))
    conduits_layer.updateExtents()
    print(f"  Merged rivers into CONDUITS -> {conduits_layer.featureCount()} total")

    # --- Outfalls replace nearest junction on SewerLine route ---
    # (runs after sewer+canal+river decomposition so all route junctions exist)
    print("\n[Outfalls]")
    outfalls_layer, outfall_replaces = conv.create_outfalls(
        coord_registry=coord_registry)

    # --- Orifices & pumps (need lake_index + full coord_registry) ---
    print("\n[Link layers]")
    pumps_layer, pj = conv.create_pumps(
        coord_registry=coord_registry, lake_index=lake_index)
    orifices_layer, orj = conv.create_orifices(
        coord_registry=coord_registry, lake_index=lake_index)
    all_auto += pj + orj

    # --- Merge auto-junctions (exclude names replaced by outfalls) ---
    print("\n[Merging auto-junctions]")
    conv._add_auto_junctions(junctions_layer, all_auto,
                             exclude_names=outfall_replaces)

    # --- DEM elevation refinement ---
    conv._refine_elevations(junctions_layer, storage_layer, outfalls_layer)

    # --- Rain gages & subcatchments ---
    print("\n[Rain gages & Subcatchments]")
    raingages_layer = conv.create_raingages()
    subcatchments_layer = conv.create_subcatchments(coord_registry=coord_registry)

    # --- Tables ---
    print("\n[Tables]")
    options_path = conv.create_options_table(
        os.path.join(result_dir, "sample_options.xlsx")
    )
    timeseries_path = conv.create_timeseries_table(
        os.path.join(result_dir, "sample_timeseries.xlsx")
    )

    # --- QGIS project + export ---
    print("\n[QGIS project]")
    project = QgsProject.instance()
    layers = [junctions_layer, outfalls_layer, storage_layer,
              conduits_layer, pumps_layer,
              orifices_layer, weirs_layer,
              raingages_layer, subcatchments_layer]
    for lyr in layers:
        project.addMapLayer(lyr)
    print("  Layers added to project")

    print("\n[Processing framework]")
    import processing
    from processing.core.Processing import Processing
    Processing.initialize()

    from generate_swmm_inp.generate_swmm_provider import GenerateSwmmProvider
    provider = GenerateSwmmProvider()
    QgsApplication.processingRegistry().addProvider(provider)
    print("  Plugin provider registered")

    print("\n[GenerateSwmmInpFile]")
    processing.run(
        "GenSwmmInp:GenerateSwmmInpFile",
        {
            "QGIS_OUT_INP_FILE": inp_file,
            "FILE_JUNCTIONS": junctions_layer,
            "FILE_OUTFALLS": outfalls_layer,
            "FILE_STORAGES": storage_layer,
            "FILE_CONDUITS": conduits_layer,
            "FILE_PUMPS": pumps_layer,
            "FILE_OUTLETS": conv._line_layer("outlets", []),
            "FILE_ORIFICES": orifices_layer,
            "FILE_WEIRS": weirs_layer,
            "FILE_RAINGAGES": raingages_layer,
            "FILE_SUBCATCHMENTS": subcatchments_layer,
            "FILE_OPTIONS": options_path,
            "FILE_TIMESERIES": timeseries_path,
            "USE_Z_VALS": False,
        },
    )

    print("\n" + "=" * 60)
    if os.path.exists(inp_file):
        size = os.path.getsize(inp_file)
        print(f"SUCCESS: {inp_file}")
        print(f"   File size: {size:,} bytes")
    else:
        print("ERROR: .inp file was not created")
    print("=" * 60)

    return inp_file


if __name__ == "__main__":
    run_sample()
    qgs.exitQgis()
