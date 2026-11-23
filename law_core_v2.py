"""OpenCrab Core v2 rules adapted for offline use.

This is a local, deterministic adapter of the Core v2 routing policy, NOT
a live OpenCrab API connection and NOT a legal opinion.
"""
from dataclasses import dataclass, asdict
from typing import Optional

CORE_PACK_ID = "43e5bd73-4435-4f15-95d1-dd9ba786f001"
CORE_VERSION = "v2 / local-policy-adapter"
PRIORITIES = ("REQUIRED", "CONDITIONAL", "LOW_PRIORITY", "UNKNOWN")

@dataclass(frozen=True)
class Finding:
    law_group: str
    priority: str
    condition: str
    design_impact: str
    action: str
    evidence_status: str = "공식 원문 및 현장 조건 확인 필요"

    def as_dict(self):
        return asdict(self)

def route_laws(building_use: str = "", site_address: str = "",
               site_area: Optional[float] = None,
               is_public: bool = False, is_housing_project: bool = False,
               has_district_plan: Optional[bool] = None):
    """Route legal review topics. Never infer binding legal numbers."""
    use = (building_use or "").replace(" ", "").lower()
    address = (site_address or "").strip()
    rows = []

    def add(name, priority, condition, impact, action):
        rows.append(Finding(name, priority, condition, impact, action))

    add("건축법·건축법 시행령", "REQUIRED",
        "건축물 계획에 기본 적용; 용도·규모·구조에 따라 세부사항 달라짐",
        "대지·높이·피난·방화·건축물 용도", "현행 조문, 별표 및 예외조건 검토")
    add("국토계획법·도시계획조례", "REQUIRED" if address else "UNKNOWN",
        "대지의 용도지역·용도지구 및 지역 조례 확인",
        "건폐율·용적률·허용용도·도시계획 제한",
        "주소·토지이용계획·지자체 조례·시행일 교차 확인")
    add("주차장법·주차장 조례", "REQUIRED" if use else "CONDITIONAL",
        "시설용도별 주차대수 및 조례 적용", "법정 주차 규모와 차량동선",
        "주차산정면적, 용도별 적용기준 및 반올림 규칙 확인")
    add("지구단위계획", "REQUIRED" if has_district_plan else
        ("CONDITIONAL" if has_district_plan is None else "LOW_PRIORITY"),
        "대지에 지구단위계획 결정·지침 존재 여부",
        "건축선·높이·배치·용도·경관 등", "결정도서 및 시행지침 원문 확인")
    add("건축법 일조·높이·대지안의 공지", "CONDITIONAL",
        "용도지역, 정북 방향, 경계·높이·인접대지 조건 확인",
        "건축 가능한 3차원 외피", "단일 높이÷2 공식 사용 금지; 위치·높이별 검토")
    add("피난·방화·소방", "CONDITIONAL",
        "용도·층수·면적·수용인원·구조 조건에 따라 달라짐",
        "직통계단·피난거리·방화구획·설비",
        "법정 설계기준 및 소방 관계법령 세부 검토")
    public_or_community = is_public or any(x in use for x in
        ("행정복지", "청사", "도서관", "학교", "교육연구", "문화", "복지", "커뮤니티"))
    add("장애인 편의·BF", "REQUIRED" if public_or_community else "CONDITIONAL",
        "공공·다중이용시설 또는 의무대상 조건 확인",
        "무장애 접근 및 이동·위생시설·인증", "대상 여부·예외·세부 설치기준 확인")
    add("녹색건축·에너지", "CONDITIONAL",
        "공공성·건축규모·연면적·용도·사업시점 조건 확인",
        "에너지절약계획서·인증 및 설비",
        "시행일 기준 의무·예외·인증 목표 확인")
    add("주택법·도시정비법", "CONDITIONAL" if is_housing_project else "LOW_PRIORITY",
        "공동주택 사업 또는 정비사업 해당 여부",
        "사업 승인·정비계획·주택기준",
        "사업방식 확인 전 적용 법령으로 확정 금지")
    if site_area is None:
        add("대지면적 데이터", "UNKNOWN", "대지면적 미입력",
            "면적 및 규모 산정 불가", "공부상·측량 면적 확인")
    return rows

def preview_area(site_area, building_area, floor_area_for_far, coverage_pct, far_pct,
                 verified_source=False):
    """Only calculate conditional scenarios with explicit verified legal inputs."""
    numeric = [site_area, coverage_pct, far_pct]
    if any(v is None for v in numeric) or site_area <= 0 or not 0 <= coverage_pct <= 100 or far_pct < 0:
        return {"status": "UNKNOWN", "reason": "면적 또는 검증된 비율 입력 부족/오류"}
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
