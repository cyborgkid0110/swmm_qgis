"""
Migrate all datasets to standardized CSV format.
Creates standardized CSVs for all components defined in docs/standardization_module.md.

Components handled:
  2.1 River       - from river.shp
  2.3 Lake        - sample data (Hanoi)
  2.4 Dam         - from mekongdam_database
  3.1 Sewer       - sample data (Hanoi)
  3.2 Manholes    - sample data (Hanoi)
  3.3 Pumps       - from TRAMBOM2023
  3.4 Weirs       - from CONGDAP2023 + CONGDUOIDE2023
  3.5 Orifices    - from CONGKIEMSOATTRIEU2023
  5.1 Pollution   - from VITRIXATHAI2022 + VITRIXATHAIVAOCTTL2023

Usage:  conda run -n qgis-env python migrate_all.py
"""
import csv, json, os
from osgeo import ogr

ogr.UseExceptions()

BASE = r"g:\workspace\github\swmm\dataset"


# ── helpers ──────────────────────────────────────────────────────────────────

def _enc(path):
    for e in ["utf-8-sig", "utf-8", "latin-1", "cp1258", "cp1252"]:
        try:
            with open(path, encoding=e) as f:
                f.read(4096)
            return e
        except (UnicodeDecodeError, UnicodeError):
            pass
    return "latin-1"


def _pt(lon, lat):
    return json.dumps({"type": "Point", "coordinates": [lon, lat]})


def _ls(coords):
    return json.dumps({"type": "LineString", "coordinates": coords})


def _write(path, fields, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"  -> {os.path.basename(path)}: {len(rows)} rows")


def _read(path):
    enc = _enc(path)
    with open(path, encoding=enc) as f:
        return list(csv.DictReader(f))


def _gjpt(s):
    """Extract (lon, lat) from GeoJSON Shape string."""
    try:
        obj = json.loads(s)
        c = obj["coordinates"]
        return float(c[0]), float(c[1])
    except Exception:
        return None


def _san(text):
    """Sanitize text for CSV output."""
    if not text:
        return ""
    return text.encode("utf-8", errors="replace").decode("utf-8", errors="replace").strip()


# ═════════════════════════════════════════════════════════════════════════════
# 2.1 River  (from river.shp -> rivers.csv)
# ═════════════════════════════════════════════════════════════════════════════

def migrate_rivers():
    print("\n[2.1] Migrating rivers...")
    shp = os.path.join(BASE, r"mang_luoi_song_ho_kenh_muong\river\river.shp")
    out = os.path.join(BASE, r"mang_luoi_song_ho_kenh_muong\rivers.csv")

    FIELDS = [
        "ID", "Name", "Code", "Strahler", "Length_m", "Width_m",
        "BedElev_m", "BankElev_m", "FlowDir", "FromNode", "ToNode",
        "RouteShape", "XSType", "Material", "Basin", "IrrigSys",
        "Location", "Province", "District", "Ward", "Manager",
        "YearBuilt", "YearUpdate", "Status", "Notes",
    ]

    ds = ogr.Open(shp)
    lyr = ds.GetLayer(0)

    # discover field names
    defn = lyr.GetLayerDefn()
    shp_fields = [defn.GetFieldDefn(i).GetName() for i in range(defn.GetFieldCount())]
    print(f"  SHP fields: {shp_fields}")

    rows = []
    for feat in lyr:
        geom = feat.GetGeometryRef()
        if not geom:
            continue

        fid = feat.GetField("OBJECTID") if "OBJECTID" in shp_fields else feat.GetFID()
        name = _san(feat.GetField("Name")) if "Name" in shp_fields else ""
        code = _san(feat.GetField("Code")) if "Code" in shp_fields else ""
        strahler = feat.GetField("Strahler") if "Strahler" in shp_fields else 1
        length = feat.GetField("Length") if "Length" in shp_fields else 0

        route_shape = geom.ExportToJson()

        row = {f: "" for f in FIELDS}
        row.update({
            "ID": fid or feat.GetFID(),
            "Name": name,
            "Code": code,
            "Strahler": strahler or 1,
            "Length_m": length or 0,
            "FromNode": f"RN{fid}_start",
            "ToNode": f"RN{fid}_end",
            "RouteShape": route_shape,
        })
        rows.append(row)

    ds = None
    _write(out, FIELDS, rows)


