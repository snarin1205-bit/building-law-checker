"""VWorld 데이터 조회 클라이언트 — 오류를 삼키지 않고 상태를 돌려준다.

기존 building_law_checker.get_land_use/get_district_plan 은 모든 예외를 빈 목록으로 바꿔
'조회 실패'와 '해당 없음'을 구분하지 못했고, 인증키의 서비스 URL 제한(domain 파라미터)을 보내지 않아
INCORRECT_KEY 가 조용히 '미확인'이 되었다. 지구단위계획은 LT_C_UQ141 레이어이다(LT_C_UQ112 는 다른 레이어).

환경변수: VWORLD_API_KEY(필수), VWORLD_DOMAIN(키에 등록한 서비스 URL, 기본 localhost:8501)
"""
import os
import time

LAYER_ZONE = "LT_C_UQ111"           # 용도지역(도시지역)
LAYER_DISTRICT_PLAN = "LT_C_UQ141"  # 지구단위계획구역
DATA_URL = "https://api.vworld.kr/req/data"
NON_RETRY_CODES = {"INCORRECT_KEY", "INVALID_KEY", "UNAVAILABLE_KEY", "OVER_REQUEST_LIMIT"}


def _config(key=None, domain=None):
    return key or os.getenv("VWORLD_API_KEY", ""), domain or os.getenv("VWORLD_DOMAIN", "localhost:8501")


def query_layer(layer, x, y, key=None, domain=None, getter=None, retries=2, sleep=1.0):
    """반환: {"status": "OK"|"NOT_FOUND"|"ERROR", "names": [...], "error": str|None}
    OK 는 feature 가 있다는 뜻, NOT_FOUND 는 조회는 성공했으나 해당 지점에 feature 가 없다는 뜻이다
    (법적 '비적용' 확정이 아님). ERROR 는 조회 자체가 실패한 것이며 오류 메시지에 키는 포함하지 않는다."""
    key, domain = _config(key, domain)
    if not key:
        return {"status": "ERROR", "names": [], "error": "VWORLD_API_KEY 미설정"}
    if getter is None:
        import requests  # 지연 import: 오프라인 테스트·CI 에 requests 가 없어도 모듈을 불러올 수 있게 함
        getter = requests.get
    params = {"service": "data", "request": "GetFeature", "data": layer, "key": key, "domain": domain,
              "geomFilter": f"POINT({x} {y})", "geometry": "false", "attribute": "true",
              "format": "json", "size": "10"}
    last = "알 수 없는 오류"
    for attempt in range(retries + 1):
        try:
            r = getter(DATA_URL, params=params, timeout=20)
            resp = r.json()["response"]
        except Exception as e:  # 네트워크 오류·JSON 아님: 재시도
            last = f"응답 처리 실패({type(e).__name__})"
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
    return query_layer(LAYER_DISTRICT_PLAN, x, y, **kw)


ADDRESS_URL = "https://api.vworld.kr/req/address"


def geocode(address, key=None, domain=None, getter=None, retries=2, sleep=1.0, timeout=20):
    """주소 → 좌표. 지번(parcel) → 도로명(road) 순으로 시도한다.

    반환: {"status": "OK"|"NOT_FOUND"|"ERROR", "x": float|None, "y": float|None, "type": str|None, "error": str|None}
    ERROR 는 어느 유형에서든 조회 자체가 실패한 경우(오류 코드·예외명 포함, 키는 포함하지 않음).
    모든 유형이 NOT_FOUND 이면 NOT_FOUND."""
    key, domain = _config(key, domain)
    if not (address or "").strip():
        return {"status": "NOT_FOUND", "x": None, "y": None, "type": None, "error": None}
    if not key:
        return {"status": "ERROR", "x": None, "y": None, "type": None, "error": "VWORLD_API_KEY 미설정"}
    if getter is None:
        import requests
        getter = requests.get
    errors = []
    for addr_type in ("parcel", "road"):
        params = {"service": "address", "request": "getcoord", "key": key, "domain": domain,
                  "address": address.strip(), "type": addr_type, "format": "json"}
        last = None
        for attempt in range(retries + 1):
            try:
                r = getter(ADDRESS_URL, params=params, timeout=timeout)
                resp = r.json()["response"]
            except Exception as e:
                last = f"{addr_type}: 응답 처리 실패({type(e).__name__})"
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
