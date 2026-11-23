"""주소 → 지적도·수치지도 DXF (VWorld 벡터 레이어 → 중부원점 TM 좌표 → ezdxf).

- 좌표계: 기본 EPSG:5186 (Korea 2000 / 중부원점, 단위 m). 현상설계 CAD 도면과 겹칠 때 좌표계가 같은지 확인할 것.
- 지적도 DXF: 필지 경계(폐합 폴리선)·지번 문자, 대상 필지(빨강)
- 수치지도 DXF: 건물 외곽(층수 문자), 도로(도로명 선), 용도지역 경계(이름 문자)
- 키는 서버에서만 쓰고 파일에는 넣지 않는다. 경계·건물은 브이월드 참고 자료이며 측량 성과가 아니다.
"""
import io
import math

from vworld_client import DATA_URL, LAYER_PARCEL, LAYER_ZONE, _config, _snippet

LAYER_BUILDING = "LT_C_BLDGINFO"   # 건물 통합정보(외곽·층수)
LAYER_ROAD = "LT_L_SPRD"           # 도로명 도로 구간(선)
LAYER_ROAD_LINK = "LT_L_MOCTLINK"  # 국가표준 도로 링크(선)
EPSG = "EPSG:5186"
PAGE = 1000
MAX_PAGES = 6


def margin_deg(lat, meters):
    return meters / 111320.0, meters / (111320.0 * math.cos(math.radians(lat)))


def fetch_layer(layer, bbox, key, domain, getter):
    """bbox=(minlon,minlat,maxlon,maxlat) 안의 feature 전체(페이지 순회). 반환 (features, total, truncated)."""
    feats, total = [], None
    for page in range(1, MAX_PAGES + 1):
        params = {"service": "data", "request": "GetFeature", "data": layer, "key": key, "domain": domain,
                  "geomFilter": "BOX({},{},{},{})".format(*bbox), "geometry": "true", "attribute": "true",
                  "format": "json", "size": str(PAGE), "page": str(page), "crs": "EPSG:4326"}
        resp = getter(DATA_URL, params=params, timeout=40).json()["response"]
        st = resp.get("status")
        if st == "NOT_FOUND":
            break
        if st != "OK":
            raise ValueError(f"{layer} 조회 오류 {(resp.get('error') or {}).get('code', st)}")
        got = resp["result"]["featureCollection"]["features"]
        feats += got
        total = int((resp.get("record") or {}).get("total") or len(feats))
        if len(feats) >= total or not got:
            break
    return feats, total or 0, bool(total and len(feats) < total)


def _rings(geom):
    """GeoJSON geometry → [(ring, is_closed_polygon)] (경위도)."""
    t, c = geom.get("type"), geom.get("coordinates") or []
    out = []
    if t == "Polygon":
        out = [(r, True) for r in c]
    elif t == "MultiPolygon":
        out = [(r, True) for poly in c for r in poly]
    elif t == "LineString":
        out = [(c, False)]
    elif t == "MultiLineString":
        out = [(l, False) for l in c]
    return [([(float(p[0]), float(p[1])) for p in r], closed) for r, closed in out if len(r) >= 2]


def clip_geometry(geom, bbox):
    """geometry 를 bbox(경위도) 안으로 자른다. 크기가 구역 전체인 용도지역·긴 도로선이 CAD 범위를 늘리지 않게 한다. 실패하면 원본."""
    try:
        from shapely.geometry import box, mapping, shape
        g = shape(geom).intersection(box(*bbox))
        if g.is_empty:
            return {"type": "GeometryCollection", "coordinates": []}
        m = mapping(g)
        if m["type"] == "GeometryCollection":
            parts = [mapping(x) for x in getattr(g, "geoms", []) if x.geom_type in ("Polygon", "LineString")]
            polys = [q["coordinates"] for q in parts if q["type"] == "Polygon"]
            lines = [q["coordinates"] for q in parts if q["type"] == "LineString"]
            return {"type": "MultiPolygon", "coordinates": polys} if polys else {"type": "MultiLineString", "coordinates": lines}
        return m
    except Exception:
        return geom


def _clip_all(feats, bbox):
    return [{**f, "geometry": clip_geometry(f.get("geometry") or {}, bbox)} for f in feats]


def _centroid(ring):
    n = len(ring)
    return sum(p[0] for p in ring) / n, sum(p[1] for p in ring) / n


def _new_doc(layers):
    import ezdxf
    doc = ezdxf.new("R2010", setup=True)
    doc.units = 6  # 미터
    doc.header["$INSUNITS"] = 6
    doc.styles.add("KOR", font="malgun.ttf")
    for name, color in layers.items():
        doc.layers.add(name, color=color)
    return doc


def _dump(doc):
    s = io.StringIO()
    doc.write(s)
    return s.getvalue().encode("utf-8")


def _tx(epsg):
    from pyproj import Transformer
    return Transformer.from_crs("EPSG:4326", epsg, always_xy=True)


def _add_poly(msp, tr, ring, closed, layer, color=None, width=None):
    pts = [tr.transform(lon, lat) for lon, lat in ring]
    if closed and pts[0] != pts[-1]:
        pass
    attribs = {"layer": layer}
    if color:
        attribs["color"] = color
    if width:
        attribs["const_width"] = width
    msp.add_lwpolyline(pts, format="xy", close=closed, dxfattribs=attribs)