# ═════════════════════════════════════════════════════════════════════════════
# 2.3 Lake / Detention Pond  (sample data - Hanoi)
# ═════════════════════════════════════════════════════════════════════════════

def create_lakes():
    print("\n[2.3] Creating lake samples (Hanoi)...")
    out = os.path.join(BASE, r"mang_luoi_song_ho_kenh_muong\lakes.csv")

    FIELDS = [
        "ID", "Name", "Group", "Area_ha", "BedArea_ha", "Vol_m3",
        "BedElev_m", "CrestElv", "BankElev_m", "NatWtrLvl", "WetLvl_m",
        "DryLvl_m", "NumInlets", "Perim_m", "IrrigSys",
        "Location", "Province", "District", "Ward", "Manager",
        "YearBuilt", "YearUpdate", "Status", "Notes", "Shape",
    ]

    lakes = [
        {"ID": 1, "Name": "Ho Tay", "Group": "Ho dieu hoa",
         "Area_ha": 527.0, "BedArea_ha": 480.0, "Vol_m3": 10600000,
         "BedElev_m": 3.5, "CrestElv": 7.5, "BankElev_m": 7.0,
         "NatWtrLvl": 5.8, "WetLvl_m": 6.5, "DryLvl_m": 5.0,
         "NumInlets": 8, "Perim_m": 17000,
         "Location": "Tay Ho, Ha Noi", "Province": "Ha Noi",
         "District": "Tay Ho", "Status": "Active",
         "lon": 105.828, "lat": 21.058},

        {"ID": 2, "Name": "Ho Hoan Kiem", "Group": "Ho dieu hoa",
         "Area_ha": 12.0, "BedArea_ha": 10.5, "Vol_m3": 270000,
         "BedElev_m": 4.0, "CrestElv": 7.8, "BankElev_m": 7.2,
         "NatWtrLvl": 6.0, "WetLvl_m": 6.8, "DryLvl_m": 5.5,
         "NumInlets": 3, "Perim_m": 1750,
         "Location": "Hoan Kiem, Ha Noi", "Province": "Ha Noi",
         "District": "Hoan Kiem", "Status": "Active",
         "lon": 105.852, "lat": 21.029},

        {"ID": 3, "Name": "Ho Bay Mau", "Group": "Ho dieu hoa",
         "Area_ha": 20.0, "BedArea_ha": 17.0, "Vol_m3": 450000,
         "BedElev_m": 3.8, "CrestElv": 7.2, "BankElev_m": 6.8,
         "NatWtrLvl": 5.5, "WetLvl_m": 6.2, "DryLvl_m": 4.8,
         "NumInlets": 4, "Perim_m": 2200,
         "Location": "Hai Ba Trung, Ha Noi", "Province": "Ha Noi",
         "District": "Hai Ba Trung", "Status": "Active",
         "lon": 105.852, "lat": 21.017},

        {"ID": 4, "Name": "Ho Truc Bach", "Group": "Ho dieu hoa",
         "Area_ha": 22.0, "BedArea_ha": 19.0, "Vol_m3": 520000,
         "BedElev_m": 3.2, "CrestElv": 7.0, "BankElev_m": 6.5,
         "NatWtrLvl": 5.2, "WetLvl_m": 6.0, "DryLvl_m": 4.5,
         "NumInlets": 3, "Perim_m": 2500,
         "Location": "Ba Dinh, Ha Noi", "Province": "Ha Noi",
         "District": "Ba Dinh", "Status": "Active",
         "lon": 105.840, "lat": 21.048},

        {"ID": 5, "Name": "Ho Thanh Cong", "Group": "Ho dieu hoa",
         "Area_ha": 6.0, "BedArea_ha": 5.0, "Vol_m3": 120000,
         "BedElev_m": 4.2, "CrestElv": 7.6, "BankElev_m": 7.0,
         "NatWtrLvl": 5.8, "WetLvl_m": 6.5, "DryLvl_m": 5.2,
         "NumInlets": 2, "Perim_m": 1100,
         "Location": "Dong Da, Ha Noi", "Province": "Ha Noi",
         "District": "Dong Da", "Status": "Active",
         "lon": 105.823, "lat": 21.015},
    ]

    rows = []
    for lk in lakes:
        row = {f: "" for f in FIELDS}
        row["Shape"] = _pt(lk.pop("lon"), lk.pop("lat"))
        row.update(lk)
        rows.append(row)

    _write(out, FIELDS, rows)


