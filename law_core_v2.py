"""OpenCrab Core v2 rules adapted for offline use.

This is a local, deterministic adapter of the Core v2 routing policy, NOT
a live OpenCrab API connection and NOT a legal opinion.
"""
import json
import math
from dataclasses import dataclass, asdict
from typing import Optional, Sequence

CORE_PACK_ID = "43e5bd73-4435-4f15-95d1-dd9ba786f001"
CORE_VERSION = "v2.1 / local-policy-adapter"
PRIORITIES = ("REQUIRED", "CONDITIONAL", "LOW_PRIORITY", "UNKNOWN")

# 원문 확인용 링크(조문 인용이 아님). 시행일·조문은 직접 확인해야 한다.
LAW_URLS = {
    "건축법": "https://www.law.go.kr/법령/건축법",
    "건축법 시행령": "https://www.law.go.kr/법령/건축법시행령",
    "국토계획법": "https://www.law.go.kr/법령/국토의계획및이용에관한법률",
    "주차장법": "https://www.law.go.kr/법령/주차장법",
    "장애인등편의법": "https://www.law.go.kr/법령/장애인ㆍ노인ㆍ임산부등의편의증진보장에관한법률",
    "녹색건축물법": "https://www.law.go.kr/법령/녹색건축물조성지원법",
    "주택법": "https://www.law.go.kr/법령/주택법",
    "소방시설법": "https://www.law.go.kr/법령/소방시설설치및관리에관한법률",
}


@dataclass(frozen=True)
class Finding:
    law_group: str
    priority: str
    condition: str
    design_impact: str
    action: str
    evidence_status: str = "공식 원문 및 현장 조건 확인 필요"
    source_url: str = ""

    def as_dict(self):
        return asdict(self)


# (판별 키워드, 분류) — 구체적인 명칭이 먼저 매칭되도록 순서 유지
_NORTH_LIGHT_ZONES = ("전용주거", "일반주거")

_ZONE_RULES = (
    ("전용주거", "전용주거"), ("일반주거", "일반주거"), ("준주거", "준주거"),
    ("상업", "상업"), ("공업", "공업"), ("녹지", "녹지"),
    ("관리지역", "관리"), ("농림", "농림"), ("자연환경보전", "자연환경보전"),
)


def classify_zones(zone_names: Optional[Sequence[str]]):
    """용도지역 명칭 목록 분류. 빈 값은 '미확인'이며 '해당 없음'이 아니다."""
    names = [str(z).strip() for z in (zone_names or []) if str(z).strip()]
    cats, unmatched = [], []
    for n in names:
        compact = n.replace(" ", "")
        for kw, cat in _ZONE_RULES:
            if kw in compact:
                if cat not in cats:
                    cats.append(cat)
                break
        else:
            unmatched.append(n)
    return {
        "categories": cats,
        "unmatched": unmatched,
        "known": bool(cats),
        # 둘 이상 조회: 필지가 걸치거나 중복 지정 → 면적·위치별 검토 필요
        "overlap": len(names) > 1,
    }


