"""주소 → 수치지도·지적도 이미지 (VWorld WMTS/WMS). 키는 서버에서만 사용하고 이미지(PNG)만 화면에 넘긴다.

- 수치지도: VWorld 'Base'(일반 지도) 타일을 이어붙인 이미지
- 지적도: 같은 지도 위에 VWorld 연속지적도(WMS lp_pa_cbnd_bubun) 를 겹치고, 대상 필지 외곽선을 빨간색으로 강조
네트워크 실패는 예외 대신 {"status":"ERROR","error":...} 로 돌려준다(키는 메시지에 넣지 않는다).
"""
import io
import math

from vworld_client import DATA_URL, LAYER_PARCEL, _config, _snippet

WMTS = "https://api.vworld.kr/req/wmts/1.0.0/{key}/{layer}/{z}/{y}/{x}.{ext}"
WMS = "https://api.vworld.kr/req/wms"
TILE = 256
SIZE = 768          # 출력 한 변(px)
MAX_ZOOM, MIN_ZOOM = 19, 14
ORIGIN = 20037508.342789244  # EPSG:3857 반폭(m)


def lonlat_to_world_px(lon, lat, z):
    n = TILE * 2 ** z
    x = (lon + 180.0) / 360.0 * n
    s = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n
    return x, y


def pick_zoom(polygon, size=SIZE, fill=0.55):
    """필지가 화면의 fill 비율 안에 들어오는 가장 큰 줌. polygon 이 없으면 18."""
    if not polygon:
        return 18
    lons = [p[0] for p in polygon]; lats = [p[1] for p in polygon]
    for z in range(MAX_ZOOM, MIN_ZOOM - 1, -1):
        x0, y0 = lonlat_to_world_px(min(lons), max(lats), z)
        x1, y1 = lonlat_to_world_px(max(lons), min(lats), z)
        if max(x1 - x0, y1 - y0) <= size * fill:
            return z
    return MIN_ZOOM


def window(center_lon, center_lat, z, size=SIZE):
    cx, cy = lonlat_to_world_px(center_lon, center_lat, z)
    return cx - size / 2, cy - size / 2   # 창의 왼쪽 위 월드 픽셀


def mercator_bbox(left, top, z, size=SIZE):
    res = 2 * ORIGIN / (TILE * 2 ** z)
    minx = left * res - ORIGIN
    maxx = (left + size) * res - ORIGIN
    maxy = ORIGIN - top * res
    miny = ORIGIN - (top + size) * res
    return minx, miny, maxx, maxy


def parcel_polygon(x, y, key=None, domain=None, getter=None):
    """좌표가 속한 필지의 외곽선(경도·위도 목록, 가장 큰 고리). 실패하면 None."""
    key, domain = _config(key, domain)
    if getter is None:
        import requests
        getter = requests.get
    params = {"service": "data", "request": "GetFeature", "data": LAYER_PARCEL, "key": key, "domain": domain,
              "geomFilter": f"POINT({x} {y})", "geometry": "true", "attribute": "false", "format": "json", "size": "1"}
    try:
        resp = getter(DATA_URL, params=params, timeout=25).json()["response"]
        if resp.get("status") != "OK":
            return None
        geom = resp["result"]["featureCollection"]["features"][0]["geometry"]
        rings = []
        if geom["type"] == "Polygon":
            rings = [geom["coordinates"][0]]
        elif geom["type"] == "MultiPolygon":
            rings = [poly[0] for poly in geom["coordinates"]]
        rings = [[(float(a), float(b)) for a, b in r] for r in rings if r]
        return max(rings, key=len) if rings else None
    except Exception:
        return None


def _fetch(getter, url, params, what):
    r = getter(url, params=params, timeout=30)
    ct = (getattr(r, "headers", {}) or {}).get("content-type", "")
    if getattr(r, "status_code", 200) != 200 or "image" not in ct:
        raise ValueError(f"{what} 응답 오류 HTTP {getattr(r, 'status_code', '?')} '{_snippet(getattr(r, 'text', ''), 60)}'")
    return r.content


