import json
import unittest
from law_core_v2 import (route_laws, preview_area, classify_zones, far_counted_area,
                         findings_to_markdown, findings_to_json, sort_findings,
                         parking_required, PARKING_RULES, PARKING_LAW_META,
                         FAR_EXCLUSION_KEYS, FAR_LAW_META)


def pri(**kw):
    return {x.law_group: x.priority for x in route_laws(**kw)}


class CoreV2Tests(unittest.TestCase):
    def test_public_facility_routes_bf(self):
        self.assertEqual(pri(building_use="도서관", is_public=True)["장애인 편의·BF"], "REQUIRED")

    def test_non_housing_low_priority(self):
        self.assertEqual(pri(building_use="행정복지센터", is_public=True)["주택법·도시정비법"], "LOW_PRIORITY")

    def test_housing_case_conditional(self):
        self.assertEqual(pri(is_housing_project=True)["주택법·도시정비법"], "CONDITIONAL")

    def test_unknown_address_does_not_assert_zoning(self):
        self.assertEqual(pri()["국토계획법·도시계획조례"], "UNKNOWN")

    def test_unknown_area_does_not_assert_legal_result(self):
        self.assertEqual(preview_area(None, 100, 200, 60, 200)["status"], "UNKNOWN")

    def test_arithmetic_preview(self):
        p = preview_area(1000, 580, 1900, 60, 200)
        self.assertEqual(p["max_building_area_m2"], 600)
        self.assertEqual(p["max_far_counted_area_m2"], 2000)
        self.assertEqual(p["status"], "PREVIEW")

    def test_exceed(self):
        p = preview_area(1000, 700, 2100, 60, 200)
        self.assertEqual(p["building_area_check"], "EXCEEDS_INPUT_LIMIT")
        self.assertEqual(p["far_area_check"], "EXCEEDS_INPUT_LIMIT")

    def test_invalid_percent(self):
        self.assertEqual(preview_area(100, 1, 1, 101, 100)["status"], "UNKNOWN")

    # --- v2.1 ---
    def test_preview_rejects_nan_and_negative(self):
        self.assertEqual(preview_area(float("nan"), 1, 1, 60, 200)["status"], "UNKNOWN")
        self.assertEqual(preview_area(100, -5, 1, 60, 200)["status"], "UNKNOWN")

    def test_zone_classification(self):
        z = classify_zones(["제2종일반주거지역"])
        self.assertEqual(z["categories"], ["일반주거"])
        self.assertFalse(z["overlap"])
        self.assertFalse(classify_zones([])["known"])
        self.assertFalse(classify_zones(None)["known"])

    def test_zone_overlap_flagged(self):
        p = pri(zone_names=["제2종일반주거지역", "일반상업지역"])
        self.assertEqual(p["용도지역 중첩·걸침 검토"], "REQUIRED")
        self.assertNotIn("용도지역 중첩·걸침 검토", pri(zone_names=["일반상업지역"]))

    def test_unmatched_zone_is_unknown(self):
        self.assertEqual(pri(zone_names=["알수없는지역"])["미분류 용도지역 명칭"], "UNKNOWN")

    def test_far_counted_area(self):
        r = far_counted_area(3000, {"underground": 800, "above_ground_parking": 200})
        self.assertEqual(r["far_counted_area_m2"], 2000)
        self.assertEqual(r["status"], "PREVIEW")

    def test_far_counted_area_errors(self):
        self.assertEqual(far_counted_area(0)["status"], "UNKNOWN")
        self.assertEqual(far_counted_area(100, {"underground": 200})["status"], "UNKNOWN")
        self.assertEqual(far_counted_area(100, {"bogus": 1})["status"], "UNKNOWN")
        self.assertEqual(far_counted_area(100, {"underground": -1})["status"], "UNKNOWN")
        self.assertEqual(far_counted_area("abc")["status"], "UNKNOWN")

    def test_export(self):
        f = route_laws(building_use="도서관", site_address="x", site_area=100)
        self.assertEqual(sort_findings(f)[0].priority, "REQUIRED")
        self.assertIn("사전 검토용", findings_to_markdown(f, {"주소": "x"}))
        data = json.loads(findings_to_json(f))
        self.assertEqual(len(data["findings"]), len(f))

    def test_source_urls_present_for_statutes(self):
        f = {x.law_group: x for x in route_laws()}
        self.assertTrue(f["건축법·건축법 시행령"].source_url.startswith("https://www.law.go.kr/"))

    # --- parking: 주차장법 시행령 별표 1 (사본과 대조) ---
    def test_parking_rules_match_snapshot(self):
        import pathlib, re
        snap = (pathlib.Path(__file__).resolve().parent.parent / "data" / "law_snapshots" /
                "parking_decree_b1_20260828.txt").read_text(encoding="utf-8")
        flat = re.sub(r"[\s┃│┏┓┗┛━┯┷┠┨┼─]+", "", snap)
        for key, (no, label, unit, mult, div) in PARKING_RULES.items():
            if unit == "시설면적㎡" and div:
                self.assertIn(f"시설면적{div}㎡당1대(시설면적/{div}㎡)", flat, key)
        for token in ("1홀당10대", "1타석당1대", "정원15명당1대", "정원100명당1대",
                      "시설면적50㎡초과150㎡이하:1대", "[1+{(시설면적-150㎡)/100㎡}]",
                      "0.5이상인경우에는이를1로본다"):
            self.assertIn(token, flat, token)
        self.assertEqual(PARKING_LAW_META["effective_date"], "2026-08-28")

    def test_parking_basic_half_rule(self):
        # 기타 300㎡당 1대: 410/300=1.366.. -> 소수 첫째자리 1.3(절사)/1.4(반올림) -> 0.5 미만 -> 1대
        r = parking_required([("기타", 410)])
        self.assertEqual(r["count"], 1)
        # 근생 200㎡당: 700/200 = 3.5 -> 0.5 이상이므로 4대 (올림 아닌 0.5 규칙)
        self.assertEqual(parking_required([("근생숙박", 700)])["count"], 4)
        # 699/200 = 3.495 -> 3.4(절사)/3.5(반올림) -> 후보 3, 4 : 확정하지 않음
        r = parking_required([("근생숙박", 699)])
        self.assertTrue(r["ambiguous"])
        self.assertEqual(r["candidates"], [3, 4])
        self.assertIsNone(r["count"])
        # 590/200 = 2.95 -> 2.9/3.0 -> 후보 3, 3 => 3 확정
        self.assertEqual(parking_required([("근생숙박", 590)])["count"], 3)

    def test_parking_not_ceil(self):
        # 올림이면 3이지만 원문은 0.5 미만 버림: 410/200 = 2.05 -> 2대
        self.assertEqual(parking_required([("근생숙박", 410)])["count"], 2)

    def test_parking_units(self):
        self.assertEqual(parking_required([("골프장", 9)])["count"], 90)
        self.assertEqual(parking_required([("골프연습장", 30)])["count"], 30)
        self.assertEqual(parking_required([("옥외수영장", 150)])["count"], 10)
        self.assertEqual(parking_required([("관람장", 1000)])["count"], 10)

    def test_parking_detached_house(self):
        self.assertEqual(parking_required([("단독주택", 100)])["count"], 1)
        self.assertEqual(parking_required([("단독주택", 150)])["count"], 1)
        self.assertEqual(parking_required([("단독주택", 350)])["count"], 3)  # 1+(350-150)/100

    def test_parking_half_to_one_conflict_is_ambiguous(self):
        r = parking_required([("기타", 150)])  # 0.5대: 본문 1대 vs 단서 0대
        self.assertTrue(r["ambiguous"])
        self.assertEqual(r["candidates"], [0, 1])

    def test_parking_housing_is_manual(self):
        r = parking_required([("다가구공동오피스텔", 1000)])
        self.assertEqual(r["status"], "UNKNOWN")
        self.assertEqual(parking_required([("기타", 100), ("다가구공동오피스텔", 1)])["status"], "UNKNOWN")

    def test_parking_ordinance_override_is_marked(self):
        r = parking_required([("근생숙박", 400)], {"근생숙박": 134})
        self.assertEqual(r["rows"][0]["basis"], "조례 입력값(미검증)")
        self.assertEqual(parking_required([("골프장", 1)], {"골프장": 5})["status"], "UNKNOWN")

    def test_parking_invalid_inputs(self):
        self.assertEqual(parking_required([])["status"], "UNKNOWN")
        self.assertEqual(parking_required([("없는키", 1)])["status"], "UNKNOWN")
        self.assertEqual(parking_required([("기타", -1)])["status"], "UNKNOWN")
        self.assertEqual(parking_required([("기타", "abc")])["status"], "UNKNOWN")

    def test_north_light_not_asserted_by_zone(self):
        key = "건축법 일조·높이·대지안의 공지"
        self.assertEqual(pri(zone_names=["제1종전용주거지역"])[key], "CONDITIONAL")


    # --- 건축법령 사본 대조 ---
    def _snap(self, name):
        import pathlib
        return (pathlib.Path(__file__).resolve().parent.parent / "data" / "law_snapshots" / name
                ).read_text(encoding="utf-8")

    def test_far_exclusions_match_decree_art119(self):
        import re
        flat = re.sub(r"\s+", "", self._snap("bldg_decree_art119_20261112.txt"))
        for token in ("지하층의면적", "지상층의주차용(해당건축물의부속용도인경우만해당한다)으로쓰는면적",
                      "제34조제3항및제4항에따라초고층건축물과준초고층건축물에설치하는피난안전구역의면적",
                      "제40조제4항제2호에따라건축물의경사지붕아래에설치하는대피공간의면적",
                      "다.삭제", "라.삭제"):
            self.assertIn(token, flat, token)
        self.assertEqual(len(FAR_EXCLUSION_KEYS), 4)
        self.assertEqual(FAR_LAW_META["effective_date"], "2026-11-12")

    def test_decree_art86_exceptions_in_snapshot(self):
        import re
        flat = re.sub(r"\s+", "", self._snap("bldg_decree_art86_20261112.txt"))
        self.assertIn("정북방향의인접대지가전용주거지역이나일반주거지역이아닌용도지역에해당하는경우", flat)
        self.assertIn("너비20미터이상의도로", flat)

    def test_act_art61_snapshot_marked_pending(self):
        head = self._snap("bldg_act_art61_PENDING_20270212.txt")[:600]
        self.assertIn("현행 시행본 아님", head)

    def test_north_light_finding_cites_decree_not_numbers(self):
        f = {x.law_group: x for x in route_laws(zone_names=["제2종일반주거지역"])}
        c = f["건축법 일조·높이·대지안의 공지"].condition
        self.assertIn("2027-02-12", c)
        self.assertEqual(f["건축법 일조·높이·대지안의 공지"].priority, "CONDITIONAL")


if __name__ == "__main__":
    unittest.main()
