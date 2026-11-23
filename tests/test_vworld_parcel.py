import unittest

import vworld_client as v
from tests.test_vworld_client import FakeResp, getter_seq, ok


def parcel(pnu="3020012200102200000", addr="대전광역시 유성구 궁동 220", jiga="882000"):
    return FakeResp({"response": {"status": "OK", "result": {"featureCollection": {
        "features": [{"properties": {"pnu": pnu, "addr": addr, "jiga": jiga}}]}}}})


def land(*rows):
    return FakeResp({"landCharacteristicss": {"field": list(rows)}})


ROW = {"stdrYear": "2025", "stdrMt": "01", "lndpclAr": "783859", "lndcgrCodeNm": "학교용지",
       "prposArea1Nm": "자연녹지지역", "prposArea2Nm": "제2종일반주거지역"}


class ParcelTests(unittest.TestCase):
    KW = dict(key="SECRETKEY123", domain="localhost:8501", sleep=0)

    def test_parcel_uses_cadastral_layer(self):
        g = getter_seq(parcel())
        r = v.lookup_parcel(127.3, 36.3, getter=g, **self.KW)
        self.assertEqual(g.calls[0]["data"], "LP_PA_CBND_BUBUN")
        self.assertEqual((r["status"], r["pnu"], r["jiga"]), ("OK", "3020012200102200000", 882000.0))

    def test_parcel_not_found(self):
        r = v.lookup_parcel(1, 2, getter=getter_seq(FakeResp({"response": {"status": "NOT_FOUND"}})), **self.KW)
        self.assertEqual(r["status"], "NOT_FOUND")

    def test_land_area_zones_and_latest_year(self):
        old = {**ROW, "stdrYear": "2024", "lndpclAr": "1", "prposArea1Nm": "상업지역"}
        r = v.lookup_land("P", getter=getter_seq(land(old, ROW)), **self.KW)
        self.assertEqual((r["status"], r["area"], r["jimok"], r["year"]), ("OK", 783859.0, "학교용지", "2025"))
        self.assertEqual(r["zones"], ["자연녹지지역", "제2종일반주거지역"])

    def test_land_single_dict_and_blank_zone(self):
        row = {**ROW, "prposArea2Nm": "", "lndpclAr": "1,234.5"}
        r = v.lookup_land("P", getter=getter_seq(FakeResp({"landCharacteristicss": {"field": row}})), **self.KW)
        self.assertEqual((r["area"], r["zones"]), (1234.5, ["자연녹지지역"]))

    def test_land_empty_is_not_found_and_error_has_no_key(self):
        r = v.lookup_land("P", getter=getter_seq(FakeResp({"landCharacteristicss": {"field": []}})), **self.KW)
        self.assertEqual(r["status"], "NOT_FOUND")
        r = v.lookup_land("P", getter=getter_seq(FakeResp(bad_json=True)), **self.KW)
        self.assertEqual(r["status"], "ERROR")
        self.assertNotIn("SECRETKEY123", str(r))
        self.assertIsNone(r["area"])

    def test_district_plan_ignores_other_districts(self):
        r = v.lookup_district_plan(1, 2, getter=getter_seq(ok("토지거래계약에관한허가구역")), **self.KW)
        self.assertEqual((r["status"], r["names"]), ("NOT_FOUND", []))
        r = v.lookup_district_plan(1, 2, getter=getter_seq(ok("토지거래계약에관한허가구역", "지구단위계획구역")), **self.KW)
        self.assertEqual((r["status"], r["names"]), ("OK", ["지구단위계획구역"]))


if __name__ == "__main__":
    unittest.main()
