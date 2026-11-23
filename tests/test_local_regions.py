"""도 소재 시·군 조례 데이터(data/local_zone_limits.json, data/local_parking.json) 검증. 파일이 없으면 건너뛴다."""
import json
import pathlib
import unittest

from ordinance_parking_parse import completeness, find_follow_decree, parse_parking_annex
import re

from ordinance_parse import CANON_ZONES, parse_article, parse_hwp_table, parse_list, zone_table
from ordinance_regions import region_of

ROOT = pathlib.Path(__file__).resolve().parent.parent
ZONE_FILE = ROOT / "data" / "local_zone_limits.json"
PARK_FILE = ROOT / "data" / "local_parking.json"


def read(rel):
    t = (ROOT / rel).read_text(encoding="utf-8")
    return t, "\n".join(l for l in t.splitlines() if not l.startswith("#")).strip()


@unittest.skipUnless(ZONE_FILE.exists(), "local_zone_limits.json 없음")
class LocalZoneLimits(unittest.TestCase):
    DATA = json.loads(ZONE_FILE.read_text(encoding="utf-8"))["regions"] if ZONE_FILE.exists() else {}

    def test_regions_are_do_si_gun_keys(self):
        self.assertGreater(len(self.DATA), 30)
        for key in self.DATA:
            sido, _, sg = key.partition(" ")
            self.assertTrue(sg.endswith(("시", "군")), key)
            self.assertTrue(sido.endswith(("도", "특별자치도", "특별시", "광역시")), key)   # 전남광주통합특별시, 광역시 소속 군 포함

    def test_json_matches_snapshot_reparse(self):
        for key, r in self.DATA.items():
            o = r["ordinance"]
            raw, body = read(o["snapshot"])
            self.assertNotIn("OC=", raw)
            if o["method"] == "annex-hwp":
                cov, far = parse_hwp_table(body)
                self.assertEqual(r["zones"], zone_table(cov, far, {}, {}), key)
            elif o["method"] == "annex-list":   # 건폐율 별표 + 용적률 별표가 따로 있는 조례: '# 별표 ...' 구분선으로 나뉜 두 목록
                parts = re.split(r"^# 별표 '[^\n]*\n", raw, flags=re.M)
                self.assertGreaterEqual(len(parts), 3, key)
                (cov, cn), (far, fn) = parse_list(parts[-2]), parse_list(parts[-1])   # 마지막 두 구간 = 건폐율 별표, 용적률 별표
                self.assertEqual(r["zones"], zone_table(cov, far, cn, fn), key)
            else:
                (cov, cn), (far, fn) = parse_article(body, "건폐율"), parse_article(body, "용적률")
                self.assertEqual(r["zones"], zone_table(cov, far, cn, fn), key)

    def test_value_sanity(self):
        for key, r in self.DATA.items():
            zz = r["zones"]
            self.assertGreaterEqual(len(zz), 8, key)
            for z, v in zz.items():
                self.assertIn(z, CANON_ZONES)
                if v["coverage"] is not None:
                    self.assertTrue(0 < v["coverage"] <= 100, (key, z))
                if v["far"] is not None:
                    self.assertTrue(0 < v["far"] <= 1500, (key, z))
                if v["coverage"] and v["far"]:
                    self.assertGreaterEqual(v["far"], v["coverage"], (key, z))
            seq = [(zz.get(z) or {}).get("far") for z in ("제1종전용주거지역", "제2종전용주거지역", "제1종일반주거지역",
                                                          "제2종일반주거지역", "제3종일반주거지역", "준주거지역")]
            vals = [x for x in seq if x is not None]
            self.assertEqual(vals, sorted(vals), (key, "주거 용적률은 종이 높을수록 같거나 커야 함", seq))

    def test_missing_lists_consistent(self):
        for key, r in self.DATA.items():
            for kind in ("coverage", "far"):
                missing = {z for z in CANON_ZONES if r["zones"].get(z, {}).get(kind) is None}
                self.assertEqual(set(r["missing"][kind]), missing, (key, kind))

    def test_every_region_resolves_from_an_address(self):
        for key in self.DATA:
            self.assertEqual(region_of(key + " 가상구 1", self.DATA), key)


