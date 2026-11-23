"""VWorld 데이터 조회 클라이언트 — 오류를 삼키지 않고 상태를 돌려준다.

기존 building_law_checker.get_land_use/get_district_plan 은 모든 예외를 빈 목록으로 바꿔
'조회 실패'와 '해당 없음'을 구분하지 못했고, 인증키의 서비스 URL 제한(domain 파라미터)을 보내지 않아
INCORRECT_KEY 가 조용히 '미확인'이 되었다. 지구단위계획은 LT_C_UQ141 레이어이다(LT_C_UQ112 는 다른 레이어).

환경변수
  VWORLD_API_KEY / VWORLD_DOMAIN   직접 호출용(국내 IP). 키에 등록한 서비스 URL 이 VWORLD_DOMAIN.
  VWORLD_RELAY_URL / VWORLD_RELAY_TOKEN   중계 함수(api/vworld.js, 서울 리전) 사용. 설정되면 중계가 우선이며
                                          이때 앱에는 VWorld 키가 필요 없다(키는 중계 쪽 환경변수에만 있음).
해외 서버(Streamlit Cloud 등)에서는 VWorld 직접 호출이 막혀 중계를 쓴다.
"""
import os
import re
import time

LAYER_ZONE = "LT_C_UQ111"           # 용도지역(도시지역)
LAYER_DISTRICT_PLAN = "LT_C_UQ141"  # 지구단위계획구역
DATA_URL = "https://api.vworld.kr/req/data"
ADDRESS_URL = "https://api.vworld.kr/req/address"
NON_RETRY_CODES = {"INCORRECT_KEY", "INVALID_KEY", "UNAVAILABLE_KEY", "OVER_REQUEST_LIMIT"}
_KEY_RE = re.compile(r"[A-Fa-f0-9]{8}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{12}")


def _config(key=None, domain=None):
    return key or os.getenv("VWORLD_API_KEY", ""), domain or os.getenv("VWORLD_DOMAIN", "localhost:8501")


def relay_configured():
    return bool(os.getenv("VWORLD_RELAY_URL") and os.getenv("VWORLD_RELAY_TOKEN"))


def _snippet(text, n=80):
    return _KEY_RE.sub("<KEY>", " ".join(str(text).split()))[:n]


def make_relay_getter(url, token, http_get=None):
    """VWorld 직접 호출 인터페이스(getter(url, params, timeout))를 중계 호출로 바꿔준다."""
    def getter(target_url, params=None, timeout=None):
        get = http_get
        if get is None:
            import requests
            get = requests.get
        params = params or {}
        if target_url == ADDRESS_URL:
            rp = {"action": "geocode", "address": params.get("address", ""), "type": params.get("type", "")}
        elif target_url == DATA_URL:
            layer = params.get("data")
            action = {LAYER_ZONE: "zone", LAYER_DISTRICT_PLAN: "plan"}.get(layer)
            if not action:
                raise ValueError(f"중계가 허용하지 않는 레이어: {layer}")
            m = re.match(r"POINT\(([-\d.]+) ([-\d.]+)\)", params.get("geomFilter", ""))
            if not m:
                raise ValueError("좌표 형식 오류")
            rp = {"action": action, "x": m.group(1), "y": m.group(2)}
        else:
            raise ValueError("알 수 없는 호출 대상")
        return get(url, params=rp, headers={"x-relay-token": token}, timeout=timeout)
    return getter


def _default_getter(getter):
    if getter is not None:
        return getter
    if relay_configured():
        return make_relay_getter(os.environ["VWORLD_RELAY_URL"], os.environ["VWORLD_RELAY_TOKEN"])
    import requests
    return requests.get