# ═════════════════════════════════════════════════════════════════════════════
# (congdap migration removed — merged into migrate_weirs() under Group 3)
# ═════════════════════════════════════════════════════════════════════════════


# ═════════════════════════════════════════════════════════════════════════════
# 2.4 Dam / Hydraulic Structure  (mekongdam -> dams.csv)
# ═════════════════════════════════════════════════════════════════════════════

def migrate_mekong_dams():
    print("\n[2.4b] Migrating Mekong dams...")
    csv_path = os.path.join(BASE,
        r"mang_luoi_song_ho_kenh_muong\mekongdam_database.csv")
    out = os.path.join(BASE, r"mang_luoi_song_ho_kenh_muong\dams.csv")

    FIELDS = [
        "ID", "Name", "Type", "Form", "Chainage", "River", "Basin",
        "Length_m", "Width_m", "Height_m", "Diam_m", "Openings",
        "InvElev_m", "CrestElv", "Cap_MW", "Vol_Mm3", "Catch_km2",
        "Elev_m", "Grade", "Operation", "Purpose", "SvcArea",
        "IrrigSys", "Country", "Complete",
        "Location", "Province", "District", "Ward", "Manager",
        "YearBuilt", "YearUpdate", "Status", "Notes", "Shape",
    ]

    MAP = {
        "ID": "ID", "Name1": "Name", "River": "River", "Basin": "Basin",
        "Height_m": "Height_m", "Length_m": "Length_m",
        "Capacity_MW": "Cap_MW", "Volume_milm3": "Vol_Mm3",
        "Catch_km2": "Catch_km2", "Elevation_m": "Elev_m",
        "Use1": "Purpose", "Area_km2": "SvcArea",
        "Country": "Country", "Completion": "Complete",
        "Status": "Status", "Locality": "Location",
    }

    src = _read(csv_path)
    rows = []
    for r in src:
        lat_s = r.get("Lat", "").strip()
        lon_s = r.get("Lon", "").strip()
        if not lat_s or not lon_s:
            continue
        try:
            lat, lon = float(lat_s), float(lon_s)
        except ValueError:
            continue

        row = {f: "" for f in FIELDS}
        row["Shape"] = _pt(lon, lat)
        row["Type"] = "Dam"
        for csv_col, std_col in MAP.items():
            val = _san(r.get(csv_col, ""))
            if val and val != "<Null>":
                row[std_col] = val
        rows.append(row)

    _write(out, FIELDS, rows)


# ═════════════════════════════════════════════════════════════════════════════
# 3.1 Sewer Network  (sample data - Hanoi)
# ═════════════════════════════════════════════════════════════════════════════

