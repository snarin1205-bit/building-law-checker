import json
import pathlib
import unittest
from fractions import Fraction

from ordinance_daejeon import DJ_PARKING_RULES
from ordinance_parking_parse import parse_parking_annex, split_annex
from parking_regions import build, parking_required_region, region_data

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = json.loads((ROOT / "data" / "parking_ordinances.json").read_text(encoding="utf-8"))
REGIONS = {"서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시", "대전광역시", "울산광역시", "세종특별자치시"}


def annex_body(rel):
    t = (ROOT / rel).read_text(encoding="utf-8")
    return "\n".join(l for l in t.splitlines() if not l.startswith("#")).strip()


def count(region, items, variant=0):
    return parking_required_region(region, items, variant)


def cat(region, cid):
    return next(c for c in DATA["regions"][region]["categories"] if c["id"] == cid)


def div_of(region, cid, variant=0, sub=None):
    c = cat(region, cid)
    r = next(x for x in c["rules"] if sub is None or x["sublabel"] == sub)
    return Fraction(r["values"][variant]["div"]), Fraction(r["values"][variant]["mult"])


class ParserStructure(unittest.TestCase):
    def test_all_regions_present(self):
        self.assertEqual(set(DATA["regions"]), REGIONS)

    def test_json_matches_snapshot_reparse(self):
        """JSON 구조는 설치기준 별표 사본을 같은 파서로 다시 읽은 결과와 같아야 한다(수작업 수정 방지)."""
        for key, r in DATA["regions"].items():
            parsed = parse_parking_annex(annex_body(r["ordinance"]["annex_snapshot"]))
            for field in ("columns", "categories", "notes", "small_house_rule", "rounding_half_rule"):
                self.assertEqual(r[field], parsed[field], (key, field))

    def test_every_category_is_computable_or_manual_with_raw_text(self):
        for key, r in DATA["regions"].items():
            for c in r["categories"]:
                self.assertIn(c["kind"], ("area", "per_unit", "detached", "manual"), (key, c["id"]))
                self.assertTrue(c["raw"].strip())
                if c["kind"] == "manual":
                    self.assertTrue(c["reason"])
                if c["kind"] in ("area", "per_unit"):
                    ncols = max(1, len(r["columns"]))
                    for rule in c["rules"]:
                        self.assertEqual(len(rule["values"]), ncols, (key, c["id"]))

    def test_housing_category_is_manual_everywhere(self):
        for key, r in DATA["regions"].items():
            housing = [c for c in r["categories"] if "공동주택" in c["label"] and "기숙사" in c["label"]]
            self.assertTrue(housing, key)
            for c in housing:
                self.assertEqual(c["kind"], "manual", (key, c["id"]))

    def test_snapshots_carry_no_secrets(self):
        for key, r in DATA["regions"].items():
            for f in (r["ordinance"]["snapshot"], r["ordinance"]["annex_snapshot"]):
                t = (ROOT / f).read_text(encoding="utf-8")
                self.assertTrue(t.startswith("# 출처"))
                self.assertNotIn("OC=", t)

    def test_daejeon_parser_matches_verified_hand_table(self):
        """새 파서가 읽은 대전 값은 앞서 원문으로 검증한 ordinance_daejeon.DJ_PARKING_RULES 와 같아야 한다."""
        r = DATA["regions"]["대전광역시"]
        by_label = {}
        for c in r["categories"]:
            if c["kind"] == "area":
                by_label[c["no"]] = int(c["rules"][0]["values"][0]["div"])
        expected = {"1": DJ_PARKING_RULES["위락"][4], "2": DJ_PARKING_RULES["문화집회등"][4],
                    "3": DJ_PARKING_RULES["근생숙박"][4], "8": DJ_PARKING_RULES["창고"][4],
                    "9": DJ_PARKING_RULES["학생용기숙사"][4], "10": DJ_PARKING_RULES["기타"][4]}
        for no, v in expected.items():
            self.assertEqual(by_label[no], v, no)
        c6 = cat("대전광역시", "c6")
        self.assertEqual(c6["kind"], "per_unit")
        got = {x["sublabel"]: (Fraction(x["values"][0]["mult"]), Fraction(x["values"][0]["div"])) for x in c6["rules"]}
        self.assertEqual(got["골프장"], (15, 1))
        self.assertEqual(got["골프연습장"], (Fraction("1.5"), 1))
        self.assertEqual(got["옥외수영장"], (1, 15))
        self.assertEqual(got["관람장"], (1, 100))


