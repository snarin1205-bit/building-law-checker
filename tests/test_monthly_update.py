import sys
import unittest

sys.path.insert(0, "tools")
import monthly_update as mu


def src(name, group):
    return {"name": name, "group": group}


class Classify(unittest.TestCase):
    def test_changed_urban_triggers_rebuild_and_national_is_manual(self):
        srcs = [src("서울특별시 도시계획 조례", "urban"), src("건축법 시행령", "national"), src("서울특별시 건축 조례", "sunlight+landscape"), src("대전광역시 주차장 조례", "daejeon")]
        res = [{"name": "서울특별시 도시계획 조례", "status": "CHANGED", "expected": "a", "found": "b"},
               {"name": "건축법 시행령", "status": "CHANGED", "expected": "a", "found": "b"},
               {"name": "서울특별시 건축 조례", "status": "CHANGED", "expected": "a", "found": "b"},
               {"name": "대전광역시 주차장 조례", "status": "CHANGED", "expected": "a", "found": "b"}]
        auto, manual, bad = mu.classify(res, srcs)
        self.assertEqual(auto, {"urban", "sunlight", "landscape"})
        self.assertEqual({m[0]["name"] for m in manual}, {"건축법 시행령", "대전광역시 주차장 조례"})
        self.assertEqual(bad, [])

    def test_ok_nothing_and_errors_reported(self):
        srcs = [src("A", "parking"), src("B", "parking")]
        auto, manual, bad = mu.classify([{"name": "A", "status": "OK"}, {"name": "B", "status": "ERROR", "detail": "x"}], srcs)
        self.assertEqual((auto, manual), (set(), []))
        self.assertEqual([b["name"] for b in bad], ["B"])

    def test_local_ordinance_uses_local_tool(self):
        names = mu.local_names()
        self.assertTrue(names)
        n = sorted(names)[0]
        auto, manual, bad = mu.classify([{"name": n, "status": "CHANGED", "expected": "a", "found": "b"}], [src(n, "urban")])
        self.assertEqual(auto, {"local"})

    def test_unknown_group_goes_manual_and_report_lists_it(self):
        auto, manual, bad = mu.classify([{"name": "X", "status": "CHANGED", "expected": "a", "found": "b"}], [src("X", "zzz")])
        self.assertEqual(auto, set())
        self.assertEqual(manual[0][1], ["unknown"])
        md = mu.report_md("2026-12-01", [{"name": "X", "status": "CHANGED", "expected": "a", "found": "b"}], auto, manual, bad, [])
        self.assertIn("수동 확인 필요", md)
        self.assertIn("X", md)

    def test_every_rebuild_tool_exists(self):
        import pathlib
        for g, (tool, _) in mu.REBUILD.items():
            self.assertTrue((mu.ROOT / tool).exists(), g)


if __name__ == "__main__":
    unittest.main()