def create_sewers():
    print("\n[3.1] Creating sewer samples (Hanoi)...")
    out = os.path.join(BASE, r"thoat_nuoc\sewers.csv")

    FIELDS = [
        "ID", "Name", "Type", "Diam_mm", "Size_mm", "Length_m",
        "Material", "XSArea", "FlowDir", "FromNode", "ToNode",
        "RouteShape", "XSType", "StreetID", "DrainZone", "Catchment",
        "Location", "Province", "District", "Ward", "Manager",
        "YearBuilt", "YearUpdate", "Status", "Notes",
    ]

    # Manhole positions (ID -> (lat, lon))
    MH = {
        "MH01": (21.030, 105.848), "MH02": (21.028, 105.848),
        "MH03": (21.026, 105.848), "MH04": (21.024, 105.848),
        "MH05": (21.030, 105.851), "MH06": (21.028, 105.851),
        "MH07": (21.026, 105.851), "MH08": (21.024, 105.851),
        "MH09": (21.030, 105.854), "MH10": (21.028, 105.854),
        "MH11": (21.026, 105.854), "MH12": (21.024, 105.854),
        "OF01": (21.022, 105.851),
    }

    # Sewer segments: (id, name, from, to, diam_mm, material, xs_type)
    SEGS = [
        (1,  "Tuyen ong 1A", "MH01", "MH02", 400, "BTCT", "CIRCULAR"),
        (2,  "Tuyen ong 1B", "MH02", "MH03", 400, "BTCT", "CIRCULAR"),
        (3,  "Tuyen ong 1C", "MH03", "MH04", 600, "BTCT", "CIRCULAR"),
        (4,  "Tuyen ong 2A", "MH05", "MH06", 400, "BTCT", "CIRCULAR"),
        (5,  "Tuyen ong 2B", "MH06", "MH07", 600, "BTCT", "CIRCULAR"),
        (6,  "Tuyen ong 2C", "MH07", "MH08", 800, "BTCT", "CIRCULAR"),
        (7,  "Tuyen ong 3A", "MH09", "MH10", 400, "PVC",  "CIRCULAR"),
        (8,  "Tuyen ong 3B", "MH10", "MH11", 400, "PVC",  "CIRCULAR"),
        (9,  "Tuyen ong 3C", "MH11", "MH12", 600, "BTCT", "CIRCULAR"),
        (10, "Nhanh T1-T2",  "MH04", "MH08", 600, "BTCT", "RECT_CLOSED"),
        (11, "Nhanh T3-T2",  "MH12", "MH08", 600, "BTCT", "RECT_CLOSED"),
        (12, "Cong chinh",   "MH08", "OF01", 1200,"BTCT", "RECT_CLOSED"),
    ]

    import math
    rows = []
    for sid, name, fn, tn, diam, mat, xs in SEGS:
        lat1, lon1 = MH[fn]
        lat2, lon2 = MH[tn]
        # approximate length in metres
        dlat = (lat2 - lat1) * 111320
        dlon = (lon2 - lon1) * 111320 * math.cos(math.radians((lat1+lat2)/2))
        length = round(math.sqrt(dlat**2 + dlon**2), 1)
        xs_area = round(math.pi * (diam/2000)**2, 4) if xs == "CIRCULAR" else ""
        size_mm = "" if xs == "CIRCULAR" else f"{diam}x{diam}"

        row = {f: "" for f in FIELDS}
        row.update({
            "ID": sid, "Name": name, "Type": "Cong thoat nuoc",
            "Diam_mm": diam if xs == "CIRCULAR" else "",
            "Size_mm": size_mm,
            "Length_m": length, "Material": mat,
            "XSArea": xs_area, "FlowDir": "S",
            "FromNode": fn, "ToNode": tn,
            "RouteShape": _ls([[lon1, lat1], [lon2, lat2]]),
            "XSType": xs, "DrainZone": "DZ-HK01",
            "Catchment": "LV-HK01",
            "Location": "Hoan Kiem, Ha Noi", "Province": "Ha Noi",
            "District": "Hoan Kiem", "Status": "Active",
        })
        rows.append(row)

    _write(out, FIELDS, rows)


# ═════════════════════════════════════════════════════════════════════════════
# 3.2 Manholes  (sample data - Hanoi)
# ═════════════════════════════════════════════════════════════════════════════