def route_laws(building_use: str = "", site_address: str = "",
               site_area: Optional[float] = None,
               is_public: bool = False, is_housing_project: bool = False,
               has_district_plan: Optional[bool] = None,
               zone_names: Optional[Sequence[str]] = None):
    """Route legal review topics. Never infer binding legal numbers."""
    use = (building_use or "").replace(" ", "").lower()
    address = (site_address or "").strip()
    zinfo = classify_zones(zone_names)
    rows = []

    def add(name, priority, condition, impact, action, url=""):
        rows.append(Finding(name, priority, condition, impact, action, source_url=url))

    add("건축법·건축법 시행령", "REQUIRED",
        "건축물 계획에 기본 적용; 용도·규모·구조에 따라 세부사항 달라짐",
        "대지·높이·피난·방화·건축물 용도", "현행 조문, 별표 및 예외조건 검토",
        LAW_URLS["건축법"])
    add("국토계획법·도시계획조례", "REQUIRED" if address else "UNKNOWN",
        "대지의 용도지역·용도지구 및 지역 조례 확인",
        "건폐율·용적률·허용용도·도시계획 제한",
        "주소·토지이용계획·지자체 조례·시행일 교차 확인", LAW_URLS["국토계획법"])
    add("주차장법·주차장 조례", "REQUIRED" if use else "CONDITIONAL",
        "시설용도별 주차대수 및 조례 적용", "법정 주차 규모와 차량동선",
        "주차산정면적, 용도별 적용기준 및 반올림 규칙 확인", LAW_URLS["주차장법"])
    add("지구단위계획", "REQUIRED" if has_district_plan else
        ("CONDITIONAL" if has_district_plan is None else "LOW_PRIORITY"),
        "대지에 지구단위계획 결정·지침 존재 여부",
        "건축선·높이·배치·용도·경관 등", "결정도서 및 시행지침 원문 확인")

    # 일조: 건축법 제61조제1항(현행: 시행 2026-11-12, 제21880호) — 전용·일반주거지역 안 건축물이 대상.
    # 단서(영 제86조제2항, 시행 2026-11-12): 정북 인접 대지가 전용·일반주거지역이 아닌 경우, 일정 구역의 20m 이상 도로 접함, 건축협정 등.
    zone_txt = (", ".join(zinfo["categories"]) if zinfo["known"] else "미확인")
    exceptions = ("영 제86조제2항 예외: 정북 인접 대지가 전용·일반주거지역이 아닌 경우, 지구단위계획구역·경관지구 등에서 "
                  "너비 20m 이상 도로에 접한 경우, 건축협정구역 등 — 인접 대지 용도지역까지 확인")
    if zinfo["known"] and any(c in _NORTH_LIGHT_ZONES for c in zinfo["categories"]):
        sun_p = "REQUIRED"
        sun_cond = (f"용도지역({zone_txt}) → 건축법 제61조제1항 대상(전용·일반주거지역 안 건축물). 정북방향 인접 대지경계선에서 "
                    "높이 10m 이하 부분 1.5m 이상, 10m 초과 17m 이하 부분 5m 이상, 17m 초과 부분 높이의 1/2 이상 이격하되 "
                    "거리는 지방자치단체 조례로 정함(법 하한). " + exceptions)
    elif zinfo["known"]:
        sun_p = "CONDITIONAL"
        sun_cond = (f"용도지역({zone_txt})은 법 제61조제1항 정북일조 대상(전용·일반주거지역)이 아님. 다만 공동주택 채광 등 별도 "
                    "이격(영 제86조제3항), 지구단위계획·조례를 확인")
    else:
        sun_p = "CONDITIONAL"
        sun_cond = ("용도지역 미확인: 전용·일반주거지역이면 건축법 제61조제1항 정북일조 대상. " + exceptions)
    add("건축법 일조·높이·대지안의 공지", sun_p, sun_cond,
        "건축 가능한 3차원 외피", "단일 높이÷2 공식 사용 금지; 부분 높이별로 이격거리 검토(north_light_setback)",
        LAW_URLS["건축법"])

    add("피난·방화·소방", "CONDITIONAL",
        "용도·층수·면적·수용인원·구조 조건에 따라 달라짐",
        "직통계단·피난거리·방화구획·설비",
        "법정 설계기준 및 소방 관계법령 세부 검토", LAW_URLS["소방시설법"])
    public_or_community = is_public or any(x in use for x in
        ("행정복지", "청사", "도서관", "학교", "교육연구", "문화", "복지", "커뮤니티"))
    add("장애인 편의·BF", "REQUIRED" if public_or_community else "CONDITIONAL",
        "공공·다중이용시설 또는 의무대상 조건 확인",
        "무장애 접근 및 이동·위생시설·인증", "대상 여부·예외·세부 설치기준 확인",
        LAW_URLS["장애인등편의법"])
    add("녹색건축·에너지", "CONDITIONAL",
        "공공성·건축규모·연면적·용도·사업시점 조건 확인",
        "에너지절약계획서·인증 및 설비",
        "시행일 기준 의무·예외·인증 목표 확인", LAW_URLS["녹색건축물법"])
    add("주택법·도시정비법", "CONDITIONAL" if is_housing_project else "LOW_PRIORITY",
        "공동주택 사업 또는 정비사업 해당 여부",
        "사업 승인·정비계획·주택기준",
        "사업방식 확인 전 적용 법령으로 확정 금지", LAW_URLS["주택법"])

    if zinfo["overlap"]:
        add("용도지역 중첩·걸침 검토", "REQUIRED",
            "용도지역이 둘 이상 조회됨(" + ", ".join(zinfo["categories"] + zinfo["unmatched"]) + ")",
            "건폐율·용적률·일조 기준이 필지 내 위치/면적별로 달라질 수 있음",
            "지적경계와 용도지역 경계를 겹쳐 면적 비율 확인 후 조문별 적용 방식 검토",
            LAW_URLS["건축법"])
    if zinfo["unmatched"]:
        add("미분류 용도지역 명칭", "UNKNOWN",
            "분류 규칙에 없는 명칭: " + ", ".join(zinfo["unmatched"]),
            "해당 지역의 허용용도·밀도 판단 불가", "토지이용계획확인서로 명칭 직접 확인")
    if site_area is None:
        add("대지면적 데이터", "UNKNOWN", "대지면적 미입력",
            "면적 및 규모 산정 불가", "공부상·측량 면적 확인")
    return rows


