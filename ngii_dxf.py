"""국토정보플랫폼(국토지리정보원) 수치지형도 DXF 도엽: 로컬 저장 → 색인 → 필지 주변만 잘라 CAD 로 내보내기.

- 도엽은 사용자가 국토정보플랫폼에서 한 번 내려받아 올린다(재배포 제한 자료). 저장 위치는 저장소 밖(%LOCALAPPDATA%/law-checker/ngii)이며
  저장소·외부로 복사하지 않는다.
- 좌표는 도엽 DXF 의 값을 그대로 쓴다(1:5,000 신규 도엽은 GRS80 중부원점 = EPSG:5186 으로 표기). 범위가 5186 과 맞지 않으면 사용하지 않고 알린다.
- 잘라내기: 각 도형의 경계 상자가 조회 창과 겹치면 도형 전체를 복사(레이어·블록 유지). 도형을 기하학적으로 자르지는 않는다.
"""
import io
import json
import os
import pathlib
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent
KOREA_X = (100000.0, 400000.0)   # EPSG:5186 중부원점 범위 대략(동서)
KOREA_Y = (200000.0, 800000.0)   # 남북


def cache_dir():
    d = pathlib.Path(os.environ.get("NGII_CACHE") or (pathlib.Path(os.environ.get("LOCALAPPDATA", str(pathlib.Path.home()))) / "law-checker" / "ngii"))
    (d / "sheets").mkdir(parents=True, exist_ok=True)
    return d


def _index_path():
    return cache_dir() / "index.json"


def load_index():
    f = _index_path()
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"sheets": {}}


def _save_index(idx):
    _index_path().write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")


def _read_dxf(path):
    import ezdxf
    try:
        return ezdxf.readfile(str(path))
    except Exception:
        from ezdxf import recover
        doc, _ = recover.readfile(str(path))
        return doc


def sheet_bbox(doc):
    """모델 공간 전체의 (minx, miny, maxx, maxy). 도형이 없으면 None."""
    from ezdxf import bbox as eb
    ex = eb.extents(doc.modelspace(), fast=True)
    if not ex.has_data:
        return None
    return (ex.extmin.x, ex.extmin.y, ex.extmax.x, ex.extmax.y)


def import_file(name, data):
    """업로드된 zip/dxf 바이트를 저장·색인. 반환 {"status","sheets":[{name,bbox,plausible}],"errors":[...]}"""
    out = {"status": "OK", "sheets": [], "errors": []}
    members = []
    if name.lower().endswith(".zip"):
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile:
            return {"status": "ERROR", "sheets": [], "errors": ["zip 파일을 열 수 없습니다(손상 또는 다른 형식)"]}
        for n in z.namelist():
            if n.lower().endswith(".dxf"):
                members.append((pathlib.PurePosixPath(n).name, z.read(n)))
    elif name.lower().endswith(".dxf"):
        members.append((pathlib.PurePath(name).name, data))
    else:
        return {"status": "ERROR", "sheets": [], "errors": ["지원하는 형식은 .zip 또는 .dxf 입니다"]}
    if not members:
        return {"status": "ERROR", "sheets": [], "errors": ["압축 파일 안에서 .dxf 를 찾지 못했습니다(DXF 형식으로 받았는지 확인)"]}
    idx = load_index()
    for mname, mdata in members:
        path = cache_dir() / "sheets" / mname
        path.write_bytes(mdata)
        try:
            bb = sheet_bbox(_read_dxf(path))
        except Exception as e:
            out["errors"].append(f"{mname}: 읽기 실패({type(e).__name__})")
            path.unlink(missing_ok=True)
            continue
        if not bb:
            out["errors"].append(f"{mname}: 도형이 없습니다")
            path.unlink(missing_ok=True)
            continue
        plaus = KOREA_X[0] <= bb[0] and bb[2] <= KOREA_X[1] and KOREA_Y[0] <= bb[1] and bb[3] <= KOREA_Y[1]
        idx["sheets"][mname] = {"file": f"sheets/{mname}", "bbox": list(bb), "plausible_epsg5186": plaus}
        out["sheets"].append({"name": mname, "bbox": list(bb), "plausible": plaus})
    _save_index(idx)
    if not out["sheets"]:
        out["status"] = "ERROR"
    return out