def create_manholes():
    print("\n[3.2] Creating manhole samples (Hanoi)...")
    out = os.path.join(BASE, r"thoat_nuoc\manholes.csv")

    FIELDS = [
        "ID", "Name", "Type", "Area_m2", "Size_m", "CoverType",
        "InvElev_m", "RimElev_m", "SewerLine",
        "StreetID", "DrainZone", "Catchment",
        "Location", "Province", "District", "Ward", "Manager",
        "YearBuilt", "YearUpdate", "Status", "Notes", "Shape",
    ]

    # Manhole positions (same grid as sewers)
    MH_DATA = [
        (1,  "MH01", 21.030, 105.848, 8.5, 5.5, "Tuyen ong 1A", "Ho ga tron"),
        (2,  "MH02", 21.028, 105.848, 8.3, 5.3, "Tuyen ong 1A", "Ho ga tron"),
        (3,  "MH03", 21.026, 105.848, 8.0, 5.0, "Tuyen ong 1B", "Ho ga vuong"),
        (4,  "MH04", 21.024, 105.848, 7.8, 4.8, "Tuyen ong 1C", "Ho ga vuong"),
        (5,  "MH05", 21.030, 105.851, 8.4, 5.4, "Tuyen ong 2A", "Ho ga tron"),
        (6,  "MH06", 21.028, 105.851, 8.2, 5.2, "Tuyen ong 2A", "Ho ga tron"),
        (7,  "MH07", 21.026, 105.851, 7.9, 4.9, "Tuyen ong 2B", "Ho ga vuong"),
        (8,  "MH08", 21.024, 105.851, 7.6, 4.6, "Tuyen ong 2C", "Ho ga vuong"),
        (9,  "MH09", 21.030, 105.854, 8.6, 5.6, "Tuyen ong 3A", "Ho ga tron"),
        (10, "MH10", 21.028, 105.854, 8.3, 5.3, "Tuyen ong 3A", "Ho ga tron"),
        (11, "MH11", 21.026, 105.854, 8.1, 5.1, "Tuyen ong 3B", "Ho ga vuong"),
        (12, "MH12", 21.024, 105.854, 7.7, 4.7, "Tuyen ong 3C", "Ho ga vuong"),
    ]

    rows = []
    for mid, name, lat, lon, rim, inv, sewer, mtype in MH_DATA:
        row = {f: "" for f in FIELDS}
        row.update({
            "ID": mid, "Name": name, "Type": mtype,
            "Area_m2": 1.0 if "tron" in mtype else 1.2,
            "Size_m": "D1.0" if "tron" in mtype else "1.0x1.2",
            "CoverType": "Gang",
            "InvElev_m": inv, "RimElev_m": rim,
            "SewerLine": sewer,
            "DrainZone": "DZ-HK01", "Catchment": "LV-HK01",
            "Location": "Hoan Kiem, Ha Noi", "Province": "Ha Noi",
            "District": "Hoan Kiem", "Status": "Active",
            "Shape": _pt(lon, lat),
        })
        rows.append(row)

    _write(out, FIELDS, rows)


# ═════════════════════════════════════════════════════════════════════════════
# 3.3 Pumping Stations  (from TRAMBOM2023)
# ═════════════════════════════════════════════════════════════════════════════

def migrate_pumps():
    print("\n[3.3] Migrating pumping stations (TRAMBOM2023)...")
    csv_path = os.path.join(BASE, r"thoat_nuoc\HTQLTL_CTTL_TRAMBOM2023.csv")
    out = os.path.join(BASE, r"thoat_nuoc\pumps.csv")

    FIELDS = [
        "ID", "Name", "Source", "SewerLine",
        "Type", "Grade", "NumPumps", "Cap_m3s",
        "InElev_m", "OutElev_m", "AutoMonit", "TrashScr",
        "Purpose", "SvcArea", "IrrigSys", "StreetID",
        "Location", "Province", "District", "Ward", "Manager",
        "YearBuilt", "YearUpdate", "Status", "Notes", "Shape",
    ]

    MAP = {
        "stt_id": "ID", "TenTramBom": "Name",
        "Loai": "Type", "CongSuat": "Cap_m3s",
        "MucTieuNhiemVu": "Purpose", "DienTichPhucVu_ha": "SvcArea",
        "DiaDiem": "Location", "HeThongCongTrinhThuyLoi": "IrrigSys",
        "NamSuDung": "YearBuilt", "NamCapNhat": "YearUpdate",
        "DonViQuanLy": "Manager", "GhiChu": "Notes",
    }

    src = _read(csv_path)
    rows = []
    for i, r in enumerate(src, 1):
        shape_str = r.get("Shape", "").strip()
        coords = _gjpt(shape_str)
        if not coords:
            continue
        lon, lat = coords

        row = {f: "" for f in FIELDS}
        row["Shape"] = _pt(lon, lat)
        for csv_col, std_col in MAP.items():
            val = _san(r.get(csv_col, ""))
            if val and val != "<Null>":
                row[std_col] = val
        rows.append(row)

    _write(out, FIELDS, rows)