def _response(r):
    """응답에서 VWorld 'response' 딕셔너리를 꺼낸다. 비JSON·중계 오류는 원인을 담은 예외로 올린다(키 마스킹)."""
    try:
        body = r.json()
    except Exception:
        status = getattr(r, "status_code", "?")
        text = getattr(r, "text", "")
        raise ValueError(f"비JSON 응답 HTTP {status} '{_snippet(text)}'")
    if isinstance(body, dict) and "response" in body:
        return body["response"]
    if isinstance(body, dict) and "error" in body:  # 중계 함수의 오류 응답
        extra = body.get("detail") or body.get("upstream_status") or ""
        raise ValueError(f"중계 오류 {body['error']} {extra} {_snippet(body.get('head', ''), 60)}".strip())
    raise ValueError(f"예상하지 못한 응답 형식 '{_snippet(body)}'")


def _fail_msg(prefix, e):
    if isinstance(e, ValueError):
        return f"{prefix}{_snippet(str(e), 140)}"
    return f"{prefix}응답 처리 실패({type(e).__name__})"


def query_layer(layer, x, y, key=None, domain=None, getter=None, retries=2, sleep=1.0):
    """반환: {"status": "OK"|"NOT_FOUND"|"ERROR", "names": [...], "error": str|None}
    OK 는 feature 가 있다는 뜻, NOT_FOUND 는 조회는 성공했으나 해당 지점에 feature 가 없다는 뜻이다
    (법적 '비적용' 확정이 아님). ERROR 는 조회 자체가 실패한 것이며 오류 메시지에 키는 포함하지 않는다."""
    key, domain = _config(key, domain)
    if not key and not relay_configured():
        return {"status": "ERROR", "names": [], "error": "VWORLD_API_KEY 미설정(중계도 미설정)"}
    getter = _default_getter(getter)
    params = {"service": "data", "request": "GetFeature", "data": layer, "key": key, "domain": domain,
              "geomFilter": f"POINT({x} {y})", "geometry": "false", "attribute": "true",
              "format": "json", "size": "10"}
    last = "알 수 없는 오류"
    for attempt in range(retries + 1):
        try:
            resp = _response(getter(DATA_URL, params=params, timeout=20))
        except Exception as e:  # 네트워크 오류·비JSON: 재시도
            last = _fail_msg("", e)
            if attempt < retries:
                time.sleep(sleep)
            continue
        status = resp.get("status")
        if status == "OK":
            feats = resp["result"]["featureCollection"]["features"]
            names = []
            for f in feats:
                n = (f.get("properties") or {}).get("uname", "")
                if n and n not in names:
                    names.append(n)
            return {"status": "OK", "names": names, "error": None}
        if status == "NOT_FOUND":
            return {"status": "NOT_FOUND", "names": [], "error": None}
        err = resp.get("error") or {}
        code = str(err.get("code", status))
        last = f"VWorld 오류 {code}"
        if code in NON_RETRY_CODES:
            break
        if attempt < retries:
            time.sleep(sleep)
    return {"status": "ERROR", "names": [], "error": last}


def lookup_zones(x, y, **kw):
    return query_layer(LAYER_ZONE, x, y, **kw)


def lookup_district_plan(x, y, **kw):
    """지구단위계획구역 조회. 이 레이어는 토지거래허가구역 등 다른 구역도 섞어 돌려주므로 '지구단위계획'이 든 이름만 인정한다."""
    r = query_layer(LAYER_DISTRICT_PLAN, x, y, **kw)
    if r["status"] == "OK":
        names = [n for n in r["names"] if "지구단위계획" in n]
        if not names:
            return {"status": "NOT_FOUND", "names": [], "error": None}
        return {**r, "names": names}
    return r


