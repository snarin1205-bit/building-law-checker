import json
import pathlib
import unittest

from ordinance_sunlight_parse import parse, value_at
from sunlight_regions import note, region_data, setback

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = json.loads((ROOT / "data" / "sunlight_ordinances.json").read_text(encoding="utf-8"))
REGIONS = {"서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시", "대전광역시", "울산광역시", "세종특별자치시"}


class Parser(unittest.TestCase):
    TEXT3 = ("제35조(일조 등의 확보를 위한 건축물의 높이제한) ① 법 제61조제1항에 따라 다음 각 호와 같다.\n"
             "1. 삭제\n2. 높이 10미터 이하인 부분 : 인접대지 경계선으로부터 1.5미터 이상\n"
             "3. 높이 10미터 초과 17미터 이하인 부분 : 인접대지 경계선으로부터 5미터 이상\n"
             "4. 높이 17미터를 초과하는 부분 : 인접대지경계선으로부터 해당 건축물의 각 부분의 높이의 2분의 1 이상\n"
             "② 기타\n제36조(다른 조문) ① 내용\n")
    TEXT2 = ("제43조(일조 등의 확보를 위한 건축물의 높이제한)\n① 영 제86조제1항에서 정한다.\n"
             "2. 높이 10미터 이하인 부분: 인접 대지경계선으로부터 1.5미터 이상\n"
             "3. 높이 10미터를 초과하는 부분 : 인접 대지경계선으로부터 해당 건축물의 각 부분의 높이의 2분의 1 이상\n② 기타\n")

    def test_three_tiers(self):
        r = parse(self.TEXT3)
        self.assertEqual(r["status"], "ok")
        self.assertEqual(len(r["tiers"]), 3)
        self.assertEqual(r["cites"], "법 제61조제1항")
        for h, v in ((10, 1.5), (10.5, 5), (17, 5), (20, 10), (30, 15)):
            self.assertAlmostEqual(value_at(r["tiers"], h), v, msg=str(h))

    def test_two_tiers_and_stale_cite(self):
        r = parse(self.TEXT2)
        self.assertEqual((r["status"], r["cites"], len(r["tiers"])), ("ok", "영 제86조제1항", 2))
        self.assertAlmostEqual(value_at(r["tiers"], 14), 7.0)

    def test_gap_in_tiers_is_not_ok(self):
        t = ("제1조(일조 등의 확보를 위한 건축물의 높이 제한)\n① 거리\n"
             "1. 높이 9미터 이하인 부분: 1.5미터 이상\n2. 높이 10미터를 초과하는 부분: 높이의 2분의 1 이상\n② 기타\n")
        r = parse(t)
        self.assertEqual(r["status"], "tiers-not-contiguous")
        self.assertIsNone(value_at(r["tiers"], 5))

    def test_title_with_space_and_missing_article(self):
        t = "제32조 (일조 등의 확보를 위한 건축물의 높이제한)\n① 영 제86조제1항\n1. 높이 10미터 이하인 부분: 1.5미터 이상\n2. 높이 10미터를 초과하는 부분: 높이의 2분의 1 이상\n② x\n"
        self.assertEqual(parse(t)["status"], "ok")
        self.assertEqual(parse("제1조(목적) 내용")["status"], "no-article")


class Data(unittest.TestCase):
    def test_all_regions_present_and_parsed(self):
        self.assertEqual(set(DATA["regions"]), REGIONS)
        for k, r in DATA["regions"].items():
            self.assertEqual(r["status"], "ok", k)

    def test_json_matches_snapshot_reparse(self):
        for k, r in DATA["regions"].items():
            txt = (ROOT / r["ordinance"]["snapshot"]).read_text(encoding="utf-8")
            body = "\n".join(l for l in txt.splitlines() if not l.startswith("#")).strip()
            p = parse(body)
            self.assertEqual(p["tiers"], r["tiers"], k)
            self.assertEqual(p["cites"], r["cites"], k)
            self.assertNotIn("OC=", txt)

    def test_known_cities(self):
        d = DATA["regions"]
        # 원문을 읽어 확인한 구성: 서울·대구는 법 제61조 3단계, 그 밖은 영 제86조제1항 인용 2단계
        for k in ("서울특별시", "대구광역시"):
            self.assertEqual((d[k]["cites"], len(d[k]["tiers"])), ("법 제61조제1항", 3), k)
        for k in ("부산광역시", "인천광역시", "광주광역시", "대전광역시", "울산광역시", "세종특별자치시"):
            self.assertEqual((d[k]["cites"], len(d[k]["tiers"])), ("영 제86조제1항", 2), k)


class Compare(unittest.TestCase):
    def test_updated_ordinance_has_no_conflict(self):
        for h in (5, 10, 14, 17, 20, 40):
            r = setback("서울특별시", h)
            self.assertFalse(r["conflict"], h)
            self.assertFalse(r["stale_basis"])
            self.assertEqual(r["conservative_m"], r["law_min_m"])

    def test_stale_ordinance_conflicts_only_in_band(self):
        r = setback("부산광역시", 14)  # 법 5m, 조례 문언 7m
        self.assertEqual((r["law_min_m"], r["ordinance_text_m"], r["conservative_m"], r["conflict"], r["stale_basis"]),
                         (5.0, 7.0, 7.0, True, True))
        self.assertFalse(setback("부산광역시", 5)["conflict"])
        self.assertFalse(setback("부산광역시", 20)["conflict"])

    def test_conservative_never_below_law(self):
        for k in REGIONS:
            for h in (1, 9.9, 10, 10.1, 12, 16.9, 17, 17.1, 25):
                r = setback(k, h)
                self.assertGreaterEqual(r["conservative_m"], r["law_min_m"], (k, h))

    def test_no_data_region_and_invalid(self):
        self.assertEqual(setback("경기도 성남시", 12)["status"], "NO_DATA")
        self.assertEqual(setback("서울특별시", 0)["status"], "UNKNOWN")
        self.assertIsNone(region_data("경기도 성남시"))

    def test_note_mentions_basis(self):
        self.assertIn("영 제86조제1항", note("대전광역시"))
        self.assertIn("삭제", note("대전광역시"))
        self.assertIn("법 제61조제1항에 따라", note("서울특별시"))


class SyncCoverage(unittest.TestCase):
    def test_sync_covers_sunlight_ordinances(self):
        import law_sync
        names = {(s["name"], s.get("org")) for s in law_sync.sources()}
        for k, r in DATA["regions"].items():
            o = r["ordinance"]
            self.assertIn((o["name"], o["org"]), names, k)


if __name__ == "__main__":
    unittest.main()