class SpotValues(unittest.TestCase):
    """원문 별표를 눈으로 읽어 확인한 값."""

    def test_seoul(self):
        self.assertEqual(div_of("서울특별시", "c1"), (67, 1))
        self.assertEqual(div_of("서울특별시", "c3"), (134, 1))
        self.assertEqual(div_of("서울특별시", "c7"), (233, 1))
        self.assertEqual(div_of("서울특별시", "c8"), (267, 1))
        c = cat("서울특별시", "c2-1")
        self.assertEqual({x["sublabel"]: int(x["values"][0]["div"]) for x in c["rules"]},
                         {"일반업무시설": 100, "공공업무시설": 200})
        c10 = cat("서울특별시", "c10")
        subs = {x["sublabel"]: int(x["values"][0]["div"]) for x in c10["rules"]}
        self.assertEqual(sorted(subs.values()), [200, 250, 400])  # 학생용기숙사 400, 학교시설 250, 그 밖 200

    def test_busan_detached_thresholds(self):
        c = cat("부산광역시", "c4")
        self.assertEqual((c["kind"], c["upper"], c["step"]), ("detached", 180, 120))

    def test_daegu_note_and_values(self):
        self.assertEqual(div_of("대구광역시", "c1"), (70, 1))
        self.assertEqual(div_of("대구광역시", "c3"), (150, 1))
        self.assertIn("생활숙박시설은 호실당 1대", cat("대구광역시", "c3")["exception_note"])

    def test_incheon_two_columns(self):
        r = DATA["regions"]["인천광역시"]
        self.assertEqual(len(r["columns"]), 2)
        self.assertEqual((div_of("인천광역시", "c1", 0)[0], div_of("인천광역시", "c1", 1)[0]), (70, 100))
        self.assertEqual((div_of("인천광역시", "c9", 0)[0], div_of("인천광역시", "c9", 1)[0]), (350, 400))
        d0, m0 = div_of("인천광역시", "c6", 0, "골프연습장")
        self.assertEqual((m0, d0), (1, Fraction("0.7")))  # 0.7타석당 1대
        d1, m1 = div_of("인천광역시", "c6", 1, "골프연습장")
        self.assertEqual((m1, d1), (1, 1))

    def test_ulsan(self):
        self.assertEqual(div_of("울산광역시", "c8"), (233, 1))
        self.assertEqual(div_of("울산광역시", "c10"), (266, 1))
        self.assertEqual(cat("울산광역시", "c7")["kind"], "per_unit")
        self.assertIn("국가산업단지", cat("울산광역시", "c9")["exception_note"])

    def test_sejong(self):
        self.assertEqual(div_of("세종특별자치시", "c1"), (100, 1))
        self.assertEqual(div_of("세종특별자치시", "c2"), (134, 1))
        self.assertEqual(div_of("세종특별자치시", "c3"), (150, 1))
        c6 = {x["sublabel"]: (x["values"][0]["mult"], x["values"][0]["div"]) for x in cat("세종특별자치시", "c6")["rules"]}
        self.assertEqual(c6["골프연습장"], ("1.5", "1"))

    def test_gwangju_found_in_combined_annex(self):
        r = DATA["regions"]["광주광역시"]
        self.assertIn("합본", r["ordinance"]["annex_title"])
        self.assertEqual(div_of("광주광역시", "c1"), (67, 1))
        self.assertEqual(div_of("광주광역시", "c4"), (134, 1))
        self.assertEqual(cat("광주광역시", "c5")["kind"], "detached")