# ═════════════════════════════════════════════════════════════════════════════
# 3.4 Weirs  (from CONGDAP2023 + CONGDUOIDE2023 -> weir.csv)
# ═════════════════════════════════════════════════════════════════════════════

def migrate_weirs():
    print("\n[3.4] Migrating weirs (CONGDAP2023 + CONGDUOIDE2023)...")
    out = os.path.join(BASE, r"thoat_nuoc\weir.csv")

    FIELDS = [
        "ID", "Name", "Type", "Form", "Chainage", "River", "Basin",
        "Length_m", "Width_m", "Height_m", "Diam_m", "Openings",
        "InvElev_m", "CrestElv", "Grade", "Operation",
        "Purpose", "Receiver", "Project", "SvcArea",
        "IrrigSys", "Location", "Province", "District", "Ward", "Manager",
        "YearBuilt", "YearUpdate", "Status", "Notes", "Shape",
    ]

    # --- Part 1: CONGDAP2023 (3,707 records) ---
    CONGDAP_MAP = {
        "stt": "ID", "TenCongDap": "Name", "LoaiCongTrinh": "Type",
        "HinhThuc": "Form", "LyTrinh": "Chainage",
        "ChieuDai": "Length_m", "BeRong": "Width_m", "ChieuCao": "Height_m",
        "DuongKinh": "Diam_m", "SoCua": "Openings",
        "CaoTrinhDayCong": "InvElev_m", "CaoTrinhDinhCong": "CrestElv",
        "CapCongTrinh": "Grade", "HinhThucVanHanh": "Operation",
        "MucTieuNhiemVu": "Purpose", "DienTichPhucVu_ha": "SvcArea",
        "HeThongCongTrinhThuyLoi": "IrrigSys",
        "DiaDiem": "Location", "DonViQuanLy": "Manager",
        "NamSuDung": "YearBuilt", "NamCapNhat": "YearUpdate",
        "GhiChu": "Notes",
    }

    congdap_path = os.path.join(BASE,
        "mang_luoi_song_ho_kenh_muong\\HTQLTL_CTTL_C\u1ed0NGDAP2023.csv")
    rows = []

    if os.path.exists(congdap_path):
        src = _read(congdap_path)
        for r in src:
            shape_str = r.get("Shape", "").strip()
            coords = _gjpt(shape_str)
            if not coords:
                continue
            lon, lat = coords
            row = {f: "" for f in FIELDS}
            row["Shape"] = _pt(lon, lat)
            for csv_col, std_col in CONGDAP_MAP.items():
                val = _san(r.get(csv_col, ""))
                if val and val != "<Null>":
                    row[std_col] = val
            rows.append(row)
        print(f"  CONGDAP2023: {len(rows)} records")

    # --- Part 2: CONGDUOIDE2023 (43 records) ---
    OUTLETS_MAP = {
        "stt_id": "ID", "TenCongDap": "Name",
        "LoaiCongTrinh": "Type", "HinhThuc": "Form",
        "ChieuDai": "Length_m", "DuongKinh": "Diam_m",
        "BeRong": "Width_m", "ChieuCao": "Height_m",
        "SoCua": "Openings",
        "CaoTrinhDayCong": "InvElev_m", "CaoTrinhDinhCong": "CrestElv",
        "HinhThucVanHanh": "Operation", "MucTieuNhiemVu": "Purpose",
        "DiaDiem": "Location", "CumCongTrinh": "Project",
        "NamSuDung": "YearBuilt", "NamCapNhat": "YearUpdate",
        "GhiChu": "Notes",
    }

    outlets_path = os.path.join(BASE,
        r"thoat_nuoc\HTQLTL_DA1547GD1_CONGDUOIDE2023.csv")
    n_outlets = 0

    if os.path.exists(outlets_path):
        src = _read(outlets_path)
        # Continue ID numbering from congdap
        next_id = max((int(r.get("ID", 0) or 0) for r in rows), default=0) + 1
        for r in src:
            shape_str = r.get("Shape", "").strip()
            coords = _gjpt(shape_str)
            if not coords:
                continue
            lon, lat = coords
            row = {f: "" for f in FIELDS}
            row["Shape"] = _pt(lon, lat)
            row["ID"] = next_id
            next_id += 1
            for csv_col, std_col in OUTLETS_MAP.items():
                if std_col == "ID":
                    continue  # use sequential ID
                val = _san(r.get(csv_col, ""))
                if val and val != "<Null>":
                    row[std_col] = val
            # Default type for outlets records
            if not row["Type"]:
                row["Type"] = "Cong duoi de"
            rows.append(row)
            n_outlets += 1
        print(f"  CONGDUOIDE2023: {n_outlets} records")

    print(f"  Total merged: {len(rows)} records")
    _write(out, FIELDS, rows)