def geocode(address, key=None, domain=None, getter=None, retries=2, sleep=1.0, timeout=20):
    """주소 → 좌표. 지번(parcel) → 도로명(road) 순으로 시도한다.

    반환: {"status": "OK"|"NOT_FOUND"|"ERROR", "x": float|None, "y": float|None, "type": str|None, "error": str|None}
    ERROR 는 어느 유형에서든 조회 자체가 실패한 경우(오류 코드·예외명·응답 앞부분 포함, 키는 포함하지 않음).
    모든 유형이 NOT_FOUND 이면 NOT_FOUND."""
    key, domain = _config(key, domain)
    if not (address or "").strip():
        return {"status": "NOT_FOUND", "x": None, "y": None, "type": None, "error": None}
    if not key and not relay_configured():
        return {"status": "ERROR", "x": None, "y": None, "type": None, "error": "VWORLD_API_KEY 미설정(중계도 미설정)"}
    getter = _default_getter(getter)
    errors = []
    for addr_type in ("parcel", "road"):
        params = {"service": "address", "request": "getcoord", "key": key, "domain": domain,
                  "address": address.strip(), "type": addr_type, "format": "json"}
        last = None
        for attempt in range(retries + 1):
            try:
                resp = _response(getter(ADDRESS_URL, params=params, timeout=timeout))
            except Exception as e:
                last = _fail_msg(f"{addr_type}: ", e)
                if attempt < retries:
                    time.sleep(sleep)
                continue
            status = resp.get("status")
            if status == "OK":
                pt = resp["result"]["point"]
                return {"status": "OK", "x": float(pt["x"]), "y": float(pt["y"]), "type": addr_type, "error": None}
            if status == "NOT_FOUND":
                last = None
                break
            code = str((resp.get("error") or {}).get("code", status))
            last = f"{addr_type}: VWorld 오류 {code}"
            if code in NON_RETRY_CODES:
                break
            if attempt < retries:
                time.sleep(sleep)
        if last:
            errors.append(last)
    if errors:
        return {"status": "ERROR", "x": None, "y": None, "type": None, "error": "; ".join(errors)}
    return {"status": "NOT_FOUND", "x": None, "y": None, "type": None, "error": None}


LAYER_PARCEL = "LP_PA_CBND_BUBUN"   # 연속지적도(필지)
LAYER_GREENBELT = "LT_C_UD801"      # 개발제한구역
NED_URL = "https://api.vworld.kr/ned/data/getLandCharacteristics"


