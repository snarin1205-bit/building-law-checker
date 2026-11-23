import json
import pathlib
import unittest

import vworld_client as v
from greenbelt_parse import flat, kn, parse_resident_opinion, parse_standard, section2
from review_sheet import ReviewInput, build_review, summary_values
from tests.test_vworld_client import FakeResp, getter_seq, ok

ROOT = pathlib.Path(__file__).resolve().parent.parent
GB = json.loads((ROOT / "data" / "greenbelt.json").read_text(encoding="utf-8"))


def body(rel):
    return "\n".join(l for l in (ROOT / rel).read_text(encoding="utf-8").splitlines() if not l.startswith("#"))


def by_item(rows):
    return {r.item: r for r in rows}


class GreenbeltParse(unittest.TestCase):
    def test_kn(self):
        self.assertEqual(kn("1천500"), 1500)
        self.assertEqual(kn("5천"), 5000)
        self.assertEqual(kn("232"), 232)

    def test_json_matches_snapshot_reparse(self):
        a = GB["annex2"]
        re_ = parse_standard(body(a["snapshot"]))
        self.assertEqual(re_, {k: v for k, v in a.items() if k != "snapshot"})
        o = GB["art20"]
        self.assertEqual(parse_resident_opinion(body(o["snapshot"])), {"floor_area_m2": o["floor_area_m2"], "notice_days": o["notice_days"]})

    def test_values_are_the_ones_in_the_articles(self):
        a = GB["annex2"]
        self.assertEqual(a["status"], "ok")
        self.assertEqual(a["general"], {"coverage_pct": 60, "max_floors": 5, "far_pct": 300})
        self.assertEqual(a["housing"][0], {"coverage_pct": 60, "max_floors": 3, "far_pct": 300, "max_floor_area_m2": 232, "max_floor_area_designated_resident_m2": 300})
        self.assertEqual(a["housing"][1], {"coverage_pct": 20, "max_floors": 3, "far_pct": 100})
        self.assertEqual(a["min_site_area_m2"], 60)
        self.assertEqual((GB["art20"]["floor_area_m2"], GB["art20"]["notice_days"]), (1500, 14))

    def test_raw_text_contains_the_sentences(self):
        f = flat(body(GB["annex2"]["snapshot"]))
        for t in ("건폐율100분의60이하로건축하되높이5층이하,용적률300퍼센트이하로한다", "대지면적이60제곱미터미만인경우에는건축물의건축을허가하지아니하여야한다"):
            self.assertIn(t, f)
        self.assertIn("제22조(허가또는신고의기준)법제12조제9항에따른허가또는신고의세부기준은별표2와같다", flat(body("data/law_snapshots/greenbelt_decree_art22.txt")))
        self.assertIn("개발제한구역에서는건축물의건축", flat(body(GB["act12"])))

    def test_unparseable_text_is_not_guessed(self):
        self.assertEqual(parse_standard("관계없는 문서")["status"], "section-not-found")
        broken = "2. 건축물의 건축 또는 공작물의 설치\n 가. 건폐율은 조례로 정한다.\n3. 토지의 형질변경"
        self.assertEqual(parse_standard(broken)["status"], "general-not-parsed")
        self.assertNotIn("general", parse_standard(broken))


class GreenbeltReview(unittest.TestCase):
    BASE = dict(address="대전광역시 대덕구 연축동 산 1", zones=("자연녹지지역", "개발제한구역"), use="운수시설(여객용)", site_area=100000.0)

    def test_replaces_ordinance_limits_with_decree_limits(self):
        rows = build_review(ReviewInput(**self.BASE, total_floor_area=50000.0, planned_building_area=60000.0))
        by = by_item(rows)
        self.assertIn("개발제한구역법", by["건폐율 → 최대 건축면적"].basis)
        self.assertIn("60%", by["건폐율 → 최대 건축면적"].standard)
        self.assertIn("→ 적합", by["건폐율 → 최대 건축면적"].applied)
        v_ = summary_values(rows)
        self.assertEqual((v_["max_building_area"][1], v_["max_floor_area"][1]), (60000, 300000))
        self.assertIn("5층 이하", by["높이(층수)"].applied)
        self.assertNotIn("건폐율", by)   # 조례 기반 행은 나오지 않음
        over = by_item(build_review(ReviewInput(**self.BASE, planned_building_area=60001.0)))
        self.assertIn("초과(부적합)", over["건폐율 → 최대 건축면적"].applied)

    def test_flag_without_zone_name_and_note_mentions_ordinance_reference(self):
        rows = by_item(build_review(ReviewInput(address="대전광역시 대덕구 연축동 산 1", zones=("자연녹지지역",), use="업무시설", site_area=1000.0, in_greenbelt=True)))
        self.assertTrue(any("자연녹지지역" in n and "조례 상한" in n for n in rows["건폐율 → 최대 건축면적"].notes))
        self.assertTrue(any("허용 시설" in n or "별표 1" in n for n in rows["건폐율 → 최대 건축면적"].notes))

    def test_min_site_area_and_resident_opinion(self):
        small = by_item(build_review(ReviewInput(**{**self.BASE, "site_area": 59.0})))
        self.assertIn("건축 불허", small["최소 대지면적"].applied)
        self.assertIn("해당 없음", by_item(build_review(ReviewInput(**{**self.BASE, "site_area": 60.0})))["최소 대지면적"].applied)
        r = lambda fa: by_item(build_review(ReviewInput(**self.BASE, total_floor_area=fa)))["주민 의견청취"].applied
        self.assertIn("의견청취 대상", r(1500.0))
        self.assertIn("해당 없음", r(1499.0))

    def test_non_greenbelt_unchanged(self):
        rows = by_item(build_review(ReviewInput(address="대전광역시 서구 둔산로 100", zones=("중심상업지역",), use="업무시설", site_area=1000.0)))
        self.assertIn("도시계획 조례", rows["건폐율 → 최대 건축면적"].basis)
        self.assertNotIn("주민 의견청취", rows)


class GreenbeltLookup(unittest.TestCase):
    KW = dict(key="K", domain="localhost:8501", sleep=0)

    def test_layer_and_filter(self):
        g = getter_seq(ok("개발제한구역"))
        r = v.lookup_greenbelt(1, 2, getter=g, **self.KW)
        self.assertEqual(g.calls[0]["data"], "LT_C_UD801")
        self.assertEqual((r["status"], r["names"]), ("OK", ["개발제한구역"]))
        r = v.lookup_greenbelt(1, 2, getter=getter_seq(ok("다른구역")), **self.KW)
        self.assertEqual(r["status"], "NOT_FOUND")
        r = v.lookup_greenbelt(1, 2, getter=getter_seq(FakeResp({"response": {"status": "NOT_FOUND"}})), **self.KW)
        self.assertEqual(r["status"], "NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
