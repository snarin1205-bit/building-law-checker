import os
import pathlib
import sys
import tempfile
import unittest

_tmp = tempfile.mkdtemp(prefix="ord_cache_")
os.environ.setdefault("LOCAL_ORD_CACHE", _tmp)
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
import build_local_ordinances as bl  # noqa: E402

from ordinance_parse import CANON_ZONES, article_block, parse_list, parse_ordinance  # noqa: E402
from ordinance_regions import region_of  # noqa: E402

PCT = {z: 50 + i for i, z in enumerate(CANON_ZONES)}


def rows(kind_pct, tail=""):
    return "\n".join(f"{i + 1}. {z} : {v}퍼센트{tail if i == 7 else ''}" for i, (z, v) in enumerate(kind_pct.items()))


class Candidates(unittest.TestCase):
    def test_org_filter_covers_counties_merged_jeonnam_and_metro_counties(self):
        for org in ("충청남도 부여군", "전남광주통합특별시 광양시", "전남광주통합특별시 신안군", "부산광역시 기장군", "울산광역시 울주군",
                    "대구광역시 달성군", "경기도 수원시", "강원특별자치도 삼척시"):
            self.assertTrue(bl.ORG.match(org), org)
        for org in ("부산광역시 해운대구", "대전광역시 유성구", "서울특별시 종로구"):
            self.assertFalse(bl.ORG.match(org), org)

    def test_name_filter_accepts_gun_and_variants_and_rejects_others(self):
        for n in ("부여군 군계획 조례", "고성군계획 조례", "진주시 도시계획조례", "수원시 도시계획 조례", "평창군 도시ㆍ군계획 조례", "의령군 계획 조례",
                  "거창군 계획조례", "장흥군 관리계획 조례", "청도군 군계획 조례 [제명개정 2020. 10. 5.]", "부산광역시 기장군 도시계획 조례"):
            self.assertTrue(bl.urban_name_ok(n), n)
        for n in ("창원시 도시계획변경 공공기여협상 운영에 관한 조례", "고성군 장기미집행 도시계획시설 대지보상 임시특별회계 설치 및 운용조례", "수원시 지구단위계획 조례",
                  "OO시 도시계획 조례 시행규칙", "고성군 장기미집행  도시계획시설 대지보상특별회계 설치 및 운영에 관한 조례"):
            self.assertFalse(bl.urban_name_ok(n), n)


class ParsingFallbacks(unittest.TestCase):
    def test_title_with_space_and_non_standard_wording(self):
        body = rows({z: v for z, v in PCT.items()})
        decoy = "제11조(도시지역 내 지구단위계획구역에서의 건폐율 등 완화) 시장은 완화할 수 있다.\n"
        for title in ("제33조(용도지역ㆍ지구 등에서의 건폐율)", "제53조 (용도지역에서의 건폐율)", "제33조(용도구역·지역·지구안에서의 건폐율)"):
            txt = decoy + title + "\n① 비율은 다음과 같다.\n" + body + "\n② 기타\n제34조(용적률)\n"
            cov, far, *_ = parse_ordinance(txt)
            self.assertEqual(len(cov), 21, title)
            self.assertEqual(cov["일반상업지역"], PCT["일반상업지역"])

    def test_decoy_article_never_chosen_when_no_rows(self):
        txt = "제11조(도시지역 내 지구단위계획구역에서의 건폐율 등 완화) 시장은 완화할 수 있다.\n제12조(다음)\n"
        self.assertIsNone(article_block(txt, "건폐율"))

    def test_existing_strict_title_unchanged(self):
        txt = "제55조(용도지역 안에서의 건폐율)\n① 다음과 같다.\n" + rows(PCT) + "\n② 기타\n"
        self.assertEqual(len(parse_ordinance(txt)[0]), 21)

    def test_parse_list_from_annex_text_with_notes(self):
        txt = "【별표 27】\n용도지역에서의 건폐율\n  " + rows(PCT, "(다만, 신도시구역은 60퍼센트)").replace("\n", "\n  ")
        vals, notes = parse_list(txt)
        self.assertEqual(len(vals), 21)
        self.assertEqual(vals["제1종전용주거지역"], PCT["제1종전용주거지역"])
        self.assertIn("신도시구역", notes[CANON_ZONES[7]])
        self.assertEqual(parse_list("관계없는 문서")[0], {})


class RegionMapping(unittest.TestCase):
    KNOWN = {"전남광주통합특별시 광양시": 1, "충청남도 부여군": 1, "부산광역시 기장군": 1, "경기도 수원시": 1}

    def test_jeonnam_both_spellings_map_to_merged_org(self):
        for a in ("전라남도 광양시 중앙로 1", "전남 광양시 중앙로 1", "전남광주통합특별시 광양시 중앙로 1"):
            self.assertEqual(region_of(a, self.KNOWN), "전남광주통합특별시 광양시", a)

    def test_gun_and_metro_county(self):
        self.assertEqual(region_of("충남 부여군 부여읍 1", self.KNOWN), "충청남도 부여군")
        self.assertEqual(region_of("부산광역시 기장군 기장읍 1", self.KNOWN), "부산광역시 기장군")
        self.assertEqual(region_of("부산광역시 해운대구 우동 1", self.KNOWN), "부산광역시")
        self.assertEqual(region_of("부산광역시 기장군 기장읍 1", {}), "부산광역시")   # 군 데이터가 없으면 광역시 조례로
        self.assertIsNone(region_of("전라남도 없는시 1", self.KNOWN))


if __name__ == "__main__":
    unittest.main()
