import io
import unittest

from PIL import Image

import site_map as sm


class Resp:
    def __init__(self, content=b"", status=200, ctype="image/png", payload=None):
        self.content, self.status_code, self.headers, self.text, self._p = content, status, {"content-type": ctype}, "", payload

    def json(self):
        return self._p


def png(color=(10, 200, 10, 255), size=(256, 256)):
    b = io.BytesIO(); Image.new("RGBA", size, color).save(b, "PNG"); return b.getvalue()


SQUARE = [(127.2369, 36.2864), (127.2372, 36.2864), (127.2372, 36.2867), (127.2369, 36.2867), (127.2369, 36.2864)]


class MapMath(unittest.TestCase):
    def test_world_pixel_known_points(self):
        x, y = sm.lonlat_to_world_px(0, 0, 0)
        self.assertEqual((round(x), round(y)), (128, 128))
        x, _ = sm.lonlat_to_world_px(-180, 0, 3)
        self.assertEqual(x, 0)

    def test_zoom_shrinks_for_big_parcel(self):
        big = [(127.20, 36.25), (127.26, 36.25), (127.26, 36.31), (127.20, 36.31)]
        self.assertGreater(sm.pick_zoom(SQUARE), sm.pick_zoom(big))
        self.assertEqual(sm.pick_zoom(None), 18)
        self.assertLessEqual(sm.pick_zoom(SQUARE), sm.MAX_ZOOM)

    def test_mercator_bbox_is_square_and_ordered(self):
        left, top = sm.window(127.2370, 36.2865, 18)
        minx, miny, maxx, maxy = sm.mercator_bbox(left, top, 18)
        self.assertLess(minx, maxx); self.assertLess(miny, maxy)
        self.assertAlmostEqual(maxx - minx, maxy - miny, places=3)
        res = 2 * sm.ORIGIN / (256 * 2 ** 18)
        self.assertAlmostEqual(maxx - minx, sm.SIZE * res, places=3)


class RenderMaps(unittest.TestCase):
    def getter(self, wms_ok=True, tile_status=200):
        calls = []

        def g(url, params=None, timeout=None):
            calls.append(url)
            if "wmts" in url:
                return Resp(png((200, 200, 200, 255)), tile_status)
            if "req/wms" in url:
                return Resp(png((255, 165, 0, 80), (sm.SIZE, sm.SIZE)) if wms_ok else b"", 200 if wms_ok else 500, "image/png" if wms_ok else "text/html")
            raise AssertionError(url)
        g.calls = calls
        return g

    def test_ok_returns_two_pngs_and_no_key_in_error(self):
        g = self.getter()
        r = sm.render_maps(127.2370, 36.2865, key="SECRETKEY", domain="localhost:8501", getter=g, polygon=SQUARE)
        self.assertEqual(r["status"], "OK")
        for k in ("digital", "cadastral"):
            im = Image.open(io.BytesIO(r[k]))
            self.assertEqual(im.size, (sm.SIZE, sm.SIZE))
        self.assertNotEqual(r["digital"], r["cadastral"])

    def test_overlay_failure_keeps_digital_map(self):
        r = sm.render_maps(127.2370, 36.2865, key="SECRETKEY", domain="d", getter=self.getter(wms_ok=False), polygon=SQUARE)
        self.assertEqual(r["status"], "PARTIAL")
        self.assertIsNotNone(r["digital"])
        self.assertNotIn("SECRETKEY", str(r["error"]))

    def test_tile_failure_is_error_without_key(self):
        r = sm.render_maps(127.2370, 36.2865, key="SECRETKEY", domain="d", getter=self.getter(tile_status=403), polygon=SQUARE)
        self.assertEqual(r["status"], "ERROR")
        self.assertIsNone(r["digital"])
        self.assertNotIn("SECRETKEY", str(r["error"]))

    def test_no_key(self):
        import os
        old = os.environ.pop("VWORLD_API_KEY", None)
        try:
            r = sm.render_maps(1, 2, key="", domain="d", getter=self.getter(), polygon=SQUARE)
            self.assertEqual(r["status"], "ERROR")
        finally:
            if old is not None:
                os.environ["VWORLD_API_KEY"] = old

    def test_parcel_polygon_picks_largest_ring(self):
        feat = {"response": {"status": "OK", "result": {"featureCollection": {"features": [{"geometry": {
            "type": "MultiPolygon", "coordinates": [[[[1, 1], [1, 2], [2, 2], [1, 1]]], [[[0, 0], [0, 5], [5, 5], [5, 0], [0, 0]]]]}}]}}}}
        poly = sm.parcel_polygon(1, 2, key="k", domain="d", getter=lambda *a, **k: Resp(payload=feat))
        self.assertEqual(len(poly), 5)
        self.assertIsNone(sm.parcel_polygon(1, 2, key="k", domain="d", getter=lambda *a, **k: Resp(payload={"response": {"status": "NOT_FOUND"}})))


if __name__ == "__main__":
    unittest.main()