def find_sheets(window):
    """창(minx,miny,maxx,maxy)과 겹치는 저장 도엽 목록 (좌표가 5186 범위로 보이는 것만)."""
    hits = []
    for name, s in load_index()["sheets"].items():
        b = s["bbox"]
        if not s.get("plausible_epsg5186"):
            continue
        if b[0] <= window[2] and window[0] <= b[2] and b[1] <= window[3] and window[1] <= b[3]:
            if (cache_dir() / s["file"]).exists():
                hits.append(name)
    return hits


_POINT_TYPES = ("INSERT", "TEXT", "MTEXT", "POINT", "CIRCLE", "ARC", "ELLIPSE")


def _pos(e):
    t = e.dxftype()
    try:
        if t in ("INSERT", "TEXT", "POINT"):
            p = e.dxf.insert if t != "POINT" else e.dxf.location
        else:
            p = e.dxf.center if t in ("CIRCLE", "ARC") else (e.dxf.insert if t == "MTEXT" else e.dxf.center)
        return p.x, p.y
    except Exception:
        return None


def _inside(pt, w):
    return pt is not None and w[0] <= pt[0] <= w[2] and w[1] <= pt[1] <= w[3]


def clip_pieces(points, closed, window):
    """선(또는 닫힌 외곽)을 창으로 잘라 조각 목록([(x,y),...])을 돌려준다. 창 안에 완전히 들어오면 None(원본 유지)."""
    from shapely.geometry import LineString, box
    pts = [(p[0], p[1]) for p in points]
    if len(pts) < 2:
        return None
    if all(window[0] <= x <= window[2] and window[1] <= y <= window[3] for x, y in pts):
        return None
    ring = pts + [pts[0]] if closed and pts[0] != pts[-1] else pts
    g = LineString(ring).intersection(box(*window))
    if g.is_empty:
        return []
    geoms = list(getattr(g, "geoms", [g]))
    out = []
    for q in geoms:
        if q.geom_type == "LineString" and len(q.coords) >= 2:
            out.append([(c[0], c[1]) for c in q.coords])
        elif q.geom_type == "MultiLineString":
            out += [[(c[0], c[1]) for c in l.coords] for l in q.geoms]
    return out


