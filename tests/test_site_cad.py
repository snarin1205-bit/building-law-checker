import io
import unittest
from collections import Counter

import ezdxf

import site_cad as sc


class Resp:
    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


def feats(*fs, total=None):
    return {"response": {"status": "OK", "record": {"total": str(total if total is not None else len(fs))},
                         "result": {"featureCollection": {"features": list(fs)}}}}


def poly(lon, lat, d=0.0002):
    return {"type": "MultiPolygon", "coordinates": [[[[lon, lat], [lon + d, lat], [lon + d, lat + d], [lon, lat + d], [lon, lat]]]]}


def line(lon, lat):
    return {"type": "MultiLineString", "coordinates": [[[lon, lat], [lon + 0.001, lat + 0.0005]]]}


LON, LAT = 127.2370, 36.2865
BY_LAYER = {
    sc.LAYER_PARCEL: [{"geometry": poly(LON, LAT), "properties": {"pnu": "T", "jibun": "30"}},
                      {"geometry": poly(LON + 0.0005, LAT), "properties": {"pnu": "N", "jibun": "31 대"}}],
    sc.LAYER_BUILDING: [{"geometry": poly(LON, LAT, 0.0001), "properties": {"grnd_flr": "5"}}],
    sc.LAYER_ROAD: [{"geometry": line(LON, LAT), "properties": {"rn": "번영3길"}}],
    sc.LAYER_ZONE: [{"geometry": poly(LON - 0.05, LAT - 0.05, 0.1), "properties": {"uname": "제2종일반주거지역"}}],
}


def getter(by_layer=BY_LAYER, fail=()):
    calls = []

    def g(url, params=None, timeout=None):
        calls.append(params)
        layer = params["data"]
        if layer in fail:
            return Resp({"response": {"status": "ERROR", "error": {"code": "SERVER"}}})
        fs = by_layer.get(layer, [])
        return Resp(feats(*fs) if fs else {"response": {"status": "NOT_FOUND"}})
    g.calls = calls
    return g


def read(b):
    return ezdxf.read(io.StringIO(b.decode("utf-8")))


class CadTests(unittest.TestCase):
    def test_projection_origin_of_central_belt(self):
        x, y = sc._tx(sc.EPSG).transform(127.0, 38.0)
        self.assertAlmostEqual(x, 200000, delta=0.01)
        self.assertAlmostEqual(y, 600000, delta=0.01)

    def test_export_layers_and_target_highlight(self):
        r = sc.export_cad(LON, LAT, "T", polygon=BY_LAYER[sc.LAYER_PARCEL][0]["geometry"]["coordinates"][0][0],
                          key="SECRETKEY", domain="d", getter=getter())
        self.assertEqual(r["status"], "OK")
        c = Counter(e.dxf.layer for e in read(r["cadastral"]).modelspace())
        self.assertEqual((c["대상필지"], c["지적_필지경계"], c["지적_지번"], c["대상필지_지번"]), (1, 1, 1, 1))
        d = Counter(e.dxf.layer for e in read(r["digital"]).modelspace())
        self.assertEqual((d["건물"], d["건물_층수"], d["도로"], d["용도지역"], d["용도지역_이름"]), (1, 1, 1, 1, 1))
        self.assertEqual(r["counts"], {"필지": 2, "건물": 1, "도로": 1, "용도지역": 1})
        self.assertNotIn(b"SECRETKEY", r["cadastral"] + r["digital"])
        self.assertEqual(len(read(r["digital"]).audit().errors), 0)

    def test_korean_text_and_coordinates_in_meters(self):
        r = sc.export_cad(LON, LAT, "T", key="k", domain="d", getter=getter())
        msp = read(r["cadastral"]).modelspace()
        texts = [e.dxf.text for e in msp if e.dxftype() == "TEXT"]
        self.assertIn("31 대", texts)
        xs = [p[0] for e in msp if e.dxftype() == "LWPOLYLINE" for p in e.get_points("xy")]
        self.assertTrue(all(200000 < v < 260000 for v in xs))   # 중부원점 동쪽 약 21km → 약 221,000

    def test_zone_is_clipped_to_search_box(self):
        r = sc.export_cad(LON, LAT, "T", polygon=[(LON, LAT), (LON + 0.0002, LAT), (LON + 0.0002, LAT + 0.0002)],
                          key="k", domain="d", getter=getter(), margin_m=200)
        from ezdxf import bbox
        ext = bbox.extents(read(r["digital"]).modelspace())
        self.assertLess(ext.extmax.x - ext.extmin.x, 1000)   # 0.1° 짜리 용도지역이 그대로 들어가면 8km 이상

    def test_optional_layer_failure_is_noted_but_parcels_required(self):
        r = sc.export_cad(LON, LAT, "T", key="k", domain="d", getter=getter(fail=(sc.LAYER_BUILDING,)))
        self.assertEqual(r["status"], "OK")
        self.assertTrue(any(sc.LAYER_BUILDING in n for n in r["notes"]))
        r = sc.export_cad(LON, LAT, "T", key="SECRETKEY", domain="d", getter=getter(fail=(sc.LAYER_PARCEL,)))
        self.assertEqual(r["status"], "ERROR")
        self.assertNotIn("SECRETKEY", str(r["error"]))
        self.assertIsNone(r["cadastral"])

    def test_pagination_and_truncation_note(self):
        pages = []

        def g(url, params=None, timeout=None):
            pages.append(params["page"])
            return Resp(feats({"geometry": poly(LON, LAT), "properties": {"pnu": str(len(pages)), "jibun": "1"}}, total=5000))
        fs, total, trunc = sc.fetch_layer(sc.LAYER_PARCEL, (0, 0, 1, 1), "k", "d", g)
        self.assertEqual((total, trunc), (5000, True))
        self.assertEqual(len(pages), sc.MAX_PAGES)

    def test_no_key(self):
        import os
        old = os.environ.pop("VWORLD_API_KEY", None)
        try:
            self.assertEqual(sc.export_cad(LON, LAT, "T", key="", domain="d", getter=getter())["status"], "ERROR")
        finally:
            if old is not None:
                os.environ["VWORLD_API_KEY"] = old


if __name__ == "__main__":
    unittest.main()