def _bad(v):
    return v is None or not math.isfinite(v)


def preview_area(site_area, building_area, floor_area_for_far, coverage_pct, far_pct,
                 verified_source=False):
    """Only calculate conditional scenarios with explicit verified legal inputs."""
    unknown = {"status": "UNKNOWN", "reason": "면적 또는 검증된 비율 입력 부족/오류"}
    if any(_bad(v) for v in (site_area, coverage_pct, far_pct)):
        return unknown
    if any(v is not None and (not math.isfinite(v) or v < 0)
           for v in (building_area, floor_area_for_far)):
        return unknown
    if site_area <= 0 or not 0 <= coverage_pct <= 100 or far_pct < 0:
        return unknown
    max_footprint = site_area * coverage_pct / 100
    max_far_area = site_area * far_pct / 100
    out = {"status": "PREVIEW" if not verified_source else "CONDITIONAL",
           "max_building_area_m2": round(max_footprint, 2),
           "max_far_counted_area_m2": round(max_far_area, 2),
           "building_area_check": None, "far_area_check": None,
           "reason": "산정용 면적·예외·적용 조례의 별도 검토 필요"}
    if building_area is not None:
        out["building_area_check"] = "WITHIN_INPUT_LIMIT" if building_area <= max_footprint else "EXCEEDS_INPUT_LIMIT"
    if floor_area_for_far is not None:
        out["far_area_check"] = "WITHIN_INPUT_LIMIT" if floor_area_for_far <= max_far_area else "EXCEEDS_INPUT_LIMIT"
    return out


# 건축법 시행령 제119조제1항제4호(시행 2026-11-12): 용적률 산정 시 연면적에서 제외하는 면적.
# 다목·라목은 '삭제'. 사본: data/law_snapshots/bldg_decree_art119_20261112.txt
FAR_LAW_META = {"law": "건축법 시행령 제119조제1항제4호", "promulgation_no": "36817",
                "effective_date": "2026-11-12",
                "snapshot": "data/law_snapshots/bldg_decree_art119_20261112.txt"}
FAR_EXCLUSION_KEYS = {
    "underground": "지하층의 면적 (4호 가목)",
    "above_ground_parking": "지상층의 주차용(해당 건축물의 부속용도인 경우만 해당)으로 쓰는 면적 (4호 나목)",
    "refuge_safety_zone": "제34조제3항·제4항에 따라 초고층·준초고층 건축물에 설치하는 피난안전구역의 면적 (4호 마목)",
    "roof_refuge_space": "제40조제4항제2호에 따라 건축물의 경사지붕 아래에 설치하는 대피공간의 면적 (4호 바목)",
}