class Calculation(unittest.TestCase):
    def test_seoul_area(self):
        r = count("서울특별시", [("c1", 670)])  # 670/67 = 10
        self.assertEqual((r["status"], r["count"]), ("PREVIEW", 10))
        self.assertEqual(r["law"]["name"], "서울특별시 주차장 설치 및 관리 조례")

    def test_busan_detached_uses_busan_thresholds(self):
        # 부산 400㎡: 1 + (400-180)/120 = 2.8333.. -> 소수 첫째자리 2.8 -> 0.8 이상 1로 -> 3대
        self.assertEqual(count("부산광역시", [("c4", 400)])["count"], 3)
        # 150㎡(부산은 180 이하 1대)
        self.assertEqual(count("부산광역시", [("c4", 150)])["count"], 1)

    def test_incheon_variant_changes_result(self):
        self.assertEqual(count("인천광역시", [("c1", 700)], variant=0)["count"], 10)  # 700/70
        self.assertEqual(count("인천광역시", [("c1", 700)], variant=1)["count"], 7)   # 700/100
        r = count("인천광역시", [("c1", 700)], variant=1)
        self.assertTrue(any("적용 열" in n for n in r["notes"]))

    def test_sejong_range(self):
        self.assertEqual(count("세종특별자치시", [("c6:골프연습장", 20)])["count"], 30)  # 20×1.5
        self.assertEqual(count("세종특별자치시", [("c6:골프장", 9)])["count"], 135)

    def test_incheon_range_uses_division(self):
        self.assertEqual(count("인천광역시", [("c6:골프연습장", 14)], variant=0)["count"], 20)  # 14 ÷ 0.7

    def test_manual_category_is_not_computed(self):
        r = count("서울특별시", [("c5", 1000)])
        self.assertEqual(r["status"], "UNKNOWN")
        r = count("부산광역시", [("c1", 100), ("c5", 10)])
        self.assertEqual(r["status"], "UNKNOWN")

    def test_exception_note_surfaced(self):
        r = count("대구광역시", [("c3", 300)])
        self.assertEqual(r["status"], "PREVIEW")
        self.assertTrue(any("생활숙박시설은 호실당 1대" in n for n in r["notes"]))
        r = count("울산광역시", [("c9", 700)])
        self.assertTrue(any("국가산업단지" in n for n in r["notes"]))

    def test_related_annex_warning(self):
        r = count("서울특별시", [("c1", 100)])
        self.assertTrue(any("설치제한" in n for n in r["notes"]))

    def test_rounding_uses_decree_half_rule_and_ambiguity(self):
        # 서울 위락 67㎡당: 100/67=1.4925 -> 절사 1.4 / 반올림 1.5 -> 후보 1, 2
        r = count("서울특별시", [("c1", 100)])
        self.assertTrue(r["ambiguous"])
        self.assertEqual(r["candidates"], [1, 2])

    def test_unknown_region_and_key(self):
        self.assertEqual(parking_required_region("경기도", [("c1", 1)])["status"], "UNKNOWN")
        self.assertEqual(count("서울특별시", [("zzz", 1)])["status"], "UNKNOWN")

    def test_build_display_has_all_keys(self):
        rules, manual, special, display = build("서울특별시")
        for k in list(rules) + list(manual):
            self.assertIn(k, display)
        self.assertIn("c5", manual)
        self.assertIn("c4", special)


class ParserRobustness(unittest.TestCase):
    SAMPLE = ("부설주차장 설치기준(제14조 관련)\n시설물\n설치기준\n"
              "1. 위락시설\n- 시설면적 70제곱미터 당 1대\n"
              "2. 문화 및 집회시설\n- 시설면적 100제곱미터 당 1대\n"
              "3. 단독주택\n- 시설면적 50제곱미터 초과 150제곱미터 이하는 1대, 150제곱미터 초과하는 100제곱미터당 1대를 더한 대수\n"
              "4. 창고시설\n시설면적 400㎡당 1대\n"
              "1. 시설물의 종류는 다른 법령에 특별한 규정이 없는 한 건축법 시행령 별표 1에 따른다.\n"
              "2. 시설물의 시설면적은 공용면적을 포함한 바닥면적의 합계를 말한다.\n")

    def test_square_meter_word_is_read(self):
        r = parse_parking_annex(self.SAMPLE)
        by = {c["no"]: c for c in r["categories"]}
        self.assertEqual(by["1"]["kind"], "area")
        self.assertEqual(by["1"]["rules"][0]["values"][0]["div"], "70")
        self.assertEqual((by["3"]["kind"], by["3"]["upper"], by["3"]["step"]), ("detached", 150, 100))

    def test_numbered_notes_without_header_do_not_become_categories(self):
        r = parse_parking_annex(self.SAMPLE)
        self.assertEqual([c["no"] for c in r["categories"]], ["1", "2", "3", "4"])
        self.assertEqual(len(r["notes"]), 2)

    def test_partial_read_is_manual_not_silent(self):
        txt = ("1. 업무시설\n시설면적 100㎡당 1대\n일부 지역은 시설면적 150㎡당 1대\n")
        r = parse_parking_annex(txt)
        # 규칙이 2개 표기됐지만 열 구성이 없으므로 한쪽을 임의로 택하지 않고 수동 처리
        self.assertEqual(r["categories"][0]["kind"], "manual")


class SyncCoverage(unittest.TestCase):
    def test_sync_covers_parking_ordinances(self):
        import law_sync
        names = {(s["name"], s.get("org")) for s in law_sync.sources()}
        for key, r in DATA["regions"].items():
            o = r["ordinance"]
            self.assertIn((o["name"], o["org"]), names, key)


if __name__ == "__main__":
    unittest.main()
