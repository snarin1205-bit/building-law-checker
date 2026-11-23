import unittest
from law_core_v2 import route_laws, preview_area

class CoreV2Tests(unittest.TestCase):
    def test_public_facility_routes_bf(self):
        p = {x.law_group: x.priority for x in route_laws(building_use="도서관", is_public=True)}
        self.assertEqual(p["장애인 편의·BF"], "REQUIRED")
    def test_non_housing_low_priority(self):
        p = {x.law_group: x.priority for x in route_laws(building_use="행정복지센터", is_public=True)}
        self.assertEqual(p["주택법·도시정비법"], "LOW_PRIORITY")
    def test_housing_case_conditional(self):
        p = {x.law_group: x.priority for x in route_laws(is_housing_project=True)}
        self.assertEqual(p["주택법·도시정비법"], "CONDITIONAL")
    def test_unknown_address_does_not_assert_zoning(self):
        p = {x.law_group: x.priority for x in route_laws()}
        self.assertEqual(p["국토계획법·도시계획조례"], "UNKNOWN")
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

if __name__ == "__main__":
    unittest.main()