@unittest.skipUnless(PARK_FILE.exists(), "local_parking.json 없음")
class LocalParking(unittest.TestCase):
    DATA = json.loads(PARK_FILE.read_text(encoding="utf-8"))["regions"] if PARK_FILE.exists() else {}

    def tables(self):
        return {k: r for k, r in self.DATA.items() if not r.get("follows_decree")}

    def follows(self):
        return {k: r for k, r in self.DATA.items() if r.get("follows_decree")}

    def test_json_matches_annex_snapshot_reparse(self):
        for key, r in self.tables().items():
            raw, body = read(r["ordinance"]["annex_snapshot"])
            self.assertNotIn("OC=", raw)
            parsed = parse_parking_annex(body)
            for field in ("columns", "categories", "notes", "small_house_rule", "rounding_half_rule"):
                self.assertEqual(r[field], parsed[field], (key, field))
            self.assertEqual({k: r[k] for k in ("incomplete", "manual_heavy")}, completeness(r["categories"]), key)

    def test_enough_computable_categories_and_manual_housing(self):
        for key, r in self.tables().items():
            ok = [c for c in r["categories"] if c["kind"] in ("area", "per_unit", "detached")]
            self.assertGreaterEqual(len(ok), 3, key)
            for c in r["categories"]:
                self.assertTrue(c["raw"].strip())
                if "주택건설기준" in c["raw"]:
                    self.assertEqual(c["kind"], "manual", (key, c["id"]))
                if c["kind"] in ("area", "per_unit"):
                    for rule in c["rules"]:
                        self.assertEqual(len(rule["values"]), max(1, len(r["columns"])), (key, c["id"]))
                        for v in rule["values"]:
                            self.assertGreater(float(v["div"]), 0)

    def test_area_divisors_are_plausible(self):
        """설치기준 ㎡당 1대 값은 현실적인 범위(20~2,000㎡)여야 한다 — 파싱 오류(자릿수 등) 탐지."""
        for key, r in self.tables().items():
            for c in r["categories"]:
                if c["kind"] == "area":
                    for rule in c["rules"]:
                        for v in rule["values"]:
                            self.assertTrue(20 <= float(v["div"]) <= 2000, (key, c["id"], v))

    def test_follows_decree_entries_match_article_snapshot(self):
        f = self.follows()
        self.assertGreaterEqual(len(f), 5)
        for key, r in f.items():
            raw, body = read(r["ordinance"]["snapshot"])
            self.assertNotIn("OC=", raw)
            fd = find_follow_decree(body)
            self.assertIsNotNone(fd, key)
            self.assertEqual(fd["title"], r["article"], key)
            self.assertEqual(fd["proviso"], r["proviso"], key)
            self.assertEqual(r["categories"], [], key)

    def test_known_follow_cases_from_reading_the_articles(self):
        # 조문을 읽어 확인: 양구(영 별표 1과 같다, 단서=설치 면제), 서천/청양/태안/울진(영 별표 1 준용·따른다, 단서=공장 예외)
        for city in ("강원특별자치도 양구군", "충청남도 서천군", "충청남도 청양군", "충청남도 태안군", "경상북도 울진군"):
            self.assertTrue(self.DATA[city].get("follows_decree"), city)
        # 시행령 표를 직접 고치거나(합천) 자체 규정이 있는(제천) 조례는 '그대로 따름'으로 인정하지 않는다
        for city in ("경상남도 합천군", "충청북도 제천시"):
            self.assertNotIn(city, self.follows())


class FollowDecreeDetection(unittest.TestCase):
    def art(self, body):
        return "제13조(부설주차장의 설치기준)\n" + body + "\n제14조(다른 조문)\n내용\n"

    def test_positive_cases(self):
        for body in ("② 부설주차장의 설치기준은 영 별표 1과 같다. 다만, 공장은 500제곱미터당 1대로 한다.",
                     "부설주차장의 설치기준은 「주차장법 시행령」 제6조제1항의 별표 1과 같다.",
                     "부설주차장의 설치기준은 영 별표 1을 준용한다.",
                     "설치대상 시설물종류 및 설치기준은 「주차장법 시행령」(이하 \"영\"이라 한다) 제6조제1항을 따른다."):
            fd = find_follow_decree(self.art(body))
            self.assertIsNotNone(fd, body)
        self.assertIn("공장", find_follow_decree(self.art("설치기준은 영 별표 1과 같다. 다만, 공장은 500제곱미터당 1대로 한다."))["proviso"])

    def test_negative_cases(self):
        # 자체 별표를 인용
        self.assertIsNone(find_follow_decree(self.art("설치기준은 별표 2와 같다.")))
        # 시행령 표를 직접 수정하는 단서
        self.assertIsNone(find_follow_decree(self.art(
            "설치기준은 영 별표 1과 같다. 다만, 단독주택의 \"50㎡ 초과 150㎡ 이하\"를 \"100㎡ 초과 150㎡ 이하\"로 한다.")))
        # 별도 기준을 정하면서 영 별표 1은 하한으로만 언급
        self.assertIsNone(find_follow_decree(self.art(
            "영 제6조제1항 단서에 따라 다음 각 호의 건축물의 부설주차장 설치기준은 다음과 같다(영 별표 1의 기준으로 산정한 주차대수 이상이 되도록 하여야 한다).")))
        # 관계없는 조문(장애인 전용)
        self.assertIsNone(find_follow_decree("제10조(장애인 전용주차구획의 설치기준)\n설치기준은 영 별표 1과 같다.\n"))


class Completeness(unittest.TestCase):
    def test_flags(self):
        few = [{"kind": "area"}] * 3 + [{"kind": "manual"}] * 4
        self.assertEqual(completeness(few), {"incomplete": True, "manual_heavy": True})
        many = [{"kind": "area"}] * 8 + [{"kind": "manual"}]
        self.assertEqual(completeness(many), {"incomplete": False, "manual_heavy": False})


if __name__ == "__main__":
    unittest.main()