def _num(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def lookup_parcel(x, y, key=None, domain=None, getter=None, retries=2, sleep=1.0):
    """좌표 → 필지(PNU·지번 주소·공시지가). 반환 {"status","pnu","addr","jiga","error"}."""
    key, domain = _config(key, domain)
    out = {"status": "ERROR", "pnu": None, "addr": None, "jiga": None, "error": None}
    if not key and not relay_configured():
        out["error"] = "VWORLD_API_KEY 미설정(중계도 미설정)"
        return out
    getter = _default_getter(getter)
    params = {"service": "data", "request": "GetFeature", "data": LAYER_PARCEL, "key": key, "domain": domain,
              "geomFilter": f"POINT({x} {y})", "geometry": "false", "attribute": "true", "format": "json", "size": "1"}
    last = "알 수 없는 오류"
    for attempt in range(retries + 1):
        try:
            resp = _response(getter(DATA_URL, params=params, timeout=20))
        except Exception as e:
            last = _fail_msg("", e)
            if attempt < retries:
                time.sleep(sleep)
            continue
        st = resp.get("status")
        if st == "OK":
            feats = resp["result"]["featureCollection"]["features"]
            if feats:
                p = feats[0].get("properties") or {}
                return {"status": "OK", "pnu": p.get("pnu"), "addr": p.get("addr"), "jiga": _num(p.get("jiga")), "error": None}
            return {**out, "status": "NOT_FOUND"}
        if st == "NOT_FOUND":
            return {**out, "status": "NOT_FOUND"}
        code = str((resp.get("error") or {}).get("code", st))
        last = f"VWorld 오류 {code}"
        if code in NON_RETRY_CODES:
            break
        if attempt < retries:
            time.sleep(sleep)
    out["error"] = last
    return out


def lookup_land(pnu, key=None, domain=None, getter=None, retries=2, sleep=1.0):
    """PNU → 토지(임야)대장 특성: 면적(㎡)·지목·용도지역(토지이용계획 1·2순위). 최신 기준년월 1건.
    반환 {"status","area","jimok","zones","year","error"}. 면적은 대장 면적이며 건축법상 대지면적(도로 편입·공공용지 등 제외)과 다를 수 있다."""
    key, domain = _config(key, domain)
    out = {"status": "ERROR", "area": None, "jimok": None, "zones": [], "year": None, "error": None}
    if not pnu:
        return {**out, "status": "NOT_FOUND"}
    if not key:
        out["error"] = "VWORLD_API_KEY 미설정(토지특성은 중계 미지원)"
        return out
    if getter is None:
        import requests
        getter = requests.get
    params = {"key": key, "domain": domain, "pnu": pnu, "format": "json", "numOfRows": "20", "pageNo": "1"}
    last = "알 수 없는 오류"
    for attempt in range(retries + 1):
        try:
            r = getter(NED_URL, params=params, timeout=20)
            body = r.json()
        except Exception as e:
            last = _fail_msg("", e) if isinstance(e, ValueError) else f"응답 처리 실패({type(e).__name__})"
            if attempt < retries:
                time.sleep(sleep)
            continue
        fields = ((body.get("landCharacteristicss") or {}).get("field")) if isinstance(body, dict) else None
        if not fields:
            msg = (body.get("landCharacteristicss") or {}).get("resultMsg") if isinstance(body, dict) else ""
            if isinstance(body, dict) and "response" in body:
                msg = (body["response"] or {}).get("resultMsg") or msg
            if msg:
                last = f"토지특성 응답: {_snippet(msg, 80)}"
                break
            return {**out, "status": "NOT_FOUND"}
        if isinstance(fields, dict):
            fields = [fields]
        best = max(fields, key=lambda f: (str(f.get("stdrYear", "")), str(f.get("stdrMt", ""))))
        zones = []
        for k in ("prposArea1Nm", "prposArea2Nm"):
            z = (best.get(k) or "").strip()
            if z and z not in zones and z != "지정되지않음":
                zones.append(z)
        return {"status": "OK", "area": _num(best.get("lndpclAr")), "jimok": best.get("lndcgrCodeNm"), "zones": zones,
                "year": best.get("stdrYear"), "error": None}
    out["error"] = last
    return out


def lookup_greenbelt(x, y, **kw):
    """개발제한구역 여부. OK=구역 안(names 에 '개발제한구역'), NOT_FOUND=조회는 됐으나 구역 데이터 없음(법적 '구역 밖' 확정은 아님)."""
    r = query_layer(LAYER_GREENBELT, x, y, **kw)
    if r["status"] == "OK":
        names = [n for n in r["names"] if "개발제한구역" in n]
        if not names:
            return {"status": "NOT_FOUND", "names": [], "error": None}
        return {**r, "names": names}
    return r


def lookup_site(address, **kw):
    """주소 → 필지·대지면적·용도지역·지구단위계획 한 번에. 각 단계의 상태를 그대로 담는다(실패해도 앞 단계 결과는 보존)."""
    res = {"geocode": geocode(address, **kw), "parcel": None, "land": None, "zones": None, "plan": None, "greenbelt": None}
    g = res["geocode"]
    if g["status"] != "OK":
        return res
    res["parcel"] = lookup_parcel(g["x"], g["y"], **kw)
    if res["parcel"]["status"] == "OK":
        res["land"] = lookup_land(res["parcel"]["pnu"], **kw)
    res["zones"] = lookup_zones(g["x"], g["y"], **kw)
    res["plan"] = lookup_district_plan(g["x"], g["y"], **kw)
    res["greenbelt"] = lookup_greenbelt(g["x"], g["y"], **kw)
    return res