def clip_to_dxf(sheet_names, window, origin_xy=(0.0, 0.0), note=None, include_symbols=False, include_text=True, stats=None):
    """저장 도엽에서 창과 겹치는 도형을 새 DXF 로 복사하고 origin_xy 를 빼서 이동. 반환 (bytes, 복사한 도형 수).
    include_symbols=False: 점 기호(INSERT 블록·POINT — 논·학교·수목 표시 등 아이콘)를 빼고 선·면 도형만 담는다.
    include_text=False: 문자(표고·지명·건물명 주기)를 뺀다. stats 딕셔너리를 주면 {"symbols_skipped","text_skipped"} 를 채운다."""
    stats = stats if stats is not None else {}
    stats.update({"symbols_skipped": 0, "text_skipped": 0})
    import ezdxf
    from ezdxf import bbox as eb
    from ezdxf.addons.importer import Importer
    tgt = ezdxf.new("R2010", setup=True)
    tgt.units = 6
    tgt.header["$INSUNITS"] = 6
    msp_t = tgt.modelspace()
    n = 0
    for name in sheet_names:
        src = _read_dxf(cache_dir() / load_index()["sheets"][name]["file"])
        picked = []
        for e in src.modelspace():
            t = e.dxftype()
            if t in _POINT_TYPES:               # 기호·문자는 기준점이 창 안에 있을 때만
                if not _inside(_pos(e), window):
                    continue
                if t in ("INSERT", "POINT") and not include_symbols:
                    stats["symbols_skipped"] += 1
                    continue
                if t in ("TEXT", "MTEXT") and not include_text:
                    stats["text_skipped"] += 1
                    continue
                picked.append(e)
                continue
            if t in ("LWPOLYLINE", "LINE", "POLYLINE"):   # 선은 창 경계에서 잘라 필요한 부분만
                try:
                    if t == "LWPOLYLINE":
                        pts, closed = [(p[0], p[1]) for p in e.get_points("xy")], bool(e.closed)
                    elif t == "LINE":
                        pts, closed = [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)], False
                    else:
                        pts, closed = [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices], bool(e.is_closed)
                    pieces = clip_pieces(pts, closed, window)
                except Exception:
                    continue
                if pieces is None:
                    picked.append(e)            # 창 안에 완전히 들어옴 → 원본 그대로
                else:
                    lay = e.dxf.layer
                    if lay not in tgt.layers:
                        try:
                            tgt.layers.add(lay, color=src.layers.get(lay).dxf.color)
                        except Exception:
                            tgt.layers.add(lay)
                    attrs = {"layer": lay}
                    for k in ("color", "lineweight"):
                        if e.dxf.hasattr(k):
                            attrs[k] = e.dxf.get(k)
                    for pc in pieces:
                        msp_t.add_lwpolyline(pc, format="xy", dxfattribs=attrs)
                        n += 1
                continue
            try:                                # 그 밖의 도형은 경계 상자가 창과 겹칠 때 복사
                ex = eb.extents([e], fast=True)
            except Exception:
                continue
            if ex.has_data and ex.extmin.x <= window[2] and window[0] <= ex.extmax.x and ex.extmin.y <= window[3] and window[1] <= ex.extmax.y:
                picked.append(e)
        if picked:
            imp = Importer(src, tgt)
            imp.import_entities(picked, msp_t)
            imp.finalize()
            n += len(picked)
    if origin_xy != (0.0, 0.0):
        for e in msp_t:
            try:
                e.translate(-origin_xy[0], -origin_xy[1], 0)
            except Exception:
                pass
    if note:
        if "정보" not in tgt.layers:
            tgt.layers.add("정보", color=8)
        t = msp_t.add_text(note[2], dxfattribs={"layer": "정보", "height": 3.0})
        from ezdxf.enums import TextEntityAlignment
        t.set_placement((note[0], note[1]), align=TextEntityAlignment.LEFT)
    s = io.StringIO()
    tgt.write(s)
    return s.getvalue().encode("utf-8"), n


def export_ngii(x, y, polygon=None, margin_m=200, epsg="EPSG:5186", origin="parcel", include_symbols=False, include_text=True):
    """주소 좌표(경위도)로 저장 도엽에서 CAD 생성. 반환 {"status": "OK"|"NO_SHEET"|"EMPTY"|"ERROR", "dxf", "sheets", "count", "origin", "error"}."""
    out = {"status": "ERROR", "dxf": None, "sheets": [], "count": 0, "origin": {"mode": origin, "x": 0.0, "y": 0.0}, "stats": {}, "error": None}
    try:
        from site_cad import _tx, margin_deg
        lons = [p[0] for p in polygon] if polygon else [x]
        lats = [p[1] for p in polygon] if polygon else [y]
        tr = _tx(epsg)
        pts = [tr.transform(lo, la) for lo, la in zip(lons, lats)]
        minx, maxx = min(p[0] for p in pts) - margin_m, max(p[0] for p in pts) + margin_m
        miny, maxy = min(p[1] for p in pts) - margin_m, max(p[1] for p in pts) + margin_m
        window = (minx, miny, maxx, maxy)
        sheets = find_sheets(window)
        if not sheets:
            out["status"] = "NO_SHEET"
            return out
        off, note = (0.0, 0.0), None
        if origin == "parcel":
            off = ((min(p[0] for p in pts) + max(p[0] for p in pts)) / 2, (min(p[1] for p in pts) + max(p[1] for p in pts)) / 2)
            out["origin"].update({"x": off[0], "y": off[1]})
            note = (-margin_m, -(margin_m + 15), f"ORIGIN(0,0,0) = target parcel center / {epsg} X={off[0]:.3f} Y={off[1]:.3f} / unit m. Add X,Y to restore absolute coordinates.")
        st = {}
        data, n = clip_to_dxf(sheets, window, off, note, include_symbols, include_text, st)
        out.update({"sheets": sheets, "count": n, "dxf": data, "stats": st, "status": "OK" if n else "EMPTY"})
    except Exception as e:
        out["error"] = f"수치지도 CAD 생성 실패({type(e).__name__})"
    return out
