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


def addr_ok(x, y):
    return FakeResp({"response": {"status": "OK", "result": {"point": {"x": str(x), "y": str(y)}}}})


class GeocodeTests(unittest.TestCase):
    KW = dict(key="SECRETKEY123", domain="localhost:8501", sleep=0)

    def test_parcel_ok(self):
        g = getter_seq(addr_ok(127.1, 36.2))
        r = v.geocode("대전 어딘가", getter=g, **self.KW)
        self.assertEqual((r["status"], r["x"], r["y"], r["type"]), ("OK", 127.1, 36.2, "parcel"))
        self.assertEqual(g.calls[0]["domain"], "localhost:8501")

    def test_falls_back_to_road(self):
        g = getter_seq(FakeResp({"response": {"status": "NOT_FOUND"}}), addr_ok(127.3, 36.3))
        r = v.geocode("둔산로 100", getter=g, **self.KW)
        self.assertEqual((r["status"], r["type"]), ("OK", "road"))
        self.assertEqual([c["type"] for c in g.calls], ["parcel", "road"])

    def test_all_not_found(self):
        g = getter_seq(FakeResp({"response": {"status": "NOT_FOUND"}}))
        r = v.geocode("없는주소", getter=g, **self.KW)
        self.assertEqual((r["status"], r["error"]), ("NOT_FOUND", None))

    def test_error_surfaces_code_without_key(self):
        g = getter_seq(FakeResp({"response": {"status": "ERROR", "error": {"code": "INCORRECT_KEY"}}}))
        r = v.geocode("x", getter=g, **self.KW)
        self.assertEqual(r["status"], "ERROR")
        self.assertIn("INCORRECT_KEY", r["error"])
        self.assertNotIn("SECRETKEY123", str(r))

    def test_network_failure_is_error_not_not_found(self):
        def boom(url, params=None, timeout=None):
            raise ConnectionError("blocked")
        r = v.geocode("x", getter=boom, **self.KW)
        self.assertEqual(r["status"], "ERROR")
        self.assertIn("ConnectionError", r["error"])

    def test_empty_address_and_missing_key(self):
        self.assertEqual(v.geocode("  ", getter=getter_seq(addr_ok(1, 2)), **self.KW)["status"], "NOT_FOUND")
        import os
        old = os.environ.pop("VWORLD_API_KEY", None)
        try:
            self.assertEqual(v.geocode("x", getter=getter_seq(addr_ok(1, 2)))["status"], "ERROR")
        finally:
            if old is not None:
                os.environ["VWORLD_API_KEY"] = old


class RelayTests(unittest.TestCase):
    def _fake_http(self, payload=None, bad=None, status=200, text=""):
        calls = []

        def http_get(url, params=None, headers=None, timeout=None):
            calls.append((url, params, headers))

            class R:
                status_code = status
                def json(self_inner):
                    if bad:
                        raise ValueError("not json")
                    return payload
            R.text = text
            return R()
        http_get.calls = calls
        return http_get

    def test_geocode_via_relay_maps_params_and_sends_token(self):
        http = self._fake_http({"response": {"status": "OK", "result": {"point": {"x": "127.1", "y": "36.2"}}}})
        g = v.make_relay_getter("https://relay.example/api/vworld", "tok", http_get=http)
        r = v.geocode("대전광역시 서구 둔산로 100", key="IGNORED", getter=g, sleep=0)
        self.assertEqual(r["status"], "OK")
        url, params, headers = http.calls[0]
        self.assertEqual(url, "https://relay.example/api/vworld")
        self.assertEqual(params, {"action": "geocode", "address": "대전광역시 서구 둔산로 100", "type": "parcel"})
        self.assertEqual(headers["x-relay-token"], "tok")
        self.assertNotIn("key", params)  # 키는 중계로 보내지 않는다

    def test_zone_and_plan_via_relay(self):
        http = self._fake_http({"response": {"status": "OK", "result": {"featureCollection": {
            "features": [{"properties": {"uname": "중심상업지역"}}]}}}})
        g = v.make_relay_getter("https://r/api/vworld", "tok", http_get=http)
        self.assertEqual(v.lookup_zones(127.38, 36.35, key="k", getter=g, sleep=0)["names"], ["중심상업지역"])
        v.lookup_district_plan(127.38, 36.35, key="k", getter=g, sleep=0)
        self.assertEqual([c[1]["action"] for c in http.calls], ["zone", "plan"])
        self.assertEqual((http.calls[0][1]["x"], http.calls[0][1]["y"]), ("127.38", "36.35"))

    def test_relay_error_shapes_are_surfaced(self):
        g = v.make_relay_getter("https://r/api/vworld", "tok", http_get=self._fake_http({"error": "unauthorized"}))
        r = v.lookup_zones(1, 2, key="k", getter=g, retries=0, sleep=0)
        self.assertEqual(r["status"], "ERROR")
        self.assertIn("unauthorized", r["error"])
        g = v.make_relay_getter("https://r/api/vworld", "tok", http_get=self._fake_http(
            {"error": "upstream_failed", "detail": "ECONNRESET"}))
        self.assertIn("ECONNRESET", v.lookup_zones(1, 2, key="k", getter=g, retries=0, sleep=0)["error"])

    def test_non_json_includes_status_and_masked_snippet(self):
        http = self._fake_http(bad=True, status=403, text="<html>Access denied 09AD1234-1234-1234-1234-123456789012</html>")
        r = v.lookup_zones(1, 2, key="k", getter=lambda u, params=None, timeout=None: http(u, params=params), retries=0, sleep=0)
        self.assertEqual(r["status"], "ERROR")
        self.assertIn("HTTP 403", r["error"])
        self.assertIn("Access denied", r["error"])
        self.assertNotIn("09AD1234", r["error"])

    def test_relay_env_makes_key_optional(self):
        import os
        saved = {k: os.environ.pop(k, None) for k in ("VWORLD_API_KEY", "VWORLD_RELAY_URL", "VWORLD_RELAY_TOKEN")}
        try:
            self.assertFalse(v.relay_configured())
            self.assertEqual(v.lookup_zones(1, 2, getter=lambda *a, **k: None)["status"], "ERROR")  # 키·중계 모두 없음
            os.environ["VWORLD_RELAY_URL"], os.environ["VWORLD_RELAY_TOKEN"] = "https://r/api/vworld", "tok"
            self.assertTrue(v.relay_configured())
            http = self._fake_http({"response": {"status": "NOT_FOUND"}})
            g = v.make_relay_getter("https://r/api/vworld", "tok", http_get=http)
            self.assertEqual(v.lookup_zones(1, 2, getter=g, sleep=0)["status"], "NOT_FOUND")  # 키 없이도 중계로 조회
        finally:
            for k in ("VWORLD_API_KEY", "VWORLD_RELAY_URL", "VWORLD_RELAY_TOKEN"):
                os.environ.pop(k, None)
                if saved[k] is not None:
                    os.environ[k] = saved[k]

    def test_relay_rejects_unknown_layer(self):
        g = v.make_relay_getter("https://r/api/vworld", "tok", http_get=self._fake_http({}))
        with self.assertRaises(ValueError):
            g(v.DATA_URL, params={"data": "LT_C_ANYTHING", "geomFilter": "POINT(1 2)"})


if __name__ == "__main__":
    unittest.main()