def base_image(left, top, z, key, domain, getter, layer="Base", size=SIZE):
    from PIL import Image
    ext = "jpeg" if layer == "Satellite" else "png"
    x0, y0 = int(left // TILE), int(top // TILE)
    x1, y1 = int((left + size - 1) // TILE), int((top + size - 1) // TILE)
    canvas = Image.new("RGB", ((x1 - x0 + 1) * TILE, (y1 - y0 + 1) * TILE), (235, 235, 235))
    for ty in range(y0, y1 + 1):
        for tx in range(x0, x1 + 1):
            data = _fetch(getter, WMTS.format(key=key, layer=layer, z=z, y=ty, x=tx, ext=ext), {"domain": domain}, "지도 타일")
            canvas.paste(Image.open(io.BytesIO(data)).convert("RGB"), ((tx - x0) * TILE, (ty - y0) * TILE))
    ox, oy = int(left - x0 * TILE), int(top - y0 * TILE)
    return canvas.crop((ox, oy, ox + size, oy + size))


def cadastral_overlay(left, top, z, key, domain, getter, size=SIZE):
    from PIL import Image
    minx, miny, maxx, maxy = mercator_bbox(left, top, z, size)
    params = {"SERVICE": "WMS", "REQUEST": "GetMap", "VERSION": "1.3.0", "LAYERS": "lp_pa_cbnd_bubun", "STYLES": "lp_pa_cbnd_bubun",
              "CRS": "EPSG:3857", "BBOX": f"{minx},{miny},{maxx},{maxy}", "WIDTH": size, "HEIGHT": size, "FORMAT": "image/png",
              "TRANSPARENT": "TRUE", "KEY": key, "DOMAIN": domain}
    return Image.open(io.BytesIO(_fetch(getter, WMS, params, "지적도"))).convert("RGBA")


def _png(img):
    b = io.BytesIO(); img.save(b, "PNG"); return b.getvalue()


def render_maps(x, y, key=None, domain=None, getter=None, polygon="auto"):
    """반환: {"status","digital":PNG,"cadastral":PNG,"zoom","error"} — digital=수치지도, cadastral=지적도(필지 강조)."""
    key, domain = _config(key, domain)
    out = {"status": "ERROR", "digital": None, "cadastral": None, "zoom": None, "error": None}
    if not key:
        out["error"] = "VWORLD_API_KEY 미설정(지도는 중계 미지원)"
        return out
    if getter is None:
        import requests
        getter = requests.get
    try:
        from PIL import ImageDraw
        poly = parcel_polygon(x, y, key, domain, getter) if polygon == "auto" else polygon
        z = pick_zoom(poly)
        if poly:
            clon = (min(p[0] for p in poly) + max(p[0] for p in poly)) / 2
            clat = (min(p[1] for p in poly) + max(p[1] for p in poly)) / 2
        else:
            clon, clat = x, y
        left, top = window(clon, clat, z)
        base = base_image(left, top, z, key, domain, getter)
        out["digital"] = _png(base)
        cad = base.convert("RGBA")
        try:
            cad.alpha_composite(cadastral_overlay(left, top, z, key, domain, getter))
        except Exception as e:  # 지적 오버레이 실패 시에도 수치지도는 유지
            out["error"] = f"지적도 겹치기 실패: {_snippet(str(e), 100)}"
        if poly:
            pts = []
            for lon, lat in poly:
                wx, wy = lonlat_to_world_px(lon, lat, z)
                pts.append((wx - left, wy - top))
            d = ImageDraw.Draw(cad)
            d.line(pts + [pts[0]], fill=(230, 30, 30, 255), width=4)
        out["cadastral"] = _png(cad.convert("RGB"))
        out["zoom"] = z
        out["status"] = "OK" if not out["error"] else "PARTIAL"
    except Exception as e:
        out["error"] = _snippet(str(e), 140) if isinstance(e, ValueError) else f"지도 생성 실패({type(e).__name__})"
    return out
