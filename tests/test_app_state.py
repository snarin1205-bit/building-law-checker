"""화면 상태 유지: 결과 화면에서 체크박스·선택 칸을 눌러도 첫 화면으로 돌아가지 않아야 한다(AppTest, 네트워크는 가짜로 대체)."""
import os
import pathlib
import unittest
from unittest import mock

from streamlit.testing.v1 import AppTest

import vworld_client as v

ROOT = pathlib.Path(__file__).resolve().parent.parent


def fake_site(address, **kw):
    return {"geocode": {"status": "OK", "x": 127.2370, "y": 36.2865, "type": "parcel", "error": None},
            "parcel": {"status": "OK", "pnu": "4425011500", "addr": "충청남도 계룡시 엄사면 엄사리 1", "jiga": 1.0, "error": None},
            "land": {"status": "OK", "area": 1000.0, "jimok": "대", "zones": ["제2종일반주거지역"], "year": "2026", "error": None},
            "zones": {"status": "OK", "names": ["제2종일반주거지역"], "error": None},
            "plan": {"status": "NOT_FOUND", "names": [], "error": None},
            "greenbelt": {"status": "NOT_FOUND", "names": [], "error": None}}


class AppStateTests(unittest.TestCase):
    def run_app(self):
        # AppTest 는 같은 프로세스에서 스크립트를 실행하므로 app 이 import 하는 조회 함수를 가짜로 바꾼다.
        self.patches = [mock.patch.object(v, "lookup_site", fake_site)]
        for p in self.patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self.patches])
        os.environ.setdefault("VWORLD_API_KEY", "dummy-key-for-test")
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120).run()
        return at

    def test_results_survive_widget_clicks(self):
        at = self.run_app()
        at.text_input[0].set_value("충청남도 계룡시 엄사면 엄사리 1")
        at.button[0].click().run()
        before = [s.value for s in at.subheader]
        self.assertIn("2. 법규검토서 — 이 대지에서 지켜야 할 기준", before)
        # 결과 화면의 선택 칸(항목별 비고 선택)을 바꿔도 결과가 남아야 한다
        sel = [s for s in at.selectbox if s.key == "review_sel"][0]
        sel.select(sel.options[2]).run()
        self.assertEqual([s.value for s in at.subheader], before)
        self.assertEqual(len(at.exception), 0)

    def test_new_search_replaces_results_and_empty_start_has_none(self):
        at = self.run_app()
        self.assertEqual([s.value for s in at.subheader if s.value.startswith("1.")], [])   # 첫 화면엔 결과 없음
        at.text_input[0].set_value("충청남도 계룡시 엄사면 엄사리 1")
        at.button[0].click().run()
        self.assertTrue(any(s.value.startswith("1. 기본 자료") for s in at.subheader))


if __name__ == "__main__":
    unittest.main()
