"""법령·조례 개정 감지 (네트워크 필요, CI에서는 실행하지 않음).

저장된 원문 사본의 공포번호·시행일과 법제처 프록시의 현행 값을 비교한다.
달라지면 코드의 기준값을 자동으로 바꾸지 않고 '재검토 필요'로 알린다.

사용: python law_sync.py          (환경변수 LAW_PROXY_URL 로 프록시 주소 지정 가능)
종료코드: 0 변경 없음, 1 변경/미확인 있음
"""
import os
import re
import sys
import urllib.parse
import urllib.request

from ordinance_daejeon import DJ_META

DEFAULT_PROXY = "https://law-proxy-nine.vercel.app/api/law"

# 국가 법령 기대값 (data/law_snapshots/ 사본 기준)
NATIONAL = [
    {"name": "주차장법 시행령", "kind": "law", "promulgation_no": "36623", "effective": "2026-08-28",
     "queries": ["주차장법 시행령"]},
    {"name": "건축법 시행령", "kind": "law", "promulgation_no": "36817", "effective": "2026-11-12",
     "queries": ["건축법 시행령"]},
    # 건축법 제61조는 시행 전 개정본(조문시행일 2027-02-12)만 확보 — 법 자체의 현행 공포번호만 감시
    {"name": "건축법", "kind": "law", "promulgation_no": "21880", "effective": "2026-11-12",
     "queries": ["건축법"]},
]

_ORDIN_QUERIES = {"parking": ["주차장 조례", "주차장"]}


def sources():
    out = list(NATIONAL)
    for key, m in DJ_META.items():
        out.append({"name": m["name"], "kind": "ordin", "org": m["org"],
                    "promulgation_no": m["promulgation_no"], "effective": m["effective"],
                    "queries": _ORDIN_QUERIES.get(key, [m["name"]])})
    return out


def _http_fetch(params, base=None):
    url = (base or os.environ.get("LAW_PROXY_URL") or DEFAULT_PROXY) + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def _field(block, tag):
    m = re.search(rf"<{tag}[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{tag}>", block, re.S)
    return m.group(1).strip() if m else ""


def _date(s):
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 else s


def find_current(src, fetch=_http_fetch):
    """프록시 검색 결과에서 이름(·기관)이 정확히 일치하는 행의 (공포번호, 시행일) 반환."""
    endpoint = "lawSearchList" if src["kind"] == "law" else "ordinSearchList"
    name_tag = "법령명한글" if src["kind"] == "law" else "자치법규명"
    for q in src["queries"]:
        for page in range(1, 6):
            params = {"endpoint": endpoint, "query": q, "numOfRows": "50", "pageNo": str(page)}
            if src["kind"] == "law":
                params["target"] = "law"
            xml = fetch(params)
            rows = re.findall(r"<law id.*?</law>", xml, re.S)
            if not rows:
                break
            for b in rows:
                if _field(b, name_tag) != src["name"]:
                    continue
                if src["kind"] == "ordin" and _field(b, "지자체기관명") != src["org"]:
                    continue
                return {"promulgation_no": _field(b, "공포번호"), "effective": _date(_field(b, "시행일자"))}
    return None


def check_drift(fetch=_http_fetch):
    results = []
    for s in sources():
        try:
            cur = find_current(s, fetch)
        except Exception as e:  # 네트워크 오류는 '확인 못 함'으로 보고
            results.append({"name": s["name"], "status": "ERROR", "detail": str(e)[:120]})
            continue
        if cur is None:
            results.append({"name": s["name"], "status": "NOT_FOUND"})
        elif (cur["promulgation_no"], cur["effective"]) == (s["promulgation_no"], s["effective"]):
            results.append({"name": s["name"], "status": "OK"})
        else:
            results.append({"name": s["name"], "status": "CHANGED",
                            "expected": f'공포 {s["promulgation_no"]} / 시행 {s["effective"]}',
                            "found": f'공포 {cur["promulgation_no"]} / 시행 {cur["effective"]}'})
    return results


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    res = check_drift()
    bad = 0
    for r in res:
        extra = f' 기대 {r["expected"]} → 현행 {r["found"]}' if r["status"] == "CHANGED" else r.get("detail", "")
        print(f'[{r["status"]:9}] {r["name"]}{(" " + extra) if extra else ""}')
        bad += r["status"] != "OK"
    if bad:
        print("\n※ 변경·미확인 항목은 기준값을 자동으로 바꾸지 않았습니다. 원문을 확인한 뒤 사본과 코드를 갱신하세요.")
    sys.exit(1 if bad else 0)
