"""도시계획 조례 원문 텍스트에서 용도지역별 건폐율·용적률을 읽는 파서 (네트워크 없음).

규칙: 원문에서 읽은 값만 돌려준다. 읽지 못한 용도지역은 결과에 넣지 않는다(→ 호출 쪽에서 '미확인').
조문의 단서(괄호, '다만' 이하 등)는 note 로 함께 돌려준다.
"""
import re

CANON_ZONES = (
    "제1종전용주거지역", "제2종전용주거지역", "제1종일반주거지역", "제2종일반주거지역", "제3종일반주거지역",
    "준주거지역", "중심상업지역", "일반상업지역", "근린상업지역", "유통상업지역",
    "전용공업지역", "일반공업지역", "준공업지역", "보전녹지지역", "생산녹지지역", "자연녹지지역",
    "보전관리지역", "생산관리지역", "계획관리지역", "농림지역", "자연환경보전지역",
)
_CANON = set(CANON_ZONES)


def nospace(s):
    return re.sub(r"\s+", "", s)


def _int(s):
    return int(s.replace(",", ""))


# 비율 표기: '100분의 60' / '1천300퍼센트' / '1천 퍼센트' / '1,300퍼센트' / '60퍼센트' / '60%'
_PCT = re.compile(
    r"(?:100분의\s*(?P<q>[\d,]+))"
    r"|(?:(?P<k>\d+)\s*천\s*(?P<r>[\d,]*)\s*(?:퍼센트|%))"
    r"|(?:(?P<p>[\d,]+)\s*(?:퍼센트|%))")


def parse_pct(rest):
    """문자열 앞쪽의 첫 비율을 (정수, 그 뒤 문자열)로. 없으면 (None, rest)."""
    m = _PCT.search(rest)
    if not m:
        return None, rest
    if m.group("q"):
        v = _int(m.group("q"))
    elif m.group("k"):
        v = int(m.group("k")) * 1000 + (_int(m.group("r")) if m.group("r") else 0)
    else:
        v = _int(m.group("p"))
    return v, rest[m.end():]


_ROW = re.compile(r"^\s*\d+\.\s*([^:：\n]+?)\s*[:：]\s*(.+)$", re.M)


def article_block(txt, kind):
    """'제N조(…용도지역 (안|내)에서의 건폐율|용적률…)' 조문의 ① 항 블록."""
    pat = re.compile(r"^제\d+조(?:의\d+)?\((?:[^)]*?)용도지역\s*(?:안|내)?\s*에서의\s*" + kind + r"[^)]*\)", re.M)
    m = pat.search(txt)
    if not m:
        m = _relaxed_heading(txt, kind)   # 제목 형식이 다른 조례(괄호 앞 공백, '용도지역ㆍ지구 등에서의' 등)
    if not m:
        return None
    blk = txt[m.end():m.end() + 6000]
    cut = len(blk)
    for stop in (re.search(r"^②", blk, re.M), re.search(r"^제\d+조", blk, re.M)):
        if stop:
            cut = min(cut, stop.start())
    return txt[m.start():m.end()] + blk[:cut]


_BAD_TITLE = ("완화", "강화", "특례", "성장관리", "지구단위", "경제자유", "기존", "공장", "농지", "방화", "경관", "그 밖")


def _relaxed_heading(txt, kind):
    """엄격한 패턴이 실패했을 때: 한 줄짜리 조문 제목에 kind 와 '지역'(용도지역·용도구역ㆍ지역ㆍ지구 등)이 있고 완화·특례 조문이 아닌 것 중
    본문에 '용도지역: 비율' 행이 가장 많이 읽히는 조문. 행이 하나도 없으면 None."""
    best, best_n = None, 0
    for m in re.finditer(r"^제\d+조(?:의\d+)?\s*\(([^)\n]*)\)", txt, re.M):
        title = m.group(1)
        if kind not in title or "지역" not in title or any(b in title for b in _BAD_TITLE):
            continue
        blk = txt[m.end():m.end() + 6000]
        cut = len(blk)
        for stop in (re.search(r"^②", blk, re.M), re.search(r"^제\d+조", blk, re.M)):
            if stop:
                cut = min(cut, stop.start())
        n = sum(1 for name, rest in _ROW.findall(blk[:cut]) if nospace(name) in _CANON and parse_pct(rest)[0] is not None)
        if n > best_n:
            best, best_n = m, n
    return best