def far_counted_area(total_floor_area, exclusions=None):
    """연면적 − 사용자 입력 제외면적 = 용적률 산정용 연면적(산술 결과, 상태 PREVIEW)."""
    exclusions = exclusions or {}
    try:
        total = float(total_floor_area)
        ex = {k: float(v or 0) for k, v in exclusions.items()}
    except (TypeError, ValueError):
        return {"status": "UNKNOWN", "reason": "연면적 또는 제외면적 입력 오류"}
    if not math.isfinite(total) or total <= 0 or any(
            not math.isfinite(v) or v < 0 for v in ex.values()):
        return {"status": "UNKNOWN", "reason": "연면적은 양수, 제외면적은 0 이상이어야 함"}
    bad_keys = [k for k in ex if k not in FAR_EXCLUSION_KEYS]
    if bad_keys:
        return {"status": "UNKNOWN", "reason": "알 수 없는 제외 항목: " + ", ".join(bad_keys)}
    excluded = sum(ex.values())
    if excluded > total:
        return {"status": "UNKNOWN", "reason": "제외면적 합계가 연면적을 초과"}
    return {"status": "PREVIEW", "total_floor_area_m2": round(total, 2),
            "excluded_m2": round(excluded, 2),
            "far_counted_area_m2": round(total - excluded, 2),
            "excluded_detail": {FAR_EXCLUSION_KEYS[k]: round(v, 2) for k, v in ex.items() if v},
            "law": FAR_LAW_META,
            "reason": "제외 항목은 시행령 제119조제1항제4호 원문 기준. 연면적 자체는 각 층 바닥면적의 합계이며 바닥면적 산입 제외(같은 항 제3호)와 용적률 한도(법 제56조·조례)는 별도 확인"}


_PRIORITY_ORDER = {"REQUIRED": 0, "CONDITIONAL": 1, "UNKNOWN": 2, "LOW_PRIORITY": 3}


def sort_findings(findings):
    return sorted(findings, key=lambda f: _PRIORITY_ORDER[f.priority])


def findings_to_markdown(findings, context=None):
    lines = [f"# 법규 검토 우선순위 (Core {CORE_VERSION})", ""]
    for k, v in (context or {}).items():
        lines.append(f"- {k}: {v}")
    lines += ["", "> 사전 검토용이며 법적 적합 판정·인허가 검토를 대체하지 않습니다.", ""]
    for f in sort_findings(findings):
        lines += [f"## [{f.priority}] {f.law_group}",
                  f"- 조건: {f.condition}", f"- 설계 영향: {f.design_impact}",
                  f"- 대응 전략: {f.action}", f"- 근거 상태: {f.evidence_status}"]
        if f.source_url:
            lines.append(f"- 원문 확인 링크: {f.source_url}")
        lines.append("")
    return "\n".join(lines)


