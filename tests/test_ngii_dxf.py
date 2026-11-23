import io
import os
import pathlib
import tempfile
import unittest
import zipfile

import ezdxf

import ngii_dxf as nd

REPO = pathlib.Path(__file__).resolve().parent.parent


def make_dxf(lines, texts=(), layer="F0010000"):
    doc = ezdxf.new("R2010")
    doc.layers.add(layer, color=3)
    msp = doc.modelspace()
    for (a, b) in lines:
        msp.add_line(a, b, dxfattribs={"layer": layer})
    for (p, t) in texts:
        msp.add_text(t, dxfattribs={"layer": layer, "height": 2}).set_placement(p)
    s = io.StringIO(); doc.write(s)
    return s.getvalue().encode("utf-8")


# 엄사초 부근(5186 약 221,343 / 409,848) 도엽 가정: 동서 3km × 남북 2km
SHEET = make_dxf([((221300, 409800), (221400, 409800)),      # 창 안
                  ((221300, 409800), (221300, 409900)),      # 창 안
                  ((223000, 411000), (223100, 411000))],     # 창 밖
                 texts=[((221343, 409848), "엄사초")])


class NgiiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["NGII_CACHE"] = self.tmp.name

    def tearDown(self):
        os.environ.pop("NGII_CACHE", None)
        self.tmp.cleanup()

    def big_sheet(self):
        return make_dxf([((220500, 409000), (223500, 409000)), ((220500, 411000), (223500, 411000)),
                         ((221300, 409800), (221400, 409800)), ((221300, 409800), (221300, 409900)),
                         ((223000, 410900), (223100, 410900))], texts=[((221343, 409848), "엄사초")])

    def test_cache_is_outside_repo_by_default_and_ignored(self):
        os.environ.pop("NGII_CACHE", None)
        d = nd.cache_dir().resolve()
        self.assertNotIn(REPO.resolve(), [d, *d.parents])
        ig = (REPO / ".gitignore").read_text(encoding="utf-8")
        for pat in ("ngii/", "ngii_cache/", "*.dxf"):
            self.assertIn(pat, ig)

    def test_import_dxf_and_zip_and_bad_inputs(self):
        r = nd.import_file("공주090.dxf", self.big_sheet())
        self.assertEqual(r["status"], "OK")
        self.assertTrue(r["sheets"][0]["plausible"])
        b = r["sheets"][0]["bbox"]
        self.assertAlmostEqual(b[0], 220500, delta=1); self.assertAlmostEqual(b[3], 411000, delta=3)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("a/b/공주091.dxf", self.big_sheet())
            z.writestr("readme.txt", "x")
        self.assertEqual(nd.import_file("x.zip", buf.getvalue())["sheets"][0]["name"], "공주091.dxf")
        self.assertEqual(nd.import_file("x.zip", b"notzip")["status"], "ERROR")
        self.assertEqual(nd.import_file("x.shp", b"1")["status"], "ERROR")
        empty = io.BytesIO()
        with zipfile.ZipFile(empty, "w") as z:
            z.writestr("a.shp", "1")
        self.assertIn("DXF", nd.import_file("e.zip", empty.getvalue())["errors"][0])

    def test_implausible_coordinates_are_not_used(self):
        wrong = make_dxf([((127.2, 36.2), (127.3, 36.2))])   # 경위도 값
        r = nd.import_file("wrong.dxf", wrong)
        self.assertFalse(r["sheets"][0]["plausible"])
        self.assertEqual(nd.find_sheets((0, 0, 1000000, 1000000)), [])

    def test_find_and_clip_with_origin_shift(self):
        nd.import_file("공주090.dxf", self.big_sheet())
        window = (221143, 409648, 221543, 410048)
        self.assertEqual(nd.find_sheets(window), ["공주090.dxf"])
        self.assertEqual(nd.find_sheets((900000, 900000, 900100, 900100)), [])
        data, n = nd.clip_to_dxf(["공주090.dxf"], window, (221343.0, 409848.0), (-200, -215, "ORIGIN test"))
        self.assertEqual(n, 3)   # 창 안 선 2 + 문자 1 (창 밖 선·긴 선 제외 — 긴 선은 창과 겹쳐 포함될 수 있음)

    def test_export_ngii_layers_and_origin(self):
        nd.import_file("공주090.dxf", self.big_sheet())
        from site_cad import _tx
        lon, lat = 127.2370, 36.2865
        r = nd.export_ngii(lon, lat, polygon=None, margin_m=300)
        # 위경도(127.237,36.2865)는 5186 약 (221,43x, 409,8xx) — 도엽 안
        self.assertEqual(r["status"], "OK")
        doc = ezdxf.read(io.StringIO(r["dxf"].decode("utf-8")))
        layers = {e.dxf.layer for e in doc.modelspace()}
        self.assertIn("F0010000", layers)
        self.assertIn("정보", layers)
        xs = [p for e in doc.modelspace() if e.dxftype() == "LINE" for p in (e.dxf.start.x, e.dxf.end.x)]
        self.assertTrue(all(abs(v) < 5000 for v in xs))   # 원점 이동됨(절대 22만대가 아님)
        ab = nd.export_ngii(lon, lat, margin_m=300, origin="absolute")
        d2 = ezdxf.read(io.StringIO(ab["dxf"].decode("utf-8")))
        self.assertTrue(any(e.dxf.start.x > 200000 for e in d2.modelspace() if e.dxftype() == "LINE"))
        self.assertEqual([e for e in d2.modelspace() if e.dxf.layer == "정보"], [])

    def test_no_sheet_is_reported(self):
        self.assertEqual(nd.export_ngii(127.2370, 36.2865)["status"], "NO_SHEET")


