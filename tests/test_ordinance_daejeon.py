import pathlib
import re
import unittest

import law_sync
from ordinance_daejeon import (DJ_ZONE_LIMITS, DJ_PARKING_RULES, DJ_META, zone_limits, is_daejeon,
                               parking_required_daejeon)

ROOT = pathlib.Path(__file__).resolve().parent.parent / "data" / "law_snapshots"


def snap(name):
    return (ROOT / name).read_text(encoding="utf-8")


def flat(s):
    return re.sub(r"\s+", "", s)


def norm(s):
    return "".join(s.split())


class SnapshotTables(unittest.TestCase):
    def _block(self, text, start, end):
        i = text.index(start)
        return text[i:text.index(end, i)]

    def test_coverage_table_matches_ordinance_art45(self):
        text = snap("daejeon_urban_ordinance_20260213.txt")
        blk = self._block(text, "제45조(용도지역 안에서의 건폐율)", "② 「전통시장")
        rows = re.findall(r"^\d+\. ([^:\n]+): (\d+)퍼센트 이하", blk, re.M)
        self.assertEqual(len(rows), 22)
        for name, pct in rows:
            self.assertEqual(DJ_ZONE_LIMITS[norm(name)][0], int(pct), name)

    def test_far_table_matches_ordinance_art50(self):
        text = snap("daejeon_urban_ordinance_20260213.txt")
        blk = self._block(text, "제50조(용도지역 안에서의 용적률)", "② 「전통시장")
        rows = re.findall(r"^\d+\. ([^:\n]+): ([\d,]+)퍼센트 이하", blk, re.M)
        self.assertEqual(len(rows), 22)
        for name, pct in rows:
            self.assertEqual(DJ_ZONE_LIMITS[norm(name)][1], int(pct.replace(",", "")), name)

    def test_parking_b6_matches_snapshot(self):
        f = flat(snap("daejeon_parking_ordinance_b6_20251226.txt"))
        for token in ("시설면적67㎡당1대", "시설면적100㎡당1대", "시설면적134㎡당1대",
                      "골프장:1홀당15대", "골프연습장:1타석당1.5대", "옥외수영장:정원15인당1대",
                      "관람장:정원100인당1대", "시설면적200㎡당1대(시설면적/200㎡)다만,산업단지공장용건축물은450㎡당1대",
                      "시설면적400㎡당1대", "[1+(시설면적-150㎡/50㎡)", "50㎡초과150㎡이하이면1대"):
            self.assertIn(token, f, token)
        self.assertEqual(DJ_PARKING_RULES["위락"][4], 67)
        self.assertEqual(DJ_PARKING_RULES["문화집회등"][4], 100)
        self.assertEqual(DJ_PARKING_RULES["근생숙박"][4], 134)
        self.assertEqual(DJ_PARKING_RULES["산단공장"][4], 450)
        self.assertEqual(DJ_PARKING_RULES["골프장"][3], 15)
        self.assertEqual(DJ_PARKING_RULES["골프연습장"][3], 1.5)
        self.assertNotIn("데이터센터", f)  # 별표 6에 데이터센터 항목이 없다는 전제 확인

    def test_parking_ordinance_art16_points_to_b6(self):
        self.assertIn("제16조(부설주차장의 설치기준)", snap("daejeon_parking_ordinance_20251226.txt"))

    def test_yuseong_refers_to_city_ordinance(self):
        t = snap("yuseong_parking_ordinance_20251002.txt")
        self.assertIn("「대전광역시 주차장 조례」별표 6", t)
        self.assertIn("직선 거리 300미터 이내", t)
        self.assertNotIn("퍼센트 이하", snap("yuseong_urban_ordinance_20260923.txt"))  # 수치 없음

    def test_building_ordinance_art43_quote(self):
        t = flat(snap("daejeon_building_ordinance_20261008.txt"))
        self.assertIn("영제86조제1항에따라일조(日照)등의확보를위하여", t)
        self.assertIn("높이10미터이하인부분:인접대지경계선으로부터1.5미터이상", t)

    def test_meta_effective_dates_recorded(self):
        self.assertEqual(DJ_META["parking"]["effective"], "2025-12-26")
        self.assertEqual(DJ_META["urban"]["effective"], "2026-02-13")