# ═════════════════════════════════════════════════════════════════════════════
# 3.5 Orifices / Control Gates  (from CONGKIEMSOATTRIEU2023)
# ═════════════════════════════════════════════════════════════════════════════

def migrate_orifices():
    print("\n[3.5] Migrating orifices (CONGKIEMSOATTRIEU2023)...")
    csv_path = os.path.join(BASE,
        r"thoat_nuoc\HTQLTL_DA1547GD1_CONGKIEMSOATTRIEU2023.csv")
    out = os.path.join(BASE, r"thoat_nuoc\orifices.csv")

    FIELDS = [
        "ID", "Name", "FromNode", "ToNode", "Position",
        "Type", "Form", "Length_m", "Width_m", "Height_m",
        "Openings", "InvElev_m", "CrestElv",
        "DischCoef", "ClearSpan", "SillElev", "GateMtrl", "GateCtrl",
        "Purpose", "Receiver", "SvcArea", "Grade",
        "Location", "Province", "District", "Ward", "Manager",
        "YearBuilt", "YearUpdate", "Status", "Notes", "Shape",
    ]

    MAP = {
        "stt": "ID", "TenCongDap": "Name", "ViTri": "Position",
        "LoaiCongTrinh": "Type", "HinhThuc": "Form",
        "ChieuDai": "Length_m", "BeRong": "Width_m", "ChieuCao": "Height_m",
        "SoCua": "Openings",
        "CaoTrinhDayCong": "InvElev_m", "CaoTrinhDinhCong": "CrestElv",
        "CC_KhauDo_m": "ClearSpan", "CC_CaoTrinhNguong_m": "SillElev",
        "CC_LoaiVatLieuCuaVan": "GateMtrl",
        "CC_KieuDongMoCuaVan": "GateCtrl",
        "MucTieuNhiemVu": "Purpose", "DienTichPhucVu_ha": "SvcArea",
        "CapCongTrinh": "Grade",
        "DiaDiem": "Location",
        "NamSuDung": "YearBuilt", "NamCapNhat": "YearUpdate",
        "GhiChu": "Notes",
    }

    src = _read(csv_path)
    rows = []
    for i, r in enumerate(src, 1):
        shape_str = r.get("Shape", "").strip()
        coords = _gjpt(shape_str)
        if not coords:
            continue
        lon, lat = coords

        row = {f: "" for f in FIELDS}
        row["Shape"] = _pt(lon, lat)
        row["FromNode"] = f"OR{i}_up"
        row["ToNode"] = f"OR{i}_dn"
        for csv_col, std_col in MAP.items():
            val = _san(r.get(csv_col, ""))
            if val and val != "<Null>":
                row[std_col] = val
        rows.append(row)

    _write(out, FIELDS, rows)


# ═════════════════════════════════════════════════════════════════════════════
# 5.1 Pollution Sources  (VITRIXATHAI2022)
# ═════════════════════════════════════════════════════════════════════════════

