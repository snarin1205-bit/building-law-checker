"""지역별 도시계획 조례 건폐율·용적률 상한 조회 (data/ordinance_zone_limits.json 기반).

데이터는 법제처 원문에서 tools/build_ordinance_data.py 로 만든 것이며, 원문에서 읽지 못한 값은 없다(→ 미확인).
현재 연결 지역: 서울·부산·대구·인천·광주·대전·울산·세종(광역시·특별시의 도시계획 조례). 그 밖의 지역은 '미연결'.
"""
import json
import pathlib

DATA_FILE = pathlib.Path(__file__).resolve().parent / "data" / "ordinance_zone_limits.json"

# 주소 앞부분 → 지역 키
_PREFIXES = (
    ("서울특별시", "서울특별시"), ("서울", "서울특별시"),
    ("부산광역시", "부산광역시"), ("부산", "부산광역시"),
    ("대구광역시", "대구광역시"), ("대구", "대구광역시"),
    ("인천광역시", "인천광역시"), ("인천", "인천광역시"),
    ("광주광역시", "광주광역시"), ("광주 ", "광주광역시"),  # '광주시'(경기도)와 구분
    ("대전광역시", "대전광역시"), ("대전", "대전광역시"),
    ("울산광역시", "울산광역시"), ("울산", "울산광역시"),
    ("세종특별자치시", "세종특별자치시"), ("세종", "세종특별자치시"),
)
# 광역시 안의 군: 군 자체 도시계획 조례가 따로 있을 수 있다(미확인)
COUNTIES = ("기장군", "달성군", "군위군", "울주군", "강화군", "옹진군")

CAVEATS = (
    "상한값(이하)이며 확정 허용치가 아님. 지구단위계획·정비구역·시장정비사업구역·경제자유구역·성장관리계획구역·"
    "도시계획시설·상업지역 복합 공동주택 등 특례와 용도지구·구역별 별도 비율은 같은 조례의 다른 조항이 정함",
    "필지가 둘 이상의 용도지역에 걸치거나 용도지구·구역이 겹치면 면적·위치별로 따로 검토",
)

_cache = None


def load():
    global _cache
    if _cache is None:
        _cache = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return _cache


def region_of(address):
    a = (address or "").strip()
    for prefix, key in _PREFIXES:
        if a.startswith(prefix):
            return key
    return None


def county_in(address):
    return next((c for c in COUNTIES if c in (address or "")), None)


def _nospace(s):
    return "".join(str(s).split())


def zone_limits_for(address, zone_names):
    """주소의 지역 조례 기준 건폐율·용적률 상한. 매칭·읽기 실패는 '미확인'으로 남기고 추정하지 않는다.

    반환 status: NO_REGION(주소 지역 미연결) | UNKNOWN(용도지역 없음) | PARTIAL(일부 미확인) | OK"""
    region = region_of(address)
    if not region:
        return {"status": "NO_REGION", "region": None, "matches": [], "unmatched": list(zone_names or []),
                "overlap": False, "caveats": list(CAVEATS), "law": None, "notes": []}
    r = load()["regions"].get(region)
    if not r:
        return {"status": "NO_REGION", "region": region, "matches": [], "unmatched": list(zone_names or []),
                "overlap": False, "caveats": list(CAVEATS), "law": None, "notes": []}
    matches, unmatched, incomplete = [], [], False
    for z in zone_names or []:
        k = _nospace(z)
        if not k:
            continue
        info = r["zones"].get(k)
        if info is None:
            unmatched.append(z)
            continue
        if info["coverage"] is None or info["far"] is None:
            incomplete = True
        note = "; ".join(x for x in (
            f"건폐율: {info['coverage_note']}" if info.get("coverage_note") else "",
            f"용적률: {info['far_note']}" if info.get("far_note") else "") if x)
        matches.append({"zone": z, "coverage_max_pct": info["coverage"], "far_max_pct": info["far"], "note": note})
    notes = []
    c = county_in(address)
    if c:
        notes.append(f"{c}은 군 자체 도시계획 조례가 따로 있을 수 있어 이 광역 조례 값이 적용되는지 확인되지 않음")
    if region == "광주광역시":
        notes.append("조례 기관이 '(구)광주광역시'로 표시됨 — 전남광주통합특별시 출범(2026-07-01) 이후 이 조례의 승계·개정 여부 미확인")
    status = "UNKNOWN" if not matches else ("PARTIAL" if (unmatched or incomplete) else "OK")
    return {"status": status, "region": region, "matches": matches, "unmatched": unmatched,
            "overlap": len(matches) + len(unmatched) > 1, "caveats": list(CAVEATS),
            "law": r["ordinance"], "notes": notes}