class ZoneLimits(unittest.TestCase):
    def test_single_zone(self):
        r = zone_limits(["제2종일반주거지역"])
        self.assertEqual(r["status"], "OK")
        self.assertEqual((r["matches"][0]["coverage_max_pct"], r["matches"][0]["far_max_pct"]), (60, 200))

    def test_space_insensitive_and_unknown(self):
        self.assertEqual(zone_limits(["일반 상업 지역"])["matches"][0]["far_max_pct"], 1100)
        r = zone_limits(["없는지역"])
        self.assertEqual(r["status"], "UNKNOWN")
        self.assertEqual(r["unmatched"], ["없는지역"])
        self.assertEqual(zone_limits([])["status"], "UNKNOWN")

    def test_overlap_and_partial(self):
        r = zone_limits(["제2종일반주거지역", "일반상업지역"])
        self.assertTrue(r["overlap"])
        self.assertEqual(zone_limits(["준주거지역", "엉뚱"])["status"], "PARTIAL")

    def test_is_daejeon(self):
        self.assertTrue(is_daejeon("대전광역시 유성구 어은동"))
        self.assertFalse(is_daejeon("서울특별시 강남구"))


class DaejeonParking(unittest.TestCase):
    def test_daejeon_rate_differs_from_national(self):
        # 근린생활 134㎡당: 670/134 = 5.0 -> 5대 (국가 기준 200㎡당이면 3.35 -> 3대)
        self.assertEqual(parking_required_daejeon([("근생숙박", 670)])["count"], 5)

    def test_half_rule_applies_via_decree_note(self):
        # 위락 67㎡당: 100/67 = 1.4925 -> 1.4(절사)/1.5(반올림) -> 1대/2대 후보
        r = parking_required_daejeon([("위락", 100)])
        self.assertTrue(r["ambiguous"])
        self.assertEqual(r["candidates"], [1, 2])

    def test_golf_units(self):
        self.assertEqual(parking_required_daejeon([("골프장", 9)])["count"], 135)
        self.assertEqual(parking_required_daejeon([("골프연습장", 30)])["count"], 45)

    def test_multi_house(self):
        self.assertEqual(parking_required_daejeon([("다중주택", 100)])["count"], 1)
        self.assertEqual(parking_required_daejeon([("다중주택", 350)])["count"], 5)  # 1+(350-150)/50
        self.assertEqual(parking_required_daejeon([("다중주택", 40)])["status"], "UNKNOWN")
        self.assertEqual(parking_required_daejeon([("단독주택", 350)])["count"], 3)

    def test_data_center_and_housing_not_computed(self):
        self.assertEqual(parking_required_daejeon([("데이터센터", 1000)])["status"], "UNKNOWN")
        self.assertEqual(parking_required_daejeon([("다가구공동오피스텔", 10)])["status"], "UNKNOWN")

    def test_notes_include_ordinance_items(self):
        r = parking_required_daejeon([("기타", 400)])
        self.assertEqual(r["count"], 2)
        self.assertTrue(any("300미터" in n for n in r["notes"]))
        self.assertTrue(any("100분의 3" in n for n in r["notes"]))
        self.assertEqual(r["law"]["effective"], "2025-12-26")


class LawSyncOffline(unittest.TestCase):
    def _fake(self, rows):
        def fetch(params):
            if params["pageNo"] != "1":
                return "<LawSearch></LawSearch>"
            return "".join(
                f'<law id="{i}"><{params_tag}>{n}</{params_tag}><공포번호>{pn}</공포번호>'
                f'<시행일자>{eff}</시행일자><지자체기관명>{org}</지자체기관명></law>'
                for i, (params_tag, n, pn, eff, org) in enumerate(rows))
        return fetch

    def test_detects_ok_changed_notfound(self):
        src = {"name": "X법", "kind": "law", "promulgation_no": "1", "effective": "2026-01-01", "queries": ["X"]}
        ok = law_sync.find_current(src, self._fake([("법령명한글", "X법", "1", "20260101", "")]))
        self.assertEqual(ok, {"promulgation_no": "1", "effective": "2026-01-01"})
        self.assertIsNone(law_sync.find_current(src, self._fake([("법령명한글", "Y법", "1", "20260101", "")])))
        ch = law_sync.find_current(src, self._fake([("법령명한글", "X법", "2", "20270101", "")]))
        self.assertNotEqual((ch["promulgation_no"], ch["effective"]), ("1", "2026-01-01"))

    def test_ordinance_requires_org_match(self):
        src = {"name": "주차장 조례", "kind": "ordin", "org": "대전광역시", "promulgation_no": "1",
               "effective": "2026-01-01", "queries": ["q"]}
        self.assertIsNone(law_sync.find_current(src, self._fake([("자치법규명", "주차장 조례", "1", "20260101", "서울특별시")])))

    def test_sources_cover_all_snapshots(self):
        names = {s["name"] for s in law_sync.sources()}
        for m in DJ_META.values():
            self.assertIn(m["name"], names)
        self.assertIn("주차장법 시행령", names)


if __name__ == "__main__":
    unittest.main()
