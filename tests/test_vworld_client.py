import unittest

import vworld_client as v


class FakeResp:
    def __init__(self, payload=None, bad_json=False):
        self.payload, self.bad_json = payload, bad_json

    def json(self):
        if self.bad_json:
            raise ValueError("not json")
        return self.payload


def getter_seq(*resps):
    calls = []

    def g(url, params=None, timeout=None):
        calls.append(params)
        return resps[min(len(calls) - 1, len(resps) - 1)]
    g.calls = calls
    return g


def ok(*names):
    return FakeResp({"response": {"status": "OK", "result": {"featureCollection": {
        "features": [{"properties": {"uname": n}} for n in names]}}}})


class VWorldClientTests(unittest.TestCase):
    KW = dict(key="SECRETKEY123", domain="localhost:8501", sleep=0)

    def test_ok_filters_blank_and_dedupes(self):
        g = getter_seq(ok("제3종일반주거지역", "", "제3종일반주거지역"))
        r = v.lookup_zones(1, 2, getter=g, **self.KW)
        self.assertEqual((r["status"], r["names"]), ("OK", ["제3종일반주거지역"]))

    def test_domain_param_sent(self):
        g = getter_seq(ok("중심상업지역"))
        v.lookup_zones(1, 2, getter=g, **self.KW)
        self.assertEqual(g.calls[0]["domain"], "localhost:8501")
        self.assertEqual(g.calls[0]["data"], "LT_C_UQ111")

    def test_district_plan_uses_uq141(self):
        g = getter_seq(ok("지구단위계획구역"))
        r = v.lookup_district_plan(1, 2, getter=g, **self.KW)
        self.assertEqual(g.calls[0]["data"], "LT_C_UQ141")
        self.assertEqual(r["names"], ["지구단위계획구역"])

    def test_not_found_is_not_error_and_not_assertion(self):
        g = getter_seq(FakeResp({"response": {"status": "NOT_FOUND"}}))
        r = v.lookup_district_plan(1, 2, getter=g, **self.KW)
        self.assertEqual((r["status"], r["names"], r["error"]), ("NOT_FOUND", [], None))

    def test_incorrect_key_is_error_without_retry_and_no_key_leak(self):
        g = getter_seq(FakeResp({"response": {"status": "ERROR", "error": {"code": "INCORRECT_KEY"}}}))
        r = v.lookup_zones(1, 2, getter=g, **self.KW)
        self.assertEqual(r["status"], "ERROR")
        self.assertEqual(len(g.calls), 1)
        self.assertNotIn("SECRETKEY123", str(r))
        self.assertIn("INCORRECT_KEY", r["error"])

    def test_bad_json_retries_then_succeeds(self):
        g = getter_seq(FakeResp(bad_json=True), ok("자연녹지지역"))
        r = v.lookup_zones(1, 2, getter=g, **self.KW)
        self.assertEqual((r["status"], len(g.calls)), ("OK", 2))

    def test_persistent_failure_is_error(self):
        g = getter_seq(FakeResp(bad_json=True))
        r = v.lookup_zones(1, 2, getter=g, **self.KW)
        self.assertEqual(r["status"], "ERROR")
        self.assertEqual(len(g.calls), 3)

    def test_missing_key(self):
        import os
        old = os.environ.pop("VWORLD_API_KEY", None)
        try:
            r = v.lookup_zones(1, 2, getter=getter_seq(ok("x")))
            self.assertEqual(r["status"], "ERROR")
        finally:
            if old is not None:
                os.environ["VWORLD_API_KEY"] = old


if __name__ == "__main__":
    unittest.main()