def migrate_discharge_2022():
    print("\n[5.1a] Migrating discharge 2022 (VITRIXATHAI2022)...")
    csv_path = os.path.join(BASE,
        r"nguon_thai\HTQLTL_CTTL_VITRIXATHAI2022.csv")
    out = os.path.join(BASE, r"nguon_thai\discharge.csv")

    FIELDS = [
        "ID", "Name", "Discharger", "Address", "Industry",
        "Receiver", "DischPt", "IrrigSys", "Treatment",
        "Permit", "PermitOrg", "Standard", "FlowRate",
        "ExpiryDt", "DischTerm",
        "Location", "Province", "District", "Ward", "Manager",
        "YearBuilt", "YearUpdate", "Status", "Notes", "Shape",
    ]

    MAP = {
        "stt": "ID", "Title": "Name",
        "DonViXaThai": "Discharger",
        "DonViCapGiayPhep": "PermitOrg",
        "NamCapNhat": "YearUpdate",
    }

    src = _read(csv_path)
    rows = []
    for r in src:
        shape_str = r.get("Shape", "").strip()
        coords = _gjpt(shape_str)
        if not coords:
            continue
        lon, lat = coords

        row = {f: "" for f in FIELDS}
        row["Shape"] = _pt(lon, lat)
        for csv_col, std_col in MAP.items():
            val = _san(r.get(csv_col, ""))
            if val and val != "<Null>":
                row[std_col] = val
        rows.append(row)

    _write(out, FIELDS, rows)


# ═════════════════════════════════════════════════════════════════════════════
# 5.1 Pollution Sources  (VITRIXATHAIVAOCTTL2023)
# ═════════════════════════════════════════════════════════════════════════════

def migrate_discharge_2023():
    print("\n[5.1b] Migrating discharge 2023 (VITRIXATHAIVAOCTTL2023)...")
    csv_path = os.path.join(BASE,
        r"nguon_thai\HTQLTL_CTTL_VITRIXATHAIVAOCTTL2023.csv")
    out = os.path.join(BASE, r"nguon_thai\discharge.csv")

    FIELDS = [
        "ID", "Name", "Discharger", "Address", "Industry",
        "Receiver", "DischPt", "IrrigSys", "Treatment",
        "Permit", "PermitOrg", "Standard", "FlowRate",
        "ExpiryDt", "DischTerm",
        "Location", "Province", "District", "Ward", "Manager",
        "YearBuilt", "YearUpdate", "Status", "Notes", "Shape",
    ]

    MAP = {
        "stt": "ID", "Title": "Name",
        "DonViXaThai": "Discharger", "DiaChi": "Address",
        "NganhNghe": "Industry", "NguonTiepNhan": "Receiver",
        "ViTriXaThai": "DischPt", "HTCTTL": "IrrigSys",
        "HTXLNT": "Treatment", "GPXT": "Permit",
        "DonViCapPhep": "PermitOrg", "QuyChuanXT": "Standard",
        "LLXT": "FlowRate", "NgayHetHan": "ExpiryDt",
        "ThoiHanXaThai": "DischTerm",
        "NamCapNhat": "YearUpdate", "GhiChu": "Notes",
    }

    src = _read(csv_path)
    rows = []
    for r in src:
        shape_str = r.get("Shape", "").strip()
        coords = _gjpt(shape_str)
        if not coords:
            continue
        lon, lat = coords

        row = {f: "" for f in FIELDS}
        row["Shape"] = _pt(lon, lat)
        for csv_col, std_col in MAP.items():
            val = _san(r.get(csv_col, ""))
            if val and val != "<Null>":
                row[std_col] = val
        rows.append(row)

    _write(out, FIELDS, rows)


# ═════════════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("Dataset Migration - All Components")
    print("=" * 60)

    migrate_rivers()
    create_lakes()
    migrate_mekong_dams()
    create_sewers()
    create_manholes()
    migrate_pumps()
    migrate_weirs()
    migrate_orifices()
    migrate_discharge_2022()
    migrate_discharge_2023()

    print("\n" + "=" * 60)
    print("All migrations complete.")