class ClipTests(unittest.TestCase):
    W = (0, 0, 100, 100)

    def test_pieces(self):
        self.assertIsNone(nd.clip_pieces([(10, 10), (50, 50)], False, self.W))           # 완전히 안 → 원본
        self.assertEqual(nd.clip_pieces([(200, 200), (300, 300)], False, self.W), [])     # 완전히 밖
        p = nd.clip_pieces([(-100, 50), (300, 50)], False, self.W)                        # 긴 선 → 창 경계에서 잘림
        self.assertEqual(len(p), 1)
        xs = [q[0] for q in p[0]]
        self.assertEqual((min(xs), max(xs)), (0, 100))
        ring = nd.clip_pieces([(50, 50), (150, 50), (150, 150), (50, 150)], True, self.W)  # 걸친 닫힌 외곽 → 열린 조각
        self.assertTrue(ring and all(max(q[0] for q in piece) <= 100 and max(q[1] for q in piece) <= 100 for piece in ring))

    def test_long_lines_do_not_extend_output(self):
        tmp = tempfile.TemporaryDirectory(); os.environ["NGII_CACHE"] = tmp.name
        try:
            nd.import_file("a.dxf", make_dxf([((220000, 409848), (224000, 409848)), ((221343, 408500), (221343, 412000)),
                                               ((221300, 409800), (221400, 409800))], texts=[((221343, 409848), "안"), ((223500, 410500), "밖")]))
            window = (221143, 409648, 221543, 410048)
            data, n = nd.clip_to_dxf(["a.dxf"], window, (221343.0, 409848.0))
            doc = ezdxf.read(io.StringIO(data.decode("utf-8")))
            from ezdxf import bbox as eb
            ex = eb.extents(doc.modelspace())
            self.assertLessEqual(ex.extmax.x, 200.5); self.assertGreaterEqual(ex.extmin.x, -200.5)   # 창 반폭 200m
            self.assertLessEqual(ex.extmax.y, 200.5); self.assertGreaterEqual(ex.extmin.y, -200.5)
            texts = [e.dxf.text for e in doc.modelspace() if e.dxftype() == "TEXT"]
            self.assertEqual(texts, ["안"])
        finally:
            os.environ.pop("NGII_CACHE", None); tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
