"""지자체 주차장 조례의 부설주차장 설치기준 별표(텍스트)를 구조화한다 (네트워크 없음).

원칙: 단순하고 해석이 분명한 분류만 계산 가능한 규칙(area / per_unit / detached)으로 만들고,
그 밖(공동주택·오피스텔 등 별도 규정 인용, 복잡한 조건)은 'manual' 로 원문 텍스트를 그대로 보관한다.
원문이 정하지 않았거나 파싱이 모호하면 계산 규칙을 만들지 않는다.
"""
import re

_BULLET = re.compile(r"^[\s○◦·‧ㆍ•\-ㆍ◎※▪■]+")
_CAT = re.compile(r"^(\d+(?:[-의]\d+)?)\.\s*(.+)$")
_DUP = re.compile(r"^\(?\s*(?:시설면적\s*[/÷]\s*[\d,.]+\s*㎡|[^()]*[/÷×]\s*[\d.]+[^()]*)\)?$")
_SQM = r"(?:㎡|제곱미터|m2)"
_AREA = re.compile(r"시설면적\s*([\d,]+)\s*" + _SQM + r"\s*(?:당|마다)\s*1\s*대")
_LAB_AREA = re.compile(r"^\s*([^:：]{1,60}?)\s*[:：]\s*시설면적\s*([\d,]+)\s*" + _SQM + r"\s*(?:당|마다)\s*1\s*대")
_GOLF = re.compile(r"골프장\s*[:：]?\s*1\s*홀\s*당\s*([\d.]+)\s*대")
_RANGE_A = re.compile(r"골프연습장\s*[:：]?\s*1\s*타석\s*당\s*([\d.]+)\s*대")
_RANGE_B = re.compile(r"골프연습장\s*[:：]?\s*([\d.]+)\s*타석\s*(?:당|마다)\s*1\s*대")
_POOL = re.compile(r"옥외수영장\s*[:：]?\s*정원\s*([\d,]+)\s*(?:인|명)\s*(?:당|마다)\s*1\s*대")
_STAND = re.compile(r"관람장\s*[:：]?\s*정원\s*([\d,]+)\s*(?:인|명)\s*(?:당|마다)\s*1\s*대")
_DET_LOWER = re.compile(r"50\s*" + _SQM + r"\s*초과\s*([\d,]+)\s*" + _SQM + r"\s*이하")
_DET_STEP = re.compile(r"([\d,]+)\s*" + _SQM + r"\s*(?:를\s*)?초과(?:하는)?\s*([\d,]+)\s*" + _SQM + r"\s*(?:당|마다)\s*1\s*대")


def _n(s):
    return s.replace(",", "")


def _norm_line(l):
    return _BULLET.sub("", l).strip()


