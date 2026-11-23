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

    # 용도지역별 일조 적용 여부는 건축법 시행령 제86조 원문 대조 전이므로 단정하지 않는다.
    sun_p = "CONDITIONAL"
    zone_txt = (", ".join(zinfo["categories"]) if zinfo["known"] else "미확인")
    sun_cond = (f"용도지역({zone_txt})별 적용 여부는 건축법 시행령 제86조 원문과 조례로 확인 "
                "(정북방향, 경계·높이·인접대지 조건 포함)")
    add("건축법 일조·높이·대지안의 공지", sun_p, sun_cond,
        "건축 가능한 3차원 외피", "단일 높이÷2 공식 사용 금지; 위치·높이별 검토",
        LAW_URLS["건축법 시행령"])

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


# 사용자 입력 편의용 항목 이름. 법정 제외 항목 목록과 대조되지 않았다(원문 미대조).
FAR_EXCLUSION_KEYS = {
    "underground": "지하층 면적",
    "above_ground_parking": "지상층 주차용 면적(부속용도)",
    "refuge_safety_zone": "초고층·준초고층 피난안전구역 면적",
    "roof_refuge_space": "경사지붕 아래 대피공간 면적",
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
            "reason": "항목은 원문 미대조 - 제외 가능 여부·범위는 건축법 시행령 제119조 등 원문으로 확인 필요"}


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
# 부설주차장 산정 (사전 검토용)
# 법정 기준값(㎡당 1대)은 코드에 내장하지 않는다. 주차장법 시행령 별표 1과 해당
# 지자체 조례 원문에서 확인한 값을 사용자가 용도별로 직접 입력해야 계산한다.
# ---------------------------------------------------------------------------
def parking_required(items, sqm_per_space=None, rounding="total"):
    """용도별 (시설면적 / 입력 기준값) 산술 시나리오. 기준값 미입력 용도는 계산하지 않는다.

    items: [(용도명, 시설면적㎡), ...]
    sqm_per_space: {용도명: 원문·조례에서 확인한 '㎡당 1대' 값}
    rounding: 'total'(합산 후 올림) | 'per_use'(용도별 올림 후 합산). 끝수 처리 규정은
              원문 확인 전이므로 두 방식 값을 모두 반환하고 selected만 선택값이다.
    """
    sqm_per_space = sqm_per_space or {}
    if rounding not in ("total", "per_use"):
        return {"status": "UNKNOWN", "reason": "rounding은 total 또는 per_use"}
    if not items:
        return {"status": "UNKNOWN", "reason": "용도·시설면적 입력 없음"}
    rows, missing = [], []
    for use, area in items:
        try:
            a = float(area)
        except (TypeError, ValueError):
            return {"status": "UNKNOWN", "reason": f"면적 입력 오류: {use}"}
        if not math.isfinite(a) or a < 0:
            return {"status": "UNKNOWN", "reason": f"면적은 0 이상이어야 함: {use}"}
        if use not in sqm_per_space or sqm_per_space[use] in (None, "", 0):
            missing.append(use)
            continue
        try:
            base = float(sqm_per_space[use])
        except (TypeError, ValueError):
            return {"status": "UNKNOWN", "reason": f"기준값 입력 오류: {use}"}
        if not math.isfinite(base) or base <= 0:
            return {"status": "UNKNOWN", "reason": f"기준값은 양수여야 함: {use}"}
        exact = a / base
        rows.append({"use": use, "area_m2": round(a, 2), "sqm_per_space": base,
                     "exact": round(exact, 4), "ceil": math.ceil(round(exact, 6))})
    if missing:
        return {"status": "UNKNOWN",
                "reason": "기준값 미입력 용도 있음 — 주차장법 시행령 별표 1·지자체 조례 원문에서 확인 후 입력",
                "missing_basis_uses": missing, "computed_partial": rows,
                "source_url": LAW_URLS["주차장법"]}
    exact_total = sum(r["exact"] for r in rows)
    total_ceil = math.ceil(round(exact_total, 6))
    per_use_ceil = sum(r["ceil"] for r in rows)
    return {"status": "PREVIEW", "rows": rows,
            "exact_total": round(exact_total, 4),
            "ceil_of_total": total_ceil, "sum_of_use_ceils": per_use_ceil,
            "selected": total_ceil if rounding == "total" else per_use_ceil,
            "rounding_differs": total_ceil != per_use_ceil,
            "reason": "입력 기준값의 출처·시행일, 끝수 처리, 주차산정면적 범위는 원문으로 확인 필요",
            "source_url": LAW_URLS["주차장법"]}
