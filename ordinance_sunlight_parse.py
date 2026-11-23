"""건축 조례의 '일조 등의 확보를 위한 건축물의 높이 제한' 조문에서 정북방향 이격거리 구간(높이별)을 읽는다 (네트워크 없음).

읽은 구간이 높이 전체를 빈틈없이 덮지 못하면 값을 만들지 않는다(status != 'ok').
"""
import re

_TITLE = re.compile(r"^제\d+조(?:의\d+)?\s*\([^)\n]*일조[^)\n]*높이[^)\n]*\)", re.M)
_NEXT_ART = re.compile(r"^제\d+조(?:의\d+)?\s*\(", re.M)
_BAND = re.compile(r"높이\s*(\d+(?:\.\d+)?)\s*미터\s*초과\s*(\d+(?:\.\d+)?)\s*미터\s*이하인?\s*부분.*?(\d+(?:\.\d+)?)\s*미터\s*이상")
_LE = re.compile(r"높이\s*(\d+(?:\.\d+)?)\s*미터\s*이하인?\s*부분.*?(\d+(?:\.\d+)?)\s*미터\s*이상")
_GT = re.compile(r"높이\s*(\d+(?:\.\d+)?)\s*미터(?:를)?\s*초과(?:하는)?\s*부분.*?높이의\s*(\d+)\s*분의\s*(\d+)\s*이상")


def find_article(text):
    m = _TITLE.search(text)
    if not m:
        return None
    nxt = _NEXT_ART.search(text, m.end())
    return text[m.start(): nxt.start() if nxt else m.start() + 4000]


def paragraph1(block):
    i = block.find("①")
    if i < 0:
        return None
    j = block.find("②", i + 1)
    return block[i: j if j > 0 else len(block)]


def parse(text):
    """반환: {found, title, status, tiers, cites, proviso, block}. tiers: 높이 상한 오름차순
    [{'kind':'le','max':10,'dist':1.5}, {'kind':'band','lo':10,'hi':17,'dist':5}, {'kind':'gt','above':17,'num':1,'den':2}]"""
    block = find_article(text)
    if not block:
        return {"found": False, "status": "no-article", "tiers": []}
    title = re.match(r"^제\d+조(?:의\d+)?\s*\(([^)\n]*)\)", block).group(0)
    p1 = paragraph1(block)
    if not p1:
        return {"found": True, "title": title, "status": "no-paragraph", "tiers": [], "block": block}
    tiers = []
    for line in p1.splitlines():
        l = line.strip()
        l = re.sub(r"^[①\s]+", "", l)
        if not l or "삭제" in l:
            continue
        m = _BAND.search(l)
        if m:
            tiers.append({"kind": "band", "lo": float(m.group(1)), "hi": float(m.group(2)), "dist": float(m.group(3))})
            continue
        m = _GT.search(l)
        if m:
            tiers.append({"kind": "gt", "above": float(m.group(1)), "num": int(m.group(3)), "den": int(m.group(2))})
            continue
        m = _LE.search(l)
        if m:
            tiers.append({"kind": "le", "max": float(m.group(1)), "dist": float(m.group(2))})
    # 중복 제거(같은 구간이 '삭제' 줄 때문에 두 번 읽히는 경우 대비)
    uniq = []
    for t in tiers:
        if t not in uniq:
            uniq.append(t)
    tiers = uniq
    cites = None
    head = p1[:300]
    if re.search(r"영\s*제86조제1항", head):
        cites = "영 제86조제1항"
    elif re.search(r"법\s*제61조", head):
        cites = "법 제61조제1항"
    proviso = ""
    pm = re.search(r"다만[^\n]*", p1)
    if pm:
        proviso = pm.group(0).strip()
    return {"found": True, "title": title, "status": "ok" if _valid(tiers) else "tiers-not-contiguous",
            "tiers": tiers, "cites": cites, "proviso": proviso, "block": block}


def _valid(tiers):
    """le → (band)* → gt 가 높이를 빈틈없이 덮는지."""
    if not tiers or tiers[0]["kind"] != "le" or tiers[-1]["kind"] != "gt":
        return False
    edge = tiers[0]["max"]
    for t in tiers[1:-1]:
        if t["kind"] != "band" or abs(t["lo"] - edge) > 1e-9:
            return False
        edge = t["hi"]
    return abs(tiers[-1]["above"] - edge) < 1e-9


def value_at(tiers, h):
    """높이 h(m) 부분의 정북 이격거리(m). tiers 가 유효하지 않으면 None."""
    if not _valid(tiers):
        return None
    for t in tiers:
        if t["kind"] == "le" and h <= t["max"]:
            return t["dist"]
        if t["kind"] == "band" and t["lo"] < h <= t["hi"]:
            return t["dist"]
        if t["kind"] == "gt" and h > t["above"]:
            return h * t["num"] / t["den"]
    return None
