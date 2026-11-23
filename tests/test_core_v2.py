import json
import unittest
from law_core_v2 import (route_laws, preview_area, classify_zones, far_counted_area,
                         findings_to_markdown, findings_to_json, sort_findings)


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

    def test_north_light_depends_on_zone(self):
        key = "건축법 일조·높이·대지안의 공지"
        self.assertEqual(pri(zone_names=["제1종전용주거지역"])[key], "REQUIRED")
        self.assertEqual(pri(zone_names=["일반상업지역"])[key], "CONDITIONAL")
        self.assertEqual(pri()[key], "CONDITIONAL")  # 미확인은 해당없음 아님

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


if __name__ == "__main__":
    unittest.main()