def findings_to_json(findings, context=None):
    return json.dumps({"core_version": CORE_VERSION, "pack_id": CORE_PACK_ID,
                       "context": context or {},
                       "findings": [f.as_dict() for f in sort_findings(findings)]},
                      ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 부설주차장 산정 — 주차장법 시행령 [별표 1] (공포번호 36623, 시행일 2026-08-28)
# 원문 사본: data/law_snapshots/parking_decree_b1_20260828.txt (테스트가 코드와 대조)
# 범위: 신축 기준의 산술 시나리오. 용도변경·증축(비고 5·7), 조례 강화/완화(비고 11),
#       장애인전용구획(비고 10), 경형자동차 인정(비고 12) 등은 계산하지 않는다.
# ---------------------------------------------------------------------------
from fractions import Fraction

PARKING_LAW_META = {
    "law": "주차장법 시행령 [별표 1]", "promulgation_no": "36623",
    "effective_date": "2026-08-28", "mst": "288729",
    "snapshot": "data/law_snapshots/parking_decree_b1_20260828.txt",
}

# key: (표 호수, 표시명, 수량 단위, 곱, 나눔) → 대수 = 수량 × 곱 / 나눔 (원문 '시설면적/100㎡' 등)
PARKING_RULES = {
    "위락": (1, "위락시설", "시설면적㎡", 1, 100),
    "문화집회등": (2, "문화 및 집회시설(관람장 제외)·종교·판매·운수·의료(정신병원·요양병원·격리병원 제외)·"
               "운동(골프장·골프연습장·옥외수영장 제외)·업무(외국공관·오피스텔 제외)·방송통신 중 방송국·장례식장",
               "시설면적㎡", 1, 150),
    "근생숙박": (3, "제1종 근린생활시설(원문 제외분 제외)·제2종 근린생활시설·숙박시설", "시설면적㎡", 1, 200),
    "단독주택": (4, "단독주택(다가구주택 제외)", "시설면적㎡", None, None),
    "골프장": (6, "골프장", "홀 수", 10, 1),
    "골프연습장": (6, "골프연습장", "타석 수", 1, 1),
    "옥외수영장": (6, "옥외수영장", "정원(명)", 1, 15),
    "관람장": (6, "관람장", "정원(명)", 1, 100),
    "수련공장발전": (7, "수련시설·공장(아파트형 제외)·발전시설", "시설면적㎡", 1, 350),
    "창고": (8, "창고시설", "시설면적㎡", 1, 400),
    "학생용기숙사": (9, "학생용 기숙사", "시설면적㎡", 1, 400),
    "데이터센터": (10, "방송통신시설 중 데이터센터", "시설면적㎡", 1, 400),
    "기타": (11, "그 밖의 건축물", "시설면적㎡", 1, 300),
}
# 표 제5호: 「주택건설기준 등에 관한 규정」 제27조에 따른 대수 — 이 모듈은 산정하지 않는다.
PARKING_MANUAL_KEYS = {"다가구공동오피스텔": "다가구주택·공동주택(기숙사 제외)·업무시설 중 오피스텔 (표 제5호)"}


def _frac(x):
    return Fraction(str(x))


def _detached(area):
    """표 제4호 + 비고 4 단서. 50㎡ 이하는 비고 4 단서의 '면적/100㎡'를 적용(원문상 복합시설
    맥락의 단서이므로 해석 확인 필요)."""
    if area <= 50:
        return area / 100
    if area <= 150:
        return Fraction(1)
    return 1 + (area - 150) / 100


def _trunc1(v):
    return Fraction(math.floor(v * 10), 10)


def _round1(v):  # 0.05 이상은 올림(사사오입) — 원문이 방식을 정하지 않아 후보로만 사용
    return Fraction(math.floor(v * 10 + Fraction(1, 2)), 10)


def _final(sum_value):
    """비고 6: 소수점 이하가 0.5 이상이면 1로 본다."""
    n = math.floor(sum_value)
    return n + (1 if sum_value - n >= Fraction(1, 2) else 0)


def _multi_house(area):
    """대전광역시 주차장 조례 별표 6 제4호 다중주택. 50㎡ 이하는 조례에 규정이 없어 None(미확정)."""
    if area <= 50:
        return None
    if area <= 150:
        return Fraction(1)
    return 1 + (area - 150) / 50


def parking_required(items, ordinance_div=None, rules=None, manual=None, undefined=None,
                     law_meta=None, notes=None):
    """부설주차장 법정 대수 산술 시나리오(신축).

    items: [(규칙키, 수량), ...] — 규칙표(rules)의 키. 수량 단위는 규칙표 참고.
    rules/manual/undefined/law_meta: 지자체 조례 규칙표를 넘기면 그 표로 계산(기본: 주차장법 시행령 별표 1).
    ordinance_div: {규칙키: 직접 확인한 나눔값} 로 시설면적 기준 용도를 대체(미검증으로 표시).
    원문이 정하지 않은 부분(소수 첫째자리 처리 방식, 0.5~1대 구간)은 후보값을 모두 반환하고
    확정하지 않는다(count=None, ambiguous=True).
    """
    ordinance_div = ordinance_div or {}
    rules = PARKING_RULES if rules is None else rules
    manual = PARKING_MANUAL_KEYS if manual is None else manual
    undefined = undefined or {}
    meta = law_meta or PARKING_LAW_META
    if not items:
        return {"status": "UNKNOWN", "reason": "용도·수량 입력 없음"}
    manual_hit = [k for k, _ in items if k in manual]
    if manual_hit:
        return {"status": "UNKNOWN",
                "reason": "표 제5호 시설물은 「주택건설기준 등에 관한 규정」 제27조로 별도 산정",
                "manual_only": [manual[k] for k in manual_hit], "law": meta}
    undef_hit = [k for k, _ in items if k in undefined]
    if undef_hit:
        return {"status": "UNKNOWN", "reason": "; ".join(undefined[k] for k in undef_hit), "law": meta}
    rows = []
    for key, qty in items:
        if key not in rules:
            return {"status": "UNKNOWN", "reason": f"알 수 없는 용도 키: {key}"}
        try:
            q = _frac(qty)
        except (ValueError, TypeError):
            return {"status": "UNKNOWN", "reason": f"수량 입력 오류: {key}"}
        if q < 0:
            return {"status": "UNKNOWN", "reason": f"수량은 0 이상이어야 함: {key}"}
        no, label, unit, mult, div = rules[key]
        basis = "법령·조례 원문"
        if key == "단독주택":
            v = _detached(q)
        elif key == "다중주택":
            v = _multi_house(q)
            if v is None:
                return {"status": "UNKNOWN", "reason": "다중주택 시설면적 50㎡ 이하는 조례 별표 6에 산정 규정이 없음",
                        "law": meta}
        else:
            if key in ordinance_div:
                try:
                    div = _frac(ordinance_div[key])
                except (ValueError, TypeError):
                    return {"status": "UNKNOWN", "reason": f"기준 입력 오류: {key}"}
                if div <= 0 or unit != "시설면적㎡":
                    return {"status": "UNKNOWN", "reason": f"직접 입력 기준은 시설면적 기준 용도의 양수만 허용: {key}"}
                basis = "직접 입력값(미검증)"
            else:
                div = _frac(div)
            v = q * _frac(mult) / div
        rows.append({"table_no": no, "use": label, "quantity": float(q), "unit": unit,
                     "exact": float(v), "basis": basis, "_v": v})
    sums = {"절사": sum((_trunc1(r["_v"]) for r in rows), Fraction(0)),
            "반올림": sum((_round1(r["_v"]) for r in rows), Fraction(0))}
    candidates, reasons = set(), []
    for name, sm in sums.items():
        if sm < 1:
            if sm >= Fraction(1, 2):
                candidates.update({0, 1})
                reasons.append("합계가 0.5 이상 1 미만: 비고 6 본문(→1대)과 단서(1대 미만→0)의 적용 확인 필요")
            else:
                candidates.add(0)
        else:
            candidates.add(_final(sm))
    for r in rows:
        r.pop("_v")
    ordered = sorted(candidates)
    ambiguous = len(ordered) > 1
    if ambiguous and not reasons:
        reasons.append("용도별 소수 첫째자리 처리 방식(절사/반올림)에 따라 최종 대수가 달라짐 — 원문이 방식을 정하지 않음")
    return {"status": "PREVIEW", "rows": rows,
            "sum_one_decimal": {k: float(v) for k, v in sums.items()},
            "candidates": ordered, "ambiguous": ambiguous,
            "count": None if ambiguous else ordered[0],
            "ambiguity_reasons": reasons,
            "scope": "신축 산술 시나리오. 용도변경·증축(비고 5·7), 경형자동차 인정(비고 12) 등 미반영",
            "notes": list(notes or []),
            "law": meta, "source_url": LAW_URLS["주차장법"]}


# ---------------------------------------------------------------------------
# 정북일조 이격거리 — 건축법 제61조제1항 (현행: 시행 2026-11-12, 법률 제21880호)
# 사본: data/law_snapshots/bldg_act_art61_20261112.txt
# 법은 '조례로 정하는 거리'를 아래 범위(하한)에서 정하도록 하므로 이 값은 법 하한이며 조례가 더 클 수 있다.
# ---------------------------------------------------------------------------
NORTH_LIGHT_LAW_META = {"law": "건축법 제61조제1항", "promulgation_no": "21880", "effective_date": "2026-11-12",
                        "snapshot": "data/law_snapshots/bldg_act_art61_20261112.txt"}


def north_light_law_minimum(part_height_m):
    """건축물 한 부분의 높이(m)에 대한 정북방향 이격거리의 법 하한(m).
    10m 이하 → 1.5, 10m 초과 17m 이하 → 5, 17m 초과 → 높이의 1/2. 부분 높이는 지표면 기준 그 부분의 높이."""
    try:
        h = float(part_height_m)
    except (TypeError, ValueError):
        return {"status": "UNKNOWN", "reason": "높이 입력 오류"}
    if not math.isfinite(h) or h <= 0:
        return {"status": "UNKNOWN", "reason": "높이는 0보다 커야 함"}
    if h <= 10:
        v, tier = 1.5, "높이 10미터 이하인 부분 (제1호)"
    elif h <= 17:
        v, tier = 5.0, "높이 10미터 초과 17미터 이하인 부분 (제2호)"
    else:
        v, tier = h / 2, "높이 17미터를 초과하는 부분 (제3호, 부분 높이의 2분의 1)"
    return {"status": "PREVIEW", "height_m": h, "law_min_m": round(v, 3), "tier": tier,
            "law": NORTH_LIGHT_LAW_META,
            "reason": "법 하한. 거리는 지방자치단체 조례가 정하며, 정북 인접 대지가 전용·일반주거지역이 아닌 경우 등 "
                      "영 제86조제2항 예외는 반영하지 않음"}
