// VWorld 중계 함수 (Vercel, 서울 리전 icn1 고정 — vercel.json).
// 목적: 해외 서버(Streamlit Cloud 등)에서 VWorld 호출이 막히는 문제를 한국 IP에서 대신 호출해 우회.
// 보안: 공유 토큰(x-relay-token)이 맞아야만 동작. VWorld 키·도메인은 환경변수에만 둔다.
// 허용 호출: 주소 좌표(geocode), 용도지역(zone), 지구단위계획구역(plan) 세 가지뿐.
//
// 환경변수(Vercel): VWORLD_API_KEY, VWORLD_DOMAIN(키에 등록한 서비스 URL), RELAY_TOKEN
const crypto = require("crypto");

const LAYERS = { zone: "LT_C_UQ111", plan: "LT_C_UQ141" };
const NUM = /^-?\d{1,3}(\.\d{1,12})?$/;

function sameToken(given, expected) {
  const a = crypto.createHash("sha256").update(String(given || "")).digest();
  const b = crypto.createHash("sha256").update(String(expected || "")).digest();
  return crypto.timingSafeEqual(a, b);
}

function send(res, status, obj, extraHeaders) {
  res.statusCode = status;
  res.setHeader("content-type", "application/json; charset=utf-8");
  res.setHeader("cache-control", "no-store");
  for (const [k, v] of Object.entries(extraHeaders || {})) res.setHeader(k, v);
  res.end(JSON.stringify(obj));
}

function mask(text) {
  return String(text)
    .replace(/[A-Fa-f0-9]{8}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{12}/g, "<KEY>")
    .slice(0, 120);
}

async function upstream(url, ms) {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), ms);
  try {
    return await fetch(url, { signal: ctl.signal, headers: { "user-agent": "building-law-checker-relay/1" } });
  } finally {
    clearTimeout(t);
  }
}

module.exports = async (req, res) => {
  const key = process.env.VWORLD_API_KEY;
  const domain = process.env.VWORLD_DOMAIN;
  const token = process.env.RELAY_TOKEN;
  const region = process.env.VERCEL_REGION || "unknown";
  const meta = { "x-relay-region": region };
  if (!key || !domain || !token) return send(res, 500, { error: "relay_not_configured" }, meta);
  if (!sameToken(req.headers["x-relay-token"], token)) return send(res, 401, { error: "unauthorized" }, meta);

  const q = req.query || Object.fromEntries(new URL(req.url, "http://x").searchParams);
  const action = String(q.action || "");
  let url;
  if (action === "geocode" || action === "diag") {
    const address = action === "diag" ? "대전광역시 서구 둔산로 100" : String(q.address || "").trim();
    const type = action === "diag" ? "road" : String(q.type || "");
    if (!address || address.length > 200) return send(res, 400, { error: "bad_address" }, meta);
    if (type !== "parcel" && type !== "road") return send(res, 400, { error: "bad_type" }, meta);
    const p = new URLSearchParams({ service: "address", request: "getcoord", key, domain, address, type, format: "json" });
    url = "https://api.vworld.kr/req/address?" + p.toString();
  } else if (LAYERS[action]) {
    const x = String(q.x || ""), y = String(q.y || "");
    if (!NUM.test(x) || !NUM.test(y)) return send(res, 400, { error: "bad_point" }, meta);
    if (+x < 124 || +x > 132 || +y < 33 || +y > 39) return send(res, 400, { error: "point_out_of_korea" }, meta);
    const p = new URLSearchParams({
      service: "data", request: "GetFeature", data: LAYERS[action], key, domain,
      geomFilter: `POINT(${x} ${y})`, geometry: "false", attribute: "true", format: "json", size: "10",
    });
    url = "https://api.vworld.kr/req/data?" + p.toString();
  } else {
    return send(res, 400, { error: "bad_action" }, meta);
  }

  try {
    const r = await upstream(url, 12000);
    const body = await r.text();
    if (action === "diag") {
      return send(res, 200, { region, upstream_status: r.status, upstream_content_type: r.headers.get("content-type"),
        upstream_body_head: mask(body) }, meta);
    }
    res.statusCode = 200;
    res.setHeader("content-type", "application/json; charset=utf-8");
    res.setHeader("cache-control", "no-store");
    res.setHeader("x-relay-region", region);
    res.setHeader("x-upstream-status", String(r.status));
    // VWorld 응답이 JSON 이 아니면(차단 안내 등) 본문 앞부분을 오류로 감싸 돌려준다.
    try {
      JSON.parse(body);
      return res.end(body);
    } catch (_) {
      return send(res, 502, { error: "upstream_non_json", upstream_status: r.status, head: mask(body) }, meta);
    }
  } catch (e) {
    const code = (e && e.cause && e.cause.code) || (e && e.name) || "error";
    return send(res, 502, { error: "upstream_failed", detail: String(code) }, meta);
  }
};