def parse_list(text):
    """별표 본문(hwp 추출 텍스트 등)의 'N. 용도지역 : 비율' 목록 → ({용도지역: %}, {용도지역: 단서}). 표준 21개 용도지역만, 첫 값 사용."""
    vals, notes = {}, {}
    for name, rest in _ROW.findall(text or ""):
        n = nospace(name)
        if n not in _CANON or n in vals:
            continue
        v, tail = parse_pct(rest)
        if v is None:
            continue
        vals[n] = v
        note = _clean_note(tail)
        if note:
            notes[n] = note
    return vals, notes


def _clean_note(s):
    s = s.strip()
    s = re.sub(r"^이하\s*", "", s).strip()
    return s.strip(" .")


def parse_article(txt, kind):
    """kind: '건폐율' | '용적률' → ({정규화된 용도지역명: 정수%}, {용도지역명: 조문 단서}) (표준 21개 용도지역만)."""
    b = article_block(txt, kind)
    if not b:
        return {}, {}
    vals, notes = {}, {}
    for name, rest in _ROW.findall(b):
        n = nospace(name)
        if n not in _CANON or n in vals:
            continue
        v, tail = parse_pct(rest)
        if v is None:
            continue
        vals[n] = v
        note = _clean_note(tail)
        if note:
            notes[n] = note
    return vals, notes


_NUM = re.compile(r"^[\d,]+$")


def parse_hwp_table(txt):
    """별표 표(hwp 추출 텍스트: 용도지역명 다음 줄에 건폐율, 그 다음 줄에 용적률)에서 일반기준 값을 읽는다.
    용도지역별 첫 번째로 나오는 값 쌍만 사용한다."""
    lines = [l.strip() for l in txt.splitlines() if l.strip()]
    cov, far = {}, {}
    for i, l in enumerate(lines):
        n = nospace(l)
        if n in _CANON and n not in cov and i + 2 < len(lines) and _NUM.match(lines[i + 1]) and _NUM.match(lines[i + 2]):
            cov[n], far[n] = _int(lines[i + 1]), _int(lines[i + 2])
    return cov, far


def parse_ordinance(txt, hwp_table_text=None):
    """조문 우선, 조문에 표가 없으면(별표 인용) hwp 표 텍스트 사용.
    반환: (cov, far, cov_notes, far_notes, method)."""
    cov, cnote = parse_article(txt, "건폐율")
    far, fnote = parse_article(txt, "용적률")
    if len(cov) >= 15 and len(far) >= 15:
        return cov, far, cnote, fnote, "article"
    if hwp_table_text:
        c2, f2 = parse_hwp_table(hwp_table_text)
        if len(c2) >= 15 and len(f2) >= 15:
            return c2, f2, {}, {}, "annex-hwp"
    return cov, far, cnote, fnote, "article-partial"


def zone_table(cov, far, cov_notes=None, far_notes=None):
    """{zone: {coverage, far, coverage_note, far_note}} — 둘 중 하나라도 읽은 용도지역만. 없는 값은 None/''."""
    cov_notes, far_notes = cov_notes or {}, far_notes or {}
    zones = {}
    for z in CANON_ZONES:
        if z in cov or z in far:
            zones[z] = {"coverage": cov.get(z), "far": far.get(z),
                        "coverage_note": cov_notes.get(z, ""), "far_note": far_notes.get(z, "")}
    return zones
