"""도 소재 시·군 조례 데이터(data/local_zone_limits.json, data/local_parking.json) 검증. 파일이 없으면 건너뛴다."""
import json
import pathlib
import unittest

from ordinance_parking_parse import parse_parking_annex
from ordinance_parse import CANON_ZONES, parse_article, parse_hwp_table, zone_table
from ordinance_regions import region_of

ROOT = pathlib.Path(__file__).resolve().parent.parent
ZONE_FILE = ROOT / "data" / "local_zone_limits.json"
PARK_FILE = ROOT / "data" / "local_parking.json"


def read(rel):
    t = (ROOT / rel).read_text(encoding="utf-8")
    return t, "\n".join(l for l in t.splitlines() if not l.startswith("#")).strip()


@unittest.skipUnless(ZONE_FILE.exists(), "local_zone_limits.json 없음")
class LocalZoneLimits(unittest.TestCase):
    DATA = json.loads(ZONE_FILE.read_text(encoding="utf-8"))["regions"] if ZONE_FILE.exists() else {}

    def test_regions_are_do_si_gun_keys(self):
        self.assertGreater(len(self.DATA), 30)
        for key in self.DATA:
            sido, _, sg = key.partition(" ")
            self.assertTrue(sg.endswith(("시", "군")), key)
            self.assertTrue(sido.endswith(("도", "특별자치도")), key)

    def test_json_matches_snapshot_reparse(self):
        for key, r in self.DATA.items():
            o = r["ordinance"]
            raw, body = read(o["snapshot"])
            self.assertNotIn("OC=", raw)
            if o["method"] == "annex-hwp":
                cov, far = parse_hwp_table(body)
                self.assertEqual(r["zones"], zone_table(cov, far, {}, {}), key)
            else:
                (cov, cn), (far, fn) = parse_article(body, "건폐율"), parse_article(body, "용적률")
                self.assertEqual(r["zones"], zone_table(cov, far, cn, fn), key)

    def test_value_sanity(self):
        for key, r in self.DATA.items():
            zz = r["zones"]
            self.assertGreaterEqual(len(zz), 8, key)
            for z, v in zz.items():
                self.assertIn(z, CANON_ZONES)
                if v["coverage"] is not None:
                    self.assertTrue(0 < v["coverage"] <= 100, (key, z))
                if v["far"] is not None:
                    self.assertTrue(0 < v["far"] <= 1500, (key, z))
                if v["coverage"] and v["far"]:
                    self.assertGreaterEqual(v["far"], v["coverage"], (key, z))
            seq = [(zz.get(z) or {}).get("far") for z in ("제1종전용주거지역", "제2종전용주거지역", "제1종일반주거지역",
                                                          "제2종일반주거지역", "제3종일반주거지역", "준주거지역")]
            vals = [x for x in seq if x is not None]
            self.assertEqual(vals, sorted(vals), (key, "주거 용적률은 종이 높을수록 같거나 커야 함", seq))

    def test_missing_lists_consistent(self):
        for key, r in self.DATA.items():
            for kind in ("coverage", "far"):
                missing = {z for z in CANON_ZONES if r["zones"].get(z, {}).get(kind) is None}
                self.assertEqual(set(r["missing"][kind]), missing, (key, kind))

    def test_every_region_resolves_from_an_address(self):
        for key in self.DATA:
            self.assertEqual(region_of(key + " 가상구 1", self.DATA), key)


@unittest.skipUnless(PARK_FILE.exists(), "local_parking.json 없음")
class LocalParking(unittest.TestCase):
    DATA = json.loads(PARK_FILE.read_text(encoding="utf-8"))["regions"] if PARK_FILE.exists() else {}

    def test_json_matches_annex_snapshot_reparse(self):
        for key, r in self.DATA.items():
            raw, body = read(r["ordinance"]["annex_snapshot"])
            self.assertNotIn("OC=", raw)
            parsed = parse_parking_annex(body)
            for field in ("columns", "categories", "notes", "small_house_rule", "rounding_half_rule"):
                self.assertEqual(r[field], parsed[field], (key, field))

    def test_enough_computable_categories_and_manual_housing(self):
        for key, r in self.DATA.items():
            ok = [c for c in r["categories"] if c["kind"] in ("area", "per_unit", "detached")]
            self.assertGreaterEqual(len(ok), 5, key)
            for c in r["categories"]:
                self.assertTrue(c["raw"].strip())
                if "주택건설기준" in c["raw"]:
                    self.assertEqual(c["kind"], "manual", (key, c["id"]))
                if c["kind"] in ("area", "per_unit"):
                    for rule in c["rules"]:
                        self.assertEqual(len(rule["values"]), max(1, len(r["columns"])), (key, c["id"]))
                        for v in rule["values"]:
                            self.assertGreater(float(v["div"]), 0)

    def test_area_divisors_are_plausible(self):
        """설치기준 ㎡당 1대 값은 현실적인 범위(20~2,000㎡)여야 한다 — 파싱 오류(자릿수 등) 탐지."""
        for key, r in self.DATA.items():
            for c in r["categories"]:
                if c["kind"] == "area":
                    for rule in c["rules"]:
                        for v in rule["values"]:
                            self.assertTrue(20 <= float(v["div"]) <= 2000, (key, c["id"], v))


if __name__ == "__main__":
    unittest.main()