def _add_text(msp, tr, lon, lat, text, layer, height, color=None):
    if not text:
        return
    x, y = tr.transform(lon, lat)
    a = {"layer": layer, "height": height, "style": "KOR"}
    if color:
        a["color"] = color
    t = msp.add_text(str(text), dxfattribs=a)
    t.set_placement((x, y), align=ezdxf_align())


def ezdxf_align():
    from ezdxf.enums import TextEntityAlignment
    return TextEntityAlignment.MIDDLE_CENTER


def build_cadastral_dxf(parcels, target_pnu, epsg=EPSG):
    doc = _new_doc({"지적_필지경계": 2, "지적_지번": 7, "대상필지": 1, "대상필지_지번": 1})
    msp, tr = doc.modelspace(), _tx(epsg)
    n = 0
    for f in parcels:
        pr = f.get("properties") or {}
        is_t = pr.get("pnu") == target_pnu
        for ring, closed in _rings(f.get("geometry") or {}):
            _add_poly(msp, tr, ring, closed, "대상필지" if is_t else "지적_필지경계", color=1 if is_t else None, width=0.3 if is_t else None)
        rings = _rings(f.get("geometry") or {})
        if rings:
            lon, lat = _centroid(max(rings, key=lambda r: len(r[0]))[0])
            _add_text(msp, tr, lon, lat, pr.get("jibun"), "대상필지_지번" if is_t else "지적_지번", 2.5 if is_t else 1.8, color=1 if is_t else None)
        n += 1
    return _dump(doc), n


def build_digital_dxf(buildings, roads, zones, epsg=EPSG):
    doc = _new_doc({"건물": 5, "건물_층수": 7, "도로": 3, "용도지역": 6, "용도지역_이름": 6})
    msp, tr = doc.modelspace(), _tx(epsg)
    counts = {"건물": 0, "도로": 0, "용도지역": 0}
    for f in buildings:
        pr = f.get("properties") or {}
        rings = _rings(f.get("geometry") or {})
        for ring, closed in rings:
            _add_poly(msp, tr, ring, True, "건물")
        if rings:
            fl = pr.get("grnd_flr") or pr.get("gro_flo_co")
            label = (f"{fl}F" if fl else "")
            lon, lat = _centroid(max(rings, key=lambda r: len(r[0]))[0])
            _add_text(msp, tr, lon, lat, label, "건물_층수", 1.5)
            counts["건물"] += 1
    for f in roads:
        for ring, closed in _rings(f.get("geometry") or {}):
            _add_poly(msp, tr, ring, False, "도로")
        counts["도로"] += 1
    for f in zones:
        pr = f.get("properties") or {}
        rings = _rings(f.get("geometry") or {})
        for ring, closed in rings:
            _add_poly(msp, tr, ring, True, "용도지역")
        if rings:
            lon, lat = _centroid(max(rings, key=lambda r: len(r[0]))[0])
            _add_text(msp, tr, lon, lat, pr.get("uname"), "용도지역_이름", 4.0)
            counts["용도지역"] += 1
    return _dump(doc), counts


def export_cad(x, y, pnu, polygon=None, key=None, domain=None, getter=None, margin_m=200, epsg=EPSG):
    """반환 {"status","cadastral":bytes,"digital":bytes,"epsg","counts","notes":[...],"error"}."""
    key, domain = _config(key, domain)
    out = {"status": "ERROR", "cadastral": None, "digital": None, "epsg": epsg, "counts": {}, "notes": [], "error": None}
    if not key:
        out["error"] = "VWORLD_API_KEY 미설정(CAD 내보내기는 중계 미지원)"
        return out
    if getter is None:
        import requests
        getter = requests.get
    try:
        lons = [p[0] for p in polygon] if polygon else [x]
        lats = [p[1] for p in polygon] if polygon else [y]
        dlat, dlon = margin_deg(sum(lats) / len(lats), margin_m)
        bbox = (min(lons) - dlon, min(lats) - dlat, max(lons) + dlon, max(lats) + dlat)
        data = {}
        for k, layer in (("parcels", LAYER_PARCEL), ("buildings", LAYER_BUILDING), ("roads", LAYER_ROAD), ("zones", LAYER_ZONE)):
            try:
                feats, total, trunc = fetch_layer(layer, bbox, key, domain, getter)
                data[k] = feats
                if trunc:
                    out["notes"].append(f"{layer}: 전체 {total}개 중 {len(feats)}개만 받음(범위가 넓어 일부 누락)")
            except Exception as e:
                data[k] = []
                if k == "parcels":
                    raise
                out["notes"].append(f"{layer} 조회 실패 — 해당 레이어 제외({_snippet(str(e), 60)})")
        out["cadastral"], np_ = build_cadastral_dxf(data["parcels"], pnu, epsg)
        out["digital"], cnt = build_digital_dxf(data["buildings"], _clip_all(data["roads"], bbox), _clip_all(data["zones"], bbox), epsg)
        out["counts"] = {"필지": np_, **cnt}
        out["status"] = "OK"
    except Exception as e:
        out["error"] = _snippet(str(e), 140) if isinstance(e, ValueError) else f"CAD 생성 실패({type(e).__name__})"
    return out
