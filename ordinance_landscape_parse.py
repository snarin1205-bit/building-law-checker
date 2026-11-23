"""건축 조례의 '대지의 조경' 조문에서 연면적 구간별 조경면적 비율을 읽고, '공개공지' 조문 블록을 잘라낸다 (네트워크 없음).

읽은 구간이 연면적 전체를 빈틈없이 덮지 못하면 값을 만들지 않는다(status != 'ok').
공개공지는 도시마다 대상 용도·비율 구조가 달라 계산하지 않고 조문 원문 블록만 보관한다.
"""
import re

_NEXT = re.compile(r"^제\d+조(?:의\d+)?\s*\(", re.M)
_LAND_TITLE = re.compile(r"^제\d+조(?:의\d+)?\s*\([^)\n]*(?:대지\s*안의\s*조경|대지의\s*조경|조경면적)[^)\n]*\)", re.M)
_OPEN_TITLE = re.compile(r"^제\d+조(?:의\d+)?\s*\([^)\n]*공개\s*공지[^)\n]*\)", re.M)
_NUM = r"(\d+\s*만\s*\d*\s*천?\s*\d*|\d+\s*천\s*\d*|\d[\d,]*)"
_PCT = r"대지면적의\s*(?:100분의\s*(\d+)|(\d+)\s*퍼\s*센트)"
_BAND = re.compile(r"연면적.*?" + _NUM + r"\s*제곱미터\s*이상\s*" + _NUM + r"\s*제곱미터\s*미만(?:인)?\s*건축물\s*[:：]\s*" + _PCT)
_GE = re.compile(r"연면적.*?" + _NUM + r"\s*제곱미터\s*이상(?:인)?\s*건축물\s*[:：]\s*" + _PCT)
_LT = re.compile(r"연면적.*?" + _NUM + r"\s*제곱미터\s*미만(?:인)?\s*건축물\s*[:：]\s*" + _PCT)


def kn(s):
    """'2천', '1천500', '1만', '300', '1,000' → 정수."""
    s = s.replace(",", "").replace(" ", "")
    m = re.match(r"(?:(\d+)만)?(?:(\d+)천)?(\d+)?$", s)
    if not m or not any(m.groups()):
        raise ValueError(s)
    a, b, c = m.groups()
    return (int(a) if a else 0) * 10000 + (int(b) if b else 0) * 1000 + (int(c) if c else 0)


def _block(text, rx, must=()):
    for m in rx.finditer(text):
        nxt = _NEXT.search(text, m.end())
        blk = text[m.start(): nxt.start() if nxt else m.start() + 3000]
        if all(w in blk for w in must):
            return blk
    return None


def find_landscape_article(text):
    return _block(text, _LAND_TITLE, must=("연면적", "대지면적의"))


def find_open_space_article(text):
    return _block(text, _OPEN_TITLE)


def _paragraph1(block):
    i = block.find("①")
    if i < 0:
        return None
    j = block.find("②", i + 1)
    return block[i: j if j > 0 else len(block)]


def parse_landscape(text):
    """반환: {found, title, status, tiers, special_notes, block}. tiers: 연면적 오름차순
    [{'kind':'lt','max':1000,'pct':5}, {'kind':'band','lo':1000,'hi':2000,'pct':10}, {'kind':'ge','min':2000,'pct':15}]"""
    block = find_landscape_article(text)
    if not block:
        return {"found": False, "status": "no-article", "tiers": [], "special_notes": []}
    title = re.match(r"^제\d+조(?:의\d+)?\s*\([^)\n]*\)", block).group(0)
    p1 = _paragraph1(block)
    if not p1:
        return {"found": True, "title": title, "status": "no-paragraph", "tiers": [], "special_notes": [], "block": block}
    tiers, notes = [], []
    for line in p1.splitlines():
        l = re.sub(r"^[①\s]+", "", line.strip())
        l = re.sub(r"^\d+\.\s*", "", l)
        if not l or "삭제" in l:
            continue
        m = _BAND.search(l)
        if m:
            tiers.append({"kind": "band", "lo": kn(m.group(1)), "hi": kn(m.group(2)), "pct": int(m.group(3) or m.group(4))})
            if "다만" in l:
                notes.append(l[l.index("다만"):][:220])  # 구간 줄 안의 단서(예: 세종 예정지역 산식)
            continue
        m = _GE.search(l)
        if m:
            tiers.append({"kind": "ge", "min": kn(m.group(1)), "pct": int(m.group(2) or m.group(3))})
            if "다만" in l:
                notes.append(l[l.index("다만"):][:220])
            continue
        m = _LT.search(l)
        if m:
            tiers.append({"kind": "lt", "max": kn(m.group(1)), "pct": int(m.group(2) or m.group(3))})
            if "다만" in l:
                notes.append(l[l.index("다만"):][:220])
            continue
        if ("대지면적" in l or "퍼센트" in l) and "법 제42조" not in l and "조경면적" not in l[:6]:
            notes.append(l[:220])  # 구간 외 특례(예: 서울 학교이적지 30%, 울산 개발제한구역 5%)
    order = {"lt": 0, "band": 1, "ge": 2}
    tiers = sorted({repr(t): t for t in tiers}.values(), key=lambda t: order[t["kind"]])
    return {"found": True, "title": title, "status": "ok" if _valid(tiers) else "tiers-not-contiguous",
            "tiers": tiers, "special_notes": notes, "block": block}


def _valid(tiers):
    kinds = [t["kind"] for t in tiers]
    if kinds != ["lt", "band", "ge"]:
        return False
    return tiers[0]["max"] == tiers[1]["lo"] and tiers[1]["hi"] == tiers[2]["min"]


def pct_at(tiers, floor_area):
    """연면적(㎡)에 대한 조경면적 비율(%). 유효하지 않으면 None."""
    if not _valid(tiers):
        return None
    if floor_area < tiers[0]["max"]:
        return tiers[0]["pct"]
    if floor_area < tiers[1]["hi"]:
        return tiers[1]["pct"]
    return tiers[2]["pct"]
