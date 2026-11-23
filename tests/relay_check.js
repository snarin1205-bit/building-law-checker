// api/vworld.js 로컬 점검 (CI 제외): node tests/relay_check.js
const assert = require("assert");
const handler = require("../api/vworld.js");

function call(query, headers, env) {
  Object.assign(process.env, { VWORLD_API_KEY: "KEY-SECRET-AAAA-BBBB-CCCCDDDDEEEE", VWORLD_DOMAIN: "dom.example.app",
    RELAY_TOKEN: "tok123", VERCEL_REGION: "icn1" }, env || {});
  return new Promise((resolve) => {
    const res = { headers: {}, setHeader(k, v) { this.headers[k] = v; }, end(b) { resolve({ status: this.statusCode, headers: this.headers, body: b }); } };
    handler({ query, headers: headers || {}, url: "/api/vworld" }, res);
  });
}
const T = { "x-relay-token": "tok123" };
let lastUrl = null;
global.fetch = async (url) => { lastUrl = String(url); return { status: 200, headers: { get: () => "application/json" },
  text: async () => JSON.stringify({ response: { status: "OK" } }) }; };

(async () => {
  let r = await call({ action: "zone", x: "127.38", y: "36.35" }, {});
  assert.strictEqual(r.status, 401, "토큰 없으면 401");
  r = await call({ action: "zone", x: "127.38", y: "36.35" }, { "x-relay-token": "wrong" });
  assert.strictEqual(r.status, 401, "틀린 토큰 401");
  r = await call({ action: "zone", x: "127.38", y: "36.35" }, T, { RELAY_TOKEN: "" });
  assert.strictEqual(r.status, 500, "미설정 500");
  r = await call({ action: "zone", x: "127.38", y: "36.35" }, T);
  assert.strictEqual(r.status, 200);
  assert.ok(lastUrl.includes("LT_C_UQ111") && lastUrl.includes("domain=dom.example.app"));
  assert.strictEqual(r.headers["x-relay-region"], "icn1");
  r = await call({ action: "plan", x: "127.38", y: "36.35" }, T);
  assert.ok(lastUrl.includes("LT_C_UQ141"));
  r = await call({ action: "geocode", address: "대전광역시 서구 둔산로 100", type: "road" }, T);
  assert.ok(lastUrl.includes("api.vworld.kr/req/address") && lastUrl.includes("type=road"));
  for (const bad of [{ action: "zone", x: "abc", y: "36" }, { action: "zone", x: "127;rm", y: "36" }, { action: "zone", x: "10", y: "36" },
                     { action: "geocode", address: "", type: "road" }, { action: "geocode", address: "x", type: "evil" },
                     { action: "delete" }, {}]) {
    r = await call(bad, T);
    assert.strictEqual(r.status, 400, JSON.stringify(bad));
  }
  global.fetch = async () => ({ status: 403, headers: { get: () => "text/html" }, text: async () => "<html>Access denied KEY-SECRET</html>" });
  r = await call({ action: "zone", x: "127.38", y: "36.35" }, T);
  assert.strictEqual(r.status, 502);
  assert.ok(JSON.parse(r.body).error === "upstream_non_json" && JSON.parse(r.body).upstream_status === 403);
  global.fetch = async () => { const e = new TypeError("fetch failed"); e.cause = { code: "ECONNRESET" }; throw e; };
  r = await call({ action: "zone", x: "127.38", y: "36.35" }, T);
  assert.strictEqual(r.status, 502);
  assert.strictEqual(JSON.parse(r.body).detail, "ECONNRESET");
  assert.ok(!r.body.includes("KEY-SECRET"), "응답에 키가 없어야 함");
  console.log("relay_check OK");
})().catch((e) => { console.error("FAIL", e.message); process.exit(1); });
