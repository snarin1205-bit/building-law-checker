"""지역별 주차장 조례(광역시·특별시 8곳)의 부설주차장 설치기준 계산 (data/parking_ordinances.json 기반).

데이터는 법제처 원문 별표에서 tools/build_parking_data.py 로 만든 것이다. 자동 계산은 단순·명확한 분류(면적·단위·단독주택 구간식)만 하고,
공동주택·오피스텔 등 별도 규정을 인용하거나 복잡한 분류는 manual 로 원문 텍스트를 그대로 보여주며 계산하지 않는다.
끝수 처리는 law_core_v2.parking_required 의 주차장법 시행령 별표 1 비고(0.5 이상 1대) 로직을 쓴다.
"""
import json
import pathlib
from fractions import Fraction

from law_core_v2 import parking_required

DATA_FILE = pathlib.Path(__file__).resolve().parent / "data" / "parking_ordinances.json"
_cache = None


def load():
    global _cache
    if _cache is None:
        _cache = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return _cache


def region_data(region):
    return load()["regions"].get(region)


def _frac(x):
    return Fraction(str(x))


def _detached_fn(upper, step):
    def f(area):
        if area <= 50:
            return area / 100  # 영 별표 1 비고 4 단서(50㎡ 이하 면적÷100㎡) — 아래 notes 에 근거 표시
        if area <= upper:
            return Fraction(1)
        return 1 + (area - upper) / step
    return f


def build(region, variant=0):
    """지역 데이터 → (rules, manual, special, display) — parking_required 입력. variant: 열 번호(없으면 0)."""
    r = region_data(region)
    if not r:
        return None
    ncols = max(1, len(r["columns"]))
    vi = min(max(0, variant), ncols - 1)
    rules, manual, special, display = {}, {}, {}, {}
    for c in r["categories"]:
        cid, no, label = c["id"], c["no"], c["label"]
        if c["kind"] == "manual":
            manual[cid] = f"{no}. {label}"
            display[cid] = f"{no}. {label} — 원문 표 참조(자동 계산 안 함)"
        elif c["kind"] == "detached":
            rules[cid] = (no, label, "시설면적㎡", None, None)
            special[cid] = _detached_fn(c["upper"], c["step"])
            display[cid] = f"{no}. {label}"
        else:
            for rule in c["rules"]:
                key = cid if len(c["rules"]) == 1 and not rule["sublabel"] else f"{cid}:{rule['sublabel'] or ''}"
                v = rule["values"][vi]
                sub = f" — {rule['sublabel']}" if rule["sublabel"] else ""
                rules[key] = (no, label + sub, rule["unit"], _frac(v["mult"]), _frac(v["div"]))
                display[key] = f"{no}. {label}{sub}"
    return rules, manual, special, display


def parking_required_region(region, items, variant=0):
    """items: [(키, 수량)] — 키는 build() 의 display 키. 미연결 지역·수동 분류는 UNKNOWN."""
    r = region_data(region)
    if not r:
        return {"status": "UNKNOWN", "reason": f"{region} 주차장 조례 데이터 미연결"}
    rules, manual, special, display = build(region, variant)
    notes = []
    ncols = len(r["columns"])
    if ncols:
        vi = min(max(0, variant), ncols - 1)
        notes.append(f"조례 표의 열 구분: 적용 열 = {r['columns'][vi]} (다른 열은 값이 다름 — 대지의 구역에 맞는 열인지 확인)")
    used = {k for k, _ in items}
    for c in r["categories"]:
        base_used = any(k == c["id"] or k.startswith(c["id"] + ":") for k in used)
        if base_used and c.get("exception_note"):
            notes.append(f"{c['no']}호 예외 규정(원문): {c['exception_note']} — 이 계산에는 반영하지 않음")
        if base_used and c["kind"] == "detached":
            notes.append("단독주택 시설면적 50㎡ 이하: 영 별표 1 비고 4 단서(면적÷100㎡) 적용" +
                         ("(조례 별표 비고에도 같은 단서가 있음)" if r.get("small_house_rule") else
                          "(조례 별표에 이 단서가 없어 영 별표 1 비고를 준용한 것 — 해석 확인 필요)"))
    if r["related_annexes"]:
        notes.append("이 조례에는 설치제한지역·특수지역 등 별도 별표가 있음 — 해당 지역이면 별도 확인: " + "; ".join(r["related_annexes"]))
    if not r.get("rounding_half_rule"):
        notes.append("끝수 처리: 조례 별표에 비고가 없거나 일부만 있어 주차장법 시행령 별표 1 비고(0.5 이상 1대)를 적용")
    return parking_required(items, None, rules=rules, manual=manual, undefined=None,
                            law_meta=r["ordinance"], notes=notes, special=special)
