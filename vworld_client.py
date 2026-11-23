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
