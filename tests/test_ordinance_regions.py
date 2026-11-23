import json
import pathlib
import unittest

import law_sync
from ordinance_daejeon import DJ_ZONE_LIMITS
from ordinance_parse import CANON_ZONES, parse_article, parse_hwp_table, parse_pct, zone_table
from ordinance_regions import county_in, load, region_of, zone_limits_for

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = json.loads((ROOT / "data" / "ordinance_zone_limits.json").read_text(encoding="utf-8"))
EXPECTED_REGIONS = {"서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시", "대전광역시", "울산광역시", "세종특별자치시"}


class ParsePct(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(parse_pct("60퍼센트 이하")[0], 60)
        self.assertEqual(parse_pct("1,300퍼센트 이하")[0], 1300)
        self.assertEqual(parse_pct("1천300퍼센트 이하")[0], 1300)
        self.assertEqual(parse_pct("1천 300퍼센트 이하")[0], 1300)
        self.assertEqual(parse_pct("1천퍼센트(단, 서울도심: 800퍼센트)")[0], 1000)
        self.assertEqual(parse_pct("100분의 60 이하")[0], 60)
        self.assertEqual(parse_pct("70%")[0], 70)
        self.assertIsNone(parse_pct("해당없음")[0])

    def test_article_parser_reads_notes_and_ignores_non_standard_zones(self):
        txt = ("제45조(용도지역 안에서의 건폐율)\n① 건폐율은 다음 각 호와 같다.\n"
               "1. 제1종전용주거지역: 50퍼센트 이하\n"
               "2. 중심상업지역: 80퍼센트 이하(방화지구 안에서는 90퍼센트 이하)\n"
               "3. 엉뚱한지역: 10퍼센트 이하\n② 기타\n4. 일반상업지역: 99퍼센트\n")
        vals, notes = parse_article(txt, "건폐율")
        self.assertEqual(vals, {"제1종전용주거지역": 50, "중심상업지역": 80})
        self.assertIn("방화지구", notes["중심상업지역"])

    def test_hwp_table_parser(self):
        t = "연번\n1\n도시지역\n제1종 전용주거지역\n50\n100\n2\n제2종 전용주거지역\n50\n150\n중심상업지역\n80\n1,300\n"
        cov, far = parse_hwp_table(t)
        self.assertEqual((cov["제2종전용주거지역"], far["제2종전용주거지역"], far["중심상업지역"]), (50, 150, 1300))

    def test_missing_stays_missing(self):
        z = zone_table({"제1종전용주거지역": 50}, {})
        self.assertIsNone(z["제1종전용주거지역"]["far"])
        self.assertNotIn("준주거지역", z)


class RegionData(unittest.TestCase):
    def test_all_eight_regions_present(self):
        self.assertEqual(set(DATA["regions"]), EXPECTED_REGIONS)

    def test_json_matches_snapshot_reparse(self):
        """JSON 값은 원문 사본을 같은 파서로 다시 읽은 결과와 같아야 한다(수작업 수정 방지)."""
        for key, r in DATA["regions"].items():
            o = r["ordinance"]
            txt = (ROOT / o["snapshot"]).read_text(encoding="utf-8")
            if o["method"] == "annex-hwp":
                annex = (ROOT / o["annex_snapshot"]).read_text(encoding="utf-8")
                cov, far = parse_hwp_table(annex)
                cn, fn = {}, {}
            else:
                (cov, cn), (far, fn) = parse_article(txt, "건폐율"), parse_article(txt, "용적률")
            self.assertEqual(r["zones"], zone_table(cov, far, cn, fn), key)

    def test_value_sanity(self):
        for key, r in DATA["regions"].items():
            for z, v in r["zones"].items():
                self.assertIn(z, CANON_ZONES)
                if v["coverage"] is not None:
                    self.assertTrue(0 < v["coverage"] <= 100, (key, z))
                if v["far"] is not None:
                    self.assertTrue(0 < v["far"] <= 1500, (key, z))
                if v["coverage"] and v["far"]:
                    self.assertGreaterEqual(v["far"], v["coverage"] - 0, (key, z))  # 용적률 ≥ 건폐율

    def test_missing_lists_consistent(self):
        for key, r in DATA["regions"].items():
            for kind, field in (("coverage", "coverage"), ("far", "far")):
                missing = {z for z in CANON_ZONES if r["zones"].get(z, {}).get(field) is None}
                self.assertEqual(set(r["missing"][kind]), missing, (key, kind))

    def test_daejeon_json_equals_verified_daejeon_table(self):
        z = DATA["regions"]["대전광역시"]["zones"]
        for name in CANON_ZONES:
            self.assertEqual((z[name]["coverage"], z[name]["far"]), DJ_ZONE_LIMITS[name][:2], name)

    def test_known_spot_values_from_ordinance_text(self):
        z = DATA["regions"]
        self.assertEqual(z["서울특별시"]["zones"]["중심상업지역"]["far"], 1000)
        self.assertIn("서울도심", z["서울특별시"]["zones"]["중심상업지역"]["far_note"])
        self.assertEqual(z["부산광역시"]["zones"]["중심상업지역"]["far"], 1300)
        self.assertEqual(z["울산광역시"]["zones"]["제2종일반주거지역"]["far"], 200)
        self.assertEqual(z["세종특별자치시"]["zones"]["일반상업지역"]["far"], 1100)

    def test_snapshots_exist_and_carry_no_secrets(self):
        for key, r in DATA["regions"].items():
            for f in (r["ordinance"]["snapshot"], r["ordinance"]["annex_snapshot"]):
                if f:
                    t = (ROOT / f).read_text(encoding="utf-8")
                    self.assertNotIn("OC=", t)
                    self.assertTrue(t.startswith("# 출처"))


class RegionLookup(unittest.TestCase):
    def test_region_of(self):
        self.assertEqual(region_of("대전광역시 유성구 어은동"), "대전광역시")
        self.assertEqual(region_of("서울 강남구 테헤란로"), "서울특별시")
        self.assertEqual(region_of("광주광역시 북구 용봉동"), "광주광역시")
        self.assertEqual(region_of("광주 북구 용봉동"), "광주광역시")
        self.assertNotEqual(region_of("경기도 광주시 오포읍"), "광주광역시")  # 경기도 광주시는 광주광역시가 아님
        self.assertIsNone(region_of("경기도 존재하지않는시 어딘구"))  # 데이터에 없는 시·군
        self.assertIsNone(region_of(""))
        self.assertIsNone(region_of("경기도"))  # 시·군 토큰 없음

    def test_local_city_resolution_follows_data(self):
        """도 소재 시·군은 '도 시' 키가 데이터에 있을 때만 인식하고, 시 아래 구는 무시한다."""
        regs = {"경기도 성남시": {}, "충청남도 천안시": {}}
        self.assertEqual(region_of("경기도 성남시 분당구 정자일로 95", regs), "경기도 성남시")
        self.assertEqual(region_of("경기 성남시 수정구", regs), "경기도 성남시")  # 약칭
        self.assertEqual(region_of("충남 천안시 서북구", regs), "충청남도 천안시")
        self.assertIsNone(region_of("경기도 수원시 팔달구", regs))  # 데이터 없음
        self.assertIsNone(region_of("강원도 춘천시", regs))

    def test_county_warning(self):
        self.assertEqual(county_in("부산광역시 기장군 기장읍"), "기장군")
        self.assertIsNone(county_in("부산광역시 해운대구"))
        r = zone_limits_for("부산광역시 기장군 기장읍", ["제2종일반주거지역"])
        self.assertTrue(any("기장군" in n for n in r["notes"]))

    def test_lookup_ok_partial_unknown(self):
        r = zone_limits_for("대전광역시 서구 둔산로 100", ["중심상업지역"])
        self.assertEqual(r["status"], "OK")
        self.assertEqual((r["matches"][0]["coverage_max_pct"], r["matches"][0]["far_max_pct"]), (80, 1300))
        r = zone_limits_for("서울특별시 종로구", ["계획관리지역"])  # 서울 조례 제1항 목록에 없어 매칭 0건 → 미확인
        self.assertEqual(r["status"], "UNKNOWN")
        self.assertEqual((r["matches"], r["unmatched"]), ([], ["계획관리지역"]))
        r = zone_limits_for("서울특별시 종로구", ["중심상업지역", "계획관리지역"])  # 일부만 확인
        self.assertEqual(r["status"], "PARTIAL")
        self.assertEqual(len(r["matches"]), 1)
        self.assertEqual(r["unmatched"], ["계획관리지역"])
        self.assertEqual(zone_limits_for("서울특별시 종로구", [])["status"], "UNKNOWN")

    def test_no_region_is_not_guessed(self):
        r = zone_limits_for("경기도 존재하지않는시 어딘구", ["제2종일반주거지역"])
        self.assertEqual(r["status"], "NO_REGION")
        self.assertEqual(r["matches"], [])

    def test_connected_local_city_returns_its_own_ordinance(self):
        local = [k for k in load()["regions"] if " " in k]
        if not local:
            self.skipTest("도 소재 시·군 데이터 없음")
        key = local[0]
        r = zone_limits_for(key + " 어딘가", ["제2종일반주거지역"])
        self.assertNotEqual(r["status"], "NO_REGION")
        self.assertEqual(r["region"], key)
        self.assertTrue(r["law"]["name"])

    def test_space_insensitive_zone_match(self):
        r = zone_limits_for("인천광역시 남동구", ["제2종 일반주거지역"])
        self.assertEqual(r["status"], "OK")

    def test_gwangju_carries_succession_note(self):
        r = zone_limits_for("광주광역시 북구", ["제2종일반주거지역"])
        self.assertTrue(any("통합특별시" in n for n in r["notes"]))


class SyncSources(unittest.TestCase):
    def test_sync_covers_regional_ordinances(self):
        names = {(s["name"], s.get("org")) for s in law_sync.sources()}
        for key, r in DATA["regions"].items():
            o = r["ordinance"]
            self.assertIn((o["name"], o["org"]), names, key)


if __name__ == "__main__":
    unittest.main()
