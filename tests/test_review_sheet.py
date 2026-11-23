import json
import pathlib
import re
import unittest

from ordinance_landscape_parse import find_open_space_article, kn, parse_landscape, pct_at
from parking_regions import build as pk_build
from review_sheet import (USES, USE_LABELS, ReviewInput, build_review, pick_parking, review_to_json, review_to_markdown,
                          summary_values)
from law_core_v2 import PARKING_RULES
from ordinance_daejeon import DJ_PARKING_RULES

ROOT = pathlib.Path(__file__).resolve().parent.parent
LAND = json.loads((ROOT / "data" / "landscape_ordinances.json").read_text(encoding="utf-8"))["regions"]
REGIONS = {"서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시", "대전광역시", "울산광역시", "세종특별자치시"}


def snap(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def flat(rel):
    return re.sub(r"\s+", "", snap(rel))


def rows_by_item(rows):
    return {r.item: r for r in rows}


class LandscapeParser(unittest.TestCase):
    def test_korean_numbers(self):
        for s, v in (("2천", 2000), ("1천500", 1500), ("1천 500", 1500), ("1만", 10000), ("3만", 30000), ("300", 300), ("1,000", 1000)):
            self.assertEqual(kn(s), v, s)

    def test_three_tiers_and_variants(self):
        t = ("제24조(대지안의 조경)\n① 기준은 다음과 같다.\n"
             "1. 연면적의 합계가 2천제곱미터 이상인 건축물 : 대지면적의 15퍼센트 이상\n"
             "2. 연면적의 합계가 1천제곱미터 이상 2천제곱미터 미만인 건축물 : 대지면적의 100분의 10 이상\n"
             "3. 연면적 1천제곱미터 미만인 건축물：대지면적의 5퍼센트 이상\n"
             "5. 학교이적지 안의 건축물 : 대지면적의 30퍼센트 이상\n② 기타\n제25조(다른 조문)\n")
        r = parse_landscape(t)
        self.assertEqual(r["status"], "ok")
        self.assertEqual([(x["kind"], x["pct"]) for x in r["tiers"]], [("lt", 5), ("band", 10), ("ge", 15)])
        self.assertEqual(len(r["special_notes"]), 1)
        for fa, pct in ((500, 5), (999, 5), (1000, 10), (1999, 10), (2000, 15), (13000, 15)):
            self.assertEqual(pct_at(r["tiers"], fa), pct, fa)

    def test_gap_is_not_ok(self):
        t = ("제24조(대지안의 조경)\n① 기준\n1. 연면적 2천제곱미터 이상인 건축물 : 대지면적의 15퍼센트 이상\n"
             "2. 연면적 1천제곱미터 미만인 건축물 : 대지면적의 5퍼센트 이상\n② 기타\n")
        r = parse_landscape(t)
        self.assertEqual(r["status"], "tiers-not-contiguous")
        self.assertIsNone(pct_at(r["tiers"], 500))

    def test_open_space_block_found(self):
        t = "제34조(공개 공지 등의 확보)\n① 대상\n② 면적 100분의 5\n제35조(다음)\n"
        self.assertIn("100분의 5", find_open_space_article(t))


class LandscapeData(unittest.TestCase):
    def test_all_regions_ok(self):
        self.assertEqual(set(LAND), REGIONS)
        for k, r in LAND.items():
            self.assertEqual(r["status"], "ok", k)

    def test_json_matches_snapshot_reparse(self):
        for k, r in LAND.items():
            raw = snap(r["ordinance"]["snapshot"])
            self.assertNotIn("OC=", raw)
            body = "\n".join(l for l in raw.splitlines() if not l.startswith("#")).strip()
            p = parse_landscape(body)
            self.assertEqual(p["tiers"], r["tiers"], k)
            self.assertEqual(p["special_notes"], r["special_notes"], k)
            self.assertTrue(r["open_space"]["snapshot"], k)

    def test_spot_values_read_from_the_articles(self):
        t = {k: [(x["kind"], x["pct"]) for x in r["tiers"]] for k, r in LAND.items()}
        self.assertEqual(t["광주광역시"], [("lt", 7), ("band", 13), ("ge", 15)])
        for k in REGIONS - {"광주광역시"}:
            self.assertEqual(t[k], [("lt", 5), ("band", 10), ("ge", 15)], k)
        self.assertIn("학교이적지", LAND["서울특별시"]["special_notes"][0])
        self.assertIn("개발제한구역", LAND["울산광역시"]["special_notes"][0])


class NationalSnapshots(unittest.TestCase):
    def test_open_space_decree_thresholds(self):
        f = flat("data/law_snapshots/bldg_decree_art27_2_openspace_20261112.txt")
        for token in ("해당용도로쓰는바닥면적의합계가5천제곱미터이상인건축물", "대지면적의100분의10이하의범위에서건축조례로정한다",
                      "용적률은해당지역에적용하는용적률의1.2배이하", "높이기준의1.2배이하"):
            self.assertIn(token, f, token)
        a = flat("data/law_snapshots/bldg_act_art43_openspace.txt")
        for token in ("일반주거지역,준주거지역", "상업지역", "준공업지역"):
            self.assertIn(token, a, token)

    def test_landscape_thresholds(self):
        self.assertIn("면적이200제곱미터이상인대지", flat("data/law_snapshots/bldg_act_art42_landscape.txt"))
        d = flat("data/law_snapshots/bldg_decree_art27_landscape_20261112.txt")
        self.assertIn("녹지지역에건축하는건축물", d)
        self.assertIn("옥상부분조경면적의3분의2", d)
        self.assertIn("조경면적의100분의50을초과할수없다", d)

    def test_egress_and_firecompartment_thresholds(self):
        f = flat("data/law_snapshots/bldg_decree_art34_stairs_20261112.txt")
        for token in ("보행거리가30미터이하", "그보행거리가50미터", "16층이상인층에대해서는40미터",
                      "그층에서해당용도로쓰는바닥면적의합계가200제곱미터", "3층이상의층으로서그층거실의바닥면적의합계가400제곱미터이상",
                      "지하층으로서그층거실의바닥면적의합계가200제곱미터이상"):
            self.assertIn(token, f, token)
        self.assertIn("연면적이1천제곱미터를넘는", flat("data/law_snapshots/bldg_decree_art46_firecompart_20261112.txt"))


class ReviewSheet(unittest.TestCase):
    DJ = dict(address="대전광역시 서구 둔산로 100", zones=("중심상업지역",), use="업무시설", site_area=1000.0)

    def test_daejeon_sample_numbers(self):
        rows = build_review(ReviewInput(**self.DJ, total_floor_area=13000.0, has_district_plan=False))
        v = summary_values(rows)
        self.assertEqual(v["max_building_area"][1], 800)
        self.assertEqual(v["max_floor_area"][1], 13000)
        self.assertEqual(v["parking_count"][1], 130)
        self.assertEqual(v["accessible_parking_min"][1], 4)   # 130 × 3% = 3.9 → 올림
        self.assertEqual(v["landscape_min_area"][1], 150)     # 연면적 2,000㎡ 이상 15%
        by = rows_by_item(rows)
        self.assertEqual(by["정북방향 일조 이격"].status, "확정")  # 상업지역은 대상 아님
        self.assertIn("법정 대상", by["공개공지 등"].applied)

    def test_assumed_floor_area_is_marked_conditional(self):
        rows = build_review(ReviewInput(**self.DJ))
        by = rows_by_item(rows)
        self.assertEqual(by["부설주차장 법정 대수"].status, "조건부")
        self.assertIn("가정", by["부설주차장 법정 대수"].applied)

    def test_no_region_is_unconnected_not_guessed(self):
        rows = build_review(ReviewInput(address="경기도 존재하지않는시 어딘구", zones=("제2종일반주거지역",), use="업무시설", site_area=1000.0))
        by = rows_by_item(rows)
        self.assertEqual(by["건폐율"].status, "미연결")
        self.assertEqual(by["용적률"].status, "미연결")
        self.assertEqual(by["조경"].status, "미연결")
        self.assertEqual(summary_values(rows).get("max_floor_area"), None)

    def test_landscape_exemptions(self):
        small = rows_by_item(build_review(ReviewInput(**{**self.DJ, "site_area": 150.0})))
        self.assertIn("200㎡ 미만", small["조경"].applied)
        green = rows_by_item(build_review(ReviewInput(address="대전광역시 유성구 대학로 99", zones=("자연녹지지역",), use="업무시설", site_area=1000.0)))
        self.assertIn("면제", green["조경"].applied)
        self.assertEqual(green["조경"].status, "확정")

    def test_sunlight_applies_to_residential_zones(self):
        rows = rows_by_item(build_review(ReviewInput(address="대전광역시 유성구 어은동 99", zones=("제3종일반주거지역",), use="업무시설", site_area=1000.0)))
        r = rows["정북방향 일조 이격"]
        self.assertEqual(r.status, "조건부")
        self.assertIn("10m 부분 법 1.5m", r.applied)
        self.assertIn("17m 부분", r.applied)
        self.assertTrue(any("영 제86조제2항" in n for n in r.notes))

    def test_open_space_logic(self):
        def op(**kw):
            base = dict(address="대전광역시 서구 둔산로 100", zones=("일반상업지역",), use="업무시설", site_area=3000.0, total_floor_area=20000.0)
            return rows_by_item(build_review(ReviewInput(**{**base, **kw})))["공개공지 등"]
        self.assertIn("법정 대상", op(use_floor_area=5000.0).applied)       # 경계값 5,000㎡
        self.assertIn("비대상", op(use_floor_area=4999.0).applied)
        self.assertIn("대상 지역", op(zones=("자연녹지지역",), use_floor_area=9000.0).applied)  # 법 제43조 대상 지역 아님
        self.assertIn("열거 용도가 아님", op(use="의료시설", use_floor_area=9000.0).applied)
        self.assertEqual(op(use_floor_area=9000.0).status, "확정")           # 입력으로 결정
        self.assertTrue(any("조례 원문 발췌" in n for n in op(use_floor_area=9000.0).notes))

    def test_egress_judgement(self):
        def eg(**kw):
            return rows_by_item(build_review(ReviewInput(**{**self.DJ, "total_floor_area": 5000.0, **kw})))["직통계단 2개소 이상 설치 대상"]
        self.assertIn("2개소 이상 필요", eg(typical_floor_area=450.0).applied)           # 업무시설 3층 이상 400㎡
        self.assertIn("대상 아님", eg(typical_floor_area=350.0).applied)
        self.assertIn("지하층 2개소 이상", eg(basement_floor_area=250.0).applied)
        self.assertEqual(eg().status, "미확인")
        # 용도별 임계: 판매시설은 200㎡
        r = rows_by_item(build_review(ReviewInput(**{**self.DJ, "use": "판매시설", "total_floor_area": 5000.0, "typical_floor_area": 250.0})))
        self.assertIn("2개소 이상 필요", r["직통계단 2개소 이상 설치 대상"].applied)

    def test_firecompartment_threshold(self):
        r = lambda fa: rows_by_item(build_review(ReviewInput(**{**self.DJ, "total_floor_area": fa})))["방화구획"].applied
        self.assertIn("대상", r(1001.0))
        self.assertIn("대상 아님", r(1000.0))

    def test_housing_parking_is_not_computed(self):
        rows = build_review(ReviewInput(**{**self.DJ, "use": "공동주택(아파트 등)", "total_floor_area": 10000.0}))
        p = rows_by_item(rows)["부설주차장 법정 대수"]
        self.assertEqual(p.status, "미확인")
        self.assertIn("자동 산정하지 않음", p.applied)
        self.assertNotIn("parking_count", summary_values(rows))

    def test_public_building_prefers_public_office_standard_in_seoul(self):
        base = dict(address="서울특별시 종로구 세종대로 175", zones=("일반상업지역",), use="업무시설", site_area=1000.0, total_floor_area=10000.0)
        pr = summary_values(build_review(ReviewInput(**base)))["parking_count"][1]
        pu = summary_values(build_review(ReviewInput(**base, is_public=True)))["parking_count"][1]
        self.assertEqual((pr, pu), (100, 50))  # 일반 100㎡당 1대, 공공업무 200㎡당 1대

    def test_every_use_resolves_to_a_parking_rule_in_every_rule_set(self):
        sets = {"national": PARKING_RULES, "대전": DJ_PARKING_RULES}
        for region in REGIONS - {"대전광역시"}:
            sets[region] = pk_build(region, 0)[0]
        for name, rules in sets.items():
            for label, spec in USES.items():
                if spec.parking_manual:
                    continue
                key, _ = pick_parking(rules, spec)
                self.assertIsNotNone(key, (name, label))

    def test_unconnected_items_are_listed_and_exports_work(self):
        rows = build_review(ReviewInput(**self.DJ, total_floor_area=13000.0))
        un = [r.item for r in rows if r.section == "미연결 항목"]
        self.assertGreaterEqual(len(un), 5)
        md = review_to_markdown(rows, {"주소": "x"})
        self.assertIn("## 규모", md)
        self.assertIn("사전 검토용", md)
        data = json.loads(review_to_json(rows))
        keys = {r["key"]: r["value"] for r in data["rows"] if r["key"]}
        self.assertEqual(keys["max_floor_area"], 13000)

    def test_local_city_uses_its_own_ordinances(self):
        rows = build_review(ReviewInput(address="경기도 수원시 영통구 광교중앙로 140", zones=("일반상업지역",), use="업무시설", site_area=2000.0, total_floor_area=10000.0))
        by = rows_by_item(rows)
        self.assertIn("수원시", by["건폐율 → 최대 건축면적"].basis)
        self.assertIn("수원시 주차장 조례", by["부설주차장 법정 대수"].basis)

    def test_all_uses_build_without_error(self):
        for u in USE_LABELS:
            rows = build_review(ReviewInput(address="대전광역시 서구 둔산로 100", zones=("일반상업지역",), use=u, site_area=1000.0, total_floor_area=6000.0))
            self.assertTrue(all(r.status in ("확정", "조건부", "미확인", "미연결") for r in rows), u)


class NoSilentSubstitution(unittest.TestCase):
    RULES = {"c1": ("1", "위락시설", "시설면적㎡", 1, 70), "c10": ("10", "그 밖의 건축물", "시설면적㎡", 1, 200)}

    def test_enumerated_use_without_computable_rule_is_not_replaced(self):
        key, note = pick_parking(self.RULES, USES["판매시설"])
        self.assertIsNone(key)
        self.assertIn("수동", note)

    def test_unlisted_use_falls_back_to_other_buildings(self):
        key, _ = pick_parking(self.RULES, USES["교육연구시설(학교)"])
        self.assertEqual(key, "c10")

    def test_over_far_limit_input_is_flagged(self):
        rows = rows_by_item(build_review(ReviewInput(address="서울특별시 종로구 세종대로 175", zones=("일반상업지역",), use="업무시설",
                                                   site_area=1000.0, total_floor_area=10000.0)))
        far = rows["용적률 → 최대 연면적"]
        self.assertEqual(far.status, "조건부")
        self.assertIn("넘음", far.notes[0])
        ok = rows_by_item(build_review(ReviewInput(address="서울특별시 종로구 세종대로 175", zones=("일반상업지역",), use="업무시설",
                                                 site_area=1000.0, total_floor_area=8000.0)))["용적률 → 최대 연면적"]
        self.assertEqual(ok.status, "확정")
        self.assertNotIn("넘음", ok.notes[0])


if __name__ == "__main__":
    unittest.main()