def split_annex(text):
    """별표 텍스트 → (columns, categories[{no,label,body_lines}], notes_lines)."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    cats, cur, pre, notes = [], None, [], []
    in_notes = False
    last_primary = 0
    for l in lines:
        nl = _norm_line(l)
        if (cats or cur) and re.match(r"^(비\s*고|<\s*비고\s*>|\[\s*비고\s*\]|※\s*비\s*고)", nl):
            in_notes = True
            if cur:
                cats.append(cur); cur = None
            continue
        if in_notes:
            notes.append(l); continue
        m = _CAT.match(nl)
        if m and not re.match(r"^\d+\.\s*\d", nl):
            primary = int(re.match(r"\d+", m.group(1)).group(0))
            if primary <= last_primary and "-" not in m.group(1) and "의" not in m.group(1):
                # 번호가 거꾸로 가면(예: 표 11호 다음의 '1. 시설물의 종류는…') 비고 구간으로 본다
                in_notes = True
                if cur:
                    cats.append(cur); cur = None
                notes.append(l)
                continue
            last_primary = max(last_primary, primary)
            if cur:
                cats.append(cur)
            cur = {"no": m.group(1), "label": m.group(2).strip(), "body": []}
            continue
        if cur is None:
            pre.append(l)
        else:
            cur["body"].append(l)
    if cur:
        cats.append(cur)
    pre_text = " ".join(pre)
    columns = []
    if "관리지역" in pre_text and "도시지역" in pre_text:
        columns = ["도시지역 및 지구단위계획구역", "관리지역"]
    return columns, cats, notes


def _rules_from_body(body, ncols):
    """본문 라인에서 규칙 후보를 순서대로 뽑는다. 반환: list[(sublabel, unit, mult, div)] 또는 None(모호).
    원문의 규칙 표기 개수와 읽은 개수가 다르면 None(조용히 누락하지 않음)."""
    joined_lines = []
    for l in body:
        nl = _norm_line(l)
        if not nl or _DUP.match(nl):
            continue
        joined_lines.append(nl)
    text = " ".join(joined_lines)
    # 라벨 글자 사이가 벌어진 표기('골  프  장')를 정규화
    for pat, rep in ((r"골\s*프\s*연\s*습\s*장", "골프연습장"), (r"골\s*프\s*장", "골프장"),
                     (r"옥\s*외\s*수\s*영\s*장", "옥외수영장"), (r"관\s*람\s*장", "관람장")):
        text = re.sub(pat, rep, text)
    n_area = len(_AREA.findall(text))
    # 1) 골프장 등 단위 기준
    # 골프연습장: '1타석당 N대'(A)와 'N타석당 1대'(B) 두 표기를 위치 순서대로(같은 위치 중복 제거)
    range_hits = {}
    for m in _RANGE_A.finditer(text):
        range_hits[m.start()] = ("골프연습장", "타석 수", m.group(1), "1")
    for m in _RANGE_B.finditer(text):
        range_hits.setdefault(m.start(), ("골프연습장", "타석 수", "1", m.group(1)))
    # 단위 기준 전체를 원문 위치 순서로 정렬(열이 있을 때 열 순서 보존)
    positioned = []
    for rx, label, unit, mk in ((_GOLF, "골프장", "홀 수", lambda v: (v, "1")),
                                (_POOL, "옥외수영장", "정원(명)", lambda v: ("1", _n(v))),
                                (_STAND, "관람장", "정원(명)", lambda v: ("1", _n(v)))):
        for m in rx.finditer(text):
            mult, div = mk(m.group(1))
            positioned.append((m.start(), (label, unit, mult, div)))
    for st, it in range_hits.items():
        positioned.append((st, it))
    unit_items = [it for _, it in sorted(positioned, key=lambda x: x[0])]
    if unit_items:
        if n_area:  # 면적 기준과 단위 기준이 섞이면 자동 해석하지 않음
            return None
        # 원문에 등장한 라벨 수 × 열 수 와 읽은 규칙 수가 같아야 한다(일부만 읽고 넘어가는 것 방지)
        flat = re.sub(r"\s+", "", text)
        expected = sum(1 for kw in ("골프장", "골프연습장", "옥외수영장", "관람장") if kw in flat) * max(1, ncols)
        if len(unit_items) != expected:
            return None
        return unit_items
    # 2) 면적 기준 (라벨 있는 줄 우선)
    labeled = [m for m in (_LAB_AREA.match(l) for l in joined_lines) if m]
    items = []
    if len(labeled) >= 2:
        for m in labeled:
            items.append((m.group(1).strip(), "시설면적㎡", 1, int(_n(m.group(2)))))
    else:
        for m in _AREA.finditer(text):
            items.append((None, "시설면적㎡", 1, int(_n(m.group(1)))))
    if len(items) != n_area:  # 읽은 규칙 수가 원문의 '시설면적 N㎡당 1대' 표기 수와 다르면 누락 위험 → 수동
        return None
    return items


def parse_category(cat, columns):
    """카테고리 하나 → dict(kind, rules/…). 단순하지 않으면 manual."""
    label, body = cat["label"], cat["body"]
    raw = "\n".join([cat["label"]] + body)
    base = {"id": "c" + cat["no"], "no": cat["no"], "label": label, "raw": raw}
    ncols = max(1, len(columns))
    text = " ".join(_norm_line(l) for l in body)
    # 공동주택·오피스텔 등 별도 규정 인용 → 수동
    if "주택건설기준" in text or "주택건설 기준" in text:
        return {**base, "kind": "manual", "reason": "「주택건설기준 등에 관한 규정」 등 별도 규정으로 산정"}
    # 단독주택형(구간식)
    ml = _DET_LOWER.search(text)
    ms = _DET_STEP.search(text)
    if ml and ms and _n(ml.group(1)) == _n(ms.group(1)):
        return {**base, "kind": "detached", "lower": 50, "upper": int(_n(ml.group(1))), "step": int(_n(ms.group(2))),
                "columns_identical": ncols > 1}
    items = _rules_from_body(body, ncols)
    if not items:
        return {**base, "kind": "manual", "reason": "자동으로 읽을 수 있는 단순 기준이 아님"}
    # 라벨별 값 모으기 (열이 있으면 라벨당 열 수만큼)
    by_label = {}
    order = []
    for sub, unit, mult, div in items:
        k = (sub, unit)
        if k not in by_label:
            by_label[k] = []
            order.append(k)
        by_label[k].append({"mult": str(mult), "div": str(div)})
    rules = []
    for k in order:
        vals = by_label[k]
        if len(vals) == ncols:
            pass
        elif ncols > 1 and len(vals) == 1:
            vals = vals * ncols  # 열 구분 없이 한 값만 적힌 경우: 모든 열에 동일
        else:
            return {**base, "kind": "manual", "reason": f"규칙 개수({len(vals)})와 열 구성({ncols})이 맞지 않아 자동 해석하지 않음"}
        rules.append({"sublabel": k[0], "unit": k[1], "values": vals})
    note = ""
    mm = re.search(r"다만[^.]*", text)
    if mm:
        note = mm.group(0).strip()
    kind = "per_unit" if any(r["unit"] != "시설면적㎡" for r in rules) else "area"
    return {**base, "kind": kind, "rules": rules, "exception_note": note}


def parse_parking_annex(text):
    """별표 텍스트 전체 → {columns, categories, notes, small_house_rule}"""
    columns, cats, notes = split_annex(text)
    notes_text = " ".join(notes)
    return {
        "columns": columns,
        "categories": [parse_category(c, columns) for c in cats],
        "notes": notes,
        "small_house_rule": bool(re.search(r"50\s*제곱미터\s*이하", notes_text) and re.search(r"100\s*제곱미터로\s*나눈", notes_text)),
        "rounding_half_rule": bool(re.search(r"0\.5\s*이상인\s*(?:경우|때)에는\s*이를\s*1로\s*본다", notes_text)),
    }


# ---------------------------------------------------------------------------
# 조례가 자체 별표 없이 '주차장법 시행령 별표 1'을 그대로 따르는 경우
# 판정은 '설치기준이 영 별표 1과 같다/따른다/준용한다'로 직접 이어지는 문장만 인정한다.
# 시행령 표를 직접 고치는 단서("…"를 "…"로 한다)가 있으면 그대로 따른다고 볼 수 없어 제외한다.
# ---------------------------------------------------------------------------
_ART = re.compile(r"^제\d+조(?:의\d+)?\s*\(([^)\n]*)\)", re.M)
_ART_SKIP = ("장애인", "전용", "인근", "관리지역", "구조", "설비", "개방", "면제", "비용", "철거", "기계식", "무상", "보조", "융자")
_SENT_SPLIT = re.compile(r"(?<=[다요])\.\s+|(?<=다\.)\s*|\n")
_FOLLOW_A = re.compile(r"별표\s*1(?!\d)\s*(?:의\s*(?:기준|내용))?\s*(?:과|와)\s*같다")
_FOLLOW_B = re.compile(r"별표\s*1(?!\d)\s*(?:의\s*기준)?\s*(?:을|를|에)?\s*(?:따른다|준용한다|따라\s*설치)")
_FOLLOW_C = re.compile(r"제6조제1항\s*(?:의\s*규정\s*)?(?:을|를|에)\s*(?:따른다|준용한다)")  # '「주차장법 시행령」(이하 "영"이라 한다) 제6조제1항을 따른다' 형태 포함
_OWN_ANNEX = re.compile(r"별표\s*(?!1(?!\d))\d+\s*(?:과|와)\s*같")  # 한글 앞에서는 \b 가 동작하지 않아 (?!\d) 사용
_SUBST = re.compile(r"[“\"][^”\"]+[”\"]\s*(?:을|를)\s*[“\"][^”\"]+[”\"]\s*(?:으)?로\s*한다")
_NOT_PLAIN = ("단서에 따라", "다음 각 호", "이상이 되도록", "범위에서")


def find_follow_decree(text):
    """반환: {title, excerpt, proviso} 또는 None. proviso 는 '다만' 이하 단서(예외·면제 등)로 계산에는 반영하지 않는다."""
    for m in _ART.finditer(text):
        title = m.group(1)
        if "부설주차장" not in title or not re.search(r"설치|기준", title) or any(k in title for k in _ART_SKIP):
            continue
        nxt = _ART.search(text, m.end())
        blk = text[m.start(): nxt.start() if nxt else m.start() + 1500]
        flat = re.sub(r"\s+", " ", blk)
        if _OWN_ANNEX.search(flat) or _SUBST.search(flat):
            continue
        ok = False
        for sent in re.split(r"(?<=다)\.\s*", flat):
            if not re.search(r"설치\s*기준", sent) or any(w in sent for w in _NOT_PLAIN):
                continue
            if not re.search(r"시행령|영\s*(?:제|별표)|\"영\"", sent):
                continue
            if _FOLLOW_A.search(sent) or _FOLLOW_B.search(sent) or _FOLLOW_C.search(sent):
                ok = True
                break
        if not ok:
            continue
        pv = re.search(r"다만[^.]*\.?", flat)
        return {"title": m.group(0).strip(), "excerpt": blk.strip()[:900], "proviso": pv.group(0).strip() if pv else ""}
    return None


def completeness(categories):
    """표를 일부만 읽었을 가능성 표시: 읽은 분류가 8개 미만(영 별표 1은 10개 안팎)이거나, 계산 가능 분류보다 수동 분류가 많으면 경고."""
    ok = sum(1 for c in categories if c["kind"] in ("area", "per_unit", "detached"))
    manual = sum(1 for c in categories if c["kind"] == "manual")
    return {"incomplete": len(categories) < 8, "manual_heavy": manual > ok}
