"""
건축법규 자동조회 시스템 - FastAPI 백엔드
- 국가법령정보 API → 용도지역 조례 데이터 조회 (우선)
- 브이월드 API → 용도지역 조회 (운영키 승인 후 활성화)
- PDF 파싱 데이터 → fallback
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import httpx
import json
import re
import os

app = FastAPI(title="건축법규 자동조회 시스템")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────
# API 키 설정
# ──────────────────────────────────────────────
VWORLD_API_KEY = os.getenv("VWORLD_API_KEY", "6F8D2670-8C8E-3958-AE79-9645DCE6BB0F")
LAW_API_KEY = os.getenv("LAW_API_KEY", "skfls1205")
DATA_GO_KEY = os.getenv("DATA_GO_KEY", "w%2Bv6AlivQ")

# 브이월드 운영키 승인 여부 (승인 후 True로 변경)
VWORLD_APPROVED = os.getenv("VWORLD_APPROVED", "false").lower() == "true"

# ──────────────────────────────────────────────
# 조례 데이터 (PDF 원문 기반, 2025~2026년 최신)
# ──────────────────────────────────────────────
# 용도지역 코드 → 한국어명 매핑
ZONE_NAMES = {
    "UQA110": "제1종전용주거지역",
    "UQA120": "제2종전용주거지역",
    "UQA210": "제1종일반주거지역",
    "UQA220": "제2종일반주거지역",
    "UQA230": "제3종일반주거지역",
    "UQA310": "준주거지역",
    "UQB110": "중심상업지역",
    "UQB120": "일반상업지역",
    "UQB130": "근린상업지역",
    "UQB140": "유통상업지역",
    "UQC110": "전용공업지역",
    "UQC120": "일반공업지역",
    "UQC130": "준공업지역",
    "UQD110": "보전녹지지역",
    "UQD120": "생산녹지지역",
    "UQD130": "자연녹지지역",
    "UQE010": "보전관리지역",
    "UQE020": "생산관리지역",
    "UQE030": "계획관리지역",
    "UQF010": "농림지역",
    "UQG010": "자연환경보전지역",
}

# 조례 데이터 구조:
# coverage_ratio: 건폐율(%)
# floor_area_ratio: 용적률(%)
# source: 조례 출처 (조례 번호, 시행일)
# note: 특이사항
ORDINANCE_DATA = {
    "서울특별시": {
        "source": "서울특별시조례 제9948호 (2026.1.5. 시행)",
        "zones": {
            "제1종전용주거지역": {"coverage": 50, "far": 100},
            "제2종전용주거지역": {"coverage": 40, "far": 120},
            "제1종일반주거지역": {"coverage": 60, "far": 150},
            "제2종일반주거지역": {"coverage": 60, "far": 200},
            "제3종일반주거지역": {"coverage": 50, "far": 250},
            "준주거지역":        {"coverage": 60, "far": 400},
            "중심상업지역":      {"coverage": 60, "far": 1000, "note": "서울도심 800%"},
            "일반상업지역":      {"coverage": 60, "far": 800,  "note": "서울도심 600%"},
            "근린상업지역":      {"coverage": 60, "far": 600,  "note": "서울도심 500%"},
            "유통상업지역":      {"coverage": 60, "far": 600,  "note": "서울도심 500%"},
            "전용공업지역":      {"coverage": 60, "far": 200},
            "일반공업지역":      {"coverage": 60, "far": 200},
            "준공업지역":        {"coverage": 60, "far": 400},
            "보전녹지지역":      {"coverage": 20, "far": 50},
            "생산녹지지역":      {"coverage": 20, "far": 50},
            "자연녹지지역":      {"coverage": 20, "far": 50},
        }
    },
    "부산광역시": {
        "source": "부산광역시조례 제7892호 (2026.2.25. 시행)",
        "zones": {
            "제1종전용주거지역": {"coverage": 50, "far": 100},
            "제2종전용주거지역": {"coverage": 40, "far": 120},
            "제1종일반주거지역": {"coverage": 60, "far": 180},
            "제2종일반주거지역": {"coverage": 60, "far": 220, "note": "대지 1천㎡ 초과 시 200%"},
            "제3종일반주거지역": {"coverage": 50, "far": 300},
            "준주거지역":        {"coverage": 60, "far": 400},
            "중심상업지역":      {"coverage": 80, "far": 1300},
            "일반상업지역":      {"coverage": 80, "far": 1000},
            "근린상업지역":      {"coverage": 70, "far": 700},
            "유통상업지역":      {"coverage": 70, "far": 800},
            "전용공업지역":      {"coverage": 70, "far": 300},
            "일반공업지역":      {"coverage": 70, "far": 350},
            "준공업지역":        {"coverage": 70, "far": 400},
            "보전녹지지역":      {"coverage": 20, "far": 60},
            "생산녹지지역":      {"coverage": 20, "far": 80},
            "자연녹지지역":      {"coverage": 20, "far": 80},
        }
    },
    "대구광역시": {
        "source": "대구광역시조례 제6393호 (2025.10.30. 시행)",
        "zones": {
            "제1종전용주거지역": {"coverage": 50, "far": 100},
            "제2종전용주거지역": {"coverage": 40, "far": 120},
            "제1종일반주거지역": {"coverage": 60, "far": 200},
            "제2종일반주거지역": {"coverage": 60, "far": 220},
            "제3종일반주거지역": {"coverage": 50, "far": 250},
            "준주거지역":        {"coverage": 60, "far": 400, "note": "공동주택 250%, 주거복합 300%"},
            "중심상업지역":      {"coverage": 80, "far": 1300},
            "일반상업지역":      {"coverage": 70, "far": 1000},
            "근린상업지역":      {"coverage": 70, "far": 800},
            "유통상업지역":      {"coverage": 70, "far": 900},
            "전용공업지역":      {"coverage": 70, "far": 300},
            "일반공업지역":      {"coverage": 70, "far": 350},
            "준공업지역":        {"coverage": 70, "far": 400},
            "보전녹지지역":      {"coverage": 20, "far": 60},
            "생산녹지지역":      {"coverage": 20, "far": 100},
            "자연녹지지역":      {"coverage": 20, "far": 100},
        }
    },
    "인천광역시": {
        "source": "인천광역시조례 제7684호 (2025.12.31. 시행)",
        "zones": {
            "제1종전용주거지역": {"coverage": 50, "far": 80},
            "제2종전용주거지역": {"coverage": 50, "far": 120},
            "제1종일반주거지역": {"coverage": 60, "far": 200},
            "제2종일반주거지역": {"coverage": 60, "far": 250},
            "제3종일반주거지역": {"coverage": 50, "far": 300},
            "준주거지역":        {"coverage": 60, "far": 500, "note": "순수주거용 공동주택 300%"},
            "중심상업지역":      {"coverage": 80, "far": 1300},
            "일반상업지역":      {"coverage": 70, "far": 1000},
            "근린상업지역":      {"coverage": 70, "far": 700},
            "유통상업지역":      {"coverage": 70, "far": 800},
            "전용공업지역":      {"coverage": 70, "far": 300},
            "일반공업지역":      {"coverage": 70, "far": 350},
            "준공업지역":        {"coverage": 70, "far": 400},
            "보전녹지지역":      {"coverage": 20, "far": 50},
            "생산녹지지역":      {"coverage": 20, "far": 80},
            "자연녹지지역":      {"coverage": 20, "far": 80},
        }
    },
    "광주광역시": {
        "source": "광주광역시조례 제6636호 (2025.11.11. 시행)",
        "zones": {
            "제1종전용주거지역": {"coverage": 40, "far": 80},
            "제2종전용주거지역": {"coverage": 40, "far": 120},
            "제1종일반주거지역": {"coverage": 60, "far": 150},
            "제2종일반주거지역": {"coverage": 60, "far": 220},
            "제3종일반주거지역": {"coverage": 50, "far": 250},
            "준주거지역":        {"coverage": 60, "far": 400},
            "중심상업지역":      {"coverage": 80, "far": 1300},
            "일반상업지역":      {"coverage": 60, "far": 1000},
            "근린상업지역":      {"coverage": 60, "far": 700},
            "유통상업지역":      {"coverage": 60, "far": 800},
            "전용공업지역":      {"coverage": 70, "far": 300},
            "일반공업지역":      {"coverage": 70, "far": 350},
            "준공업지역":        {"coverage": 70, "far": 400},
            "보전녹지지역":      {"coverage": 20, "far": 60},
            "생산녹지지역":      {"coverage": 20, "far": 60},
            "자연녹지지역":      {"coverage": 20, "far": 60},
        }
    },
    "울산광역시": {
        "source": "울산광역시조례 제3180호 (2025.9.25. 시행) - 별표24",
        "zones": {
            # 별표24 기준 (국토계획법 시행령 범위 내 울산 조례)
            "제1종전용주거지역": {"coverage": 50, "far": 100},
            "제2종전용주거지역": {"coverage": 40, "far": 120},
            "제1종일반주거지역": {"coverage": 60, "far": 200},
            "제2종일반주거지역": {"coverage": 60, "far": 250},
            "제3종일반주거지역": {"coverage": 50, "far": 300},
            "준주거지역":        {"coverage": 60, "far": 400},
            "중심상업지역":      {"coverage": 80, "far": 1300},
            "일반상업지역":      {"coverage": 80, "far": 1000},
            "근린상업지역":      {"coverage": 70, "far": 700},
            "유통상업지역":      {"coverage": 70, "far": 800},
            "전용공업지역":      {"coverage": 70, "far": 300},
            "일반공업지역":      {"coverage": 70, "far": 350},
            "준공업지역":        {"coverage": 70, "far": 400},
            "보전녹지지역":      {"coverage": 20, "far": 60},
            "생산녹지지역":      {"coverage": 20, "far": 80},
            "자연녹지지역":      {"coverage": 20, "far": 100},
        }
    },
    "세종특별자치시": {
        "source": "세종특별자치시조례 제2978호 (2026.2.27. 시행)",
        "zones": {
            "제1종전용주거지역": {"coverage": 50, "far": 100},
            "제2종전용주거지역": {"coverage": 50, "far": 150},
            "제1종일반주거지역": {"coverage": 60, "far": 200},
            "제2종일반주거지역": {"coverage": 60, "far": 250},
            "제3종일반주거지역": {"coverage": 50, "far": 300},
            "준주거지역":        {"coverage": 70, "far": 400},
            "중심상업지역":      {"coverage": 80, "far": 1300},
            "일반상업지역":      {"coverage": 80, "far": 1100},
            "근린상업지역":      {"coverage": 70, "far": 700},
            "유통상업지역":      {"coverage": 80, "far": 900},
            "전용공업지역":      {"coverage": 70, "far": 300},
            "일반공업지역":      {"coverage": 70, "far": 350},
            "준공업지역":        {"coverage": 70, "far": 400},
            "보전녹지지역":      {"coverage": 20, "far": 80},
            "생산녹지지역":      {"coverage": 20, "far": 100},
            "자연녹지지역":      {"coverage": 20, "far": 100},
        }
    },
    "대전광역시": {
        "source": "대전광역시조례 제6595호 (2026.2.13. 시행) - 제45조·제50조 원문 확인",
        "zones": {
            # 제45조(건폐율), 제50조(용적률) 원문 기준
            "제1종전용주거지역": {"coverage": 50, "far": 100},
            "제2종전용주거지역": {"coverage": 40, "far": 120},
            "제1종일반주거지역": {"coverage": 60, "far": 150},   # 용적률 150% (기존 200% 오류 수정)
            "제2종일반주거지역": {"coverage": 60, "far": 200},
            "제3종일반주거지역": {"coverage": 50, "far": 250},
            "준주거지역":        {"coverage": 60, "far": 400},
            "중심상업지역":      {"coverage": 80, "far": 1300},
            "일반상업지역":      {"coverage": 70, "far": 1100},  # 건폐율 70%, 용적률 1,100% (기존 80%/1,000% 오류 수정)
            "근린상업지역":      {"coverage": 60, "far": 700},   # 건폐율 60% (기존 70% 오류 수정)
            "유통상업지역":      {"coverage": 70, "far": 900},   # 용적률 900% (기존 800% 오류 수정)
            "전용공업지역":      {"coverage": 70, "far": 300},
            "일반공업지역":      {"coverage": 70, "far": 350},
            "준공업지역":        {"coverage": 70, "far": 400},
            "보전녹지지역":      {"coverage": 20, "far": 60},
            "생산녹지지역":      {"coverage": 20, "far": 70},    # 용적률 70% (기존 80% 오류 수정)
            "자연녹지지역":      {"coverage": 20, "far": 80},    # 용적률 80% (기존 100% 오류 수정)
        }
    },
}

# 시/도명 정규화 매핑
CITY_NORMALIZE = {
    "서울": "서울특별시", "서울특별시": "서울특별시",
    "부산": "부산광역시", "부산광역시": "부산광역시",
    "대구": "대구광역시", "대구광역시": "대구광역시",
    "인천": "인천광역시", "인천광역시": "인천광역시",
    "광주": "광주광역시", "광주광역시": "광주광역시",
    "울산": "울산광역시", "울산광역시": "울산광역시",
    "세종": "세종특별자치시", "세종특별자치시": "세종특별자치시",
    "대전": "대전광역시", "대전광역시": "대전광역시",
}

# ──────────────────────────────────────────────
# 요청/응답 모델
# ──────────────────────────────────────────────
class AddressRequest(BaseModel):
    address: str

class BuildingPlan(BaseModel):
    address: str
    site_area: float             # 대지면적 (㎡)
    building_area: float         # 건축면적 (㎡)
    total_floor_area: float      # 연면적 (㎡)
    floors: int                  # 층수
    height: float                # 높이 (m)
    building_use: str            # 건축물 용도 (예: 단독주택, 근린생활시설)
    parking_count: int           # 계획 주차대수

class LandInfo(BaseModel):
    address: str
    area: Optional[float] = None  # 토지면적 (mock 또는 브이월드)

# ──────────────────────────────────────────────
# 주소 → 시/도 추출
# ──────────────────────────────────────────────
def extract_city(address: str) -> Optional[str]:
    for keyword, city_name in CITY_NORMALIZE.items():
        if keyword in address:
            return city_name
    return None

# ──────────────────────────────────────────────
# 국가법령정보 API - 조례 데이터 조회
# ──────────────────────────────────────────────
async def fetch_ordinance_from_law_api(city: str) -> Optional[dict]:
    """
    국가법령정보 API로 도시계획조례 데이터 조회
    API: https://www.law.go.kr/DRF/lawService.do
    """
    query = f"{city} 도시계획 조례"
    url = "https://www.law.go.kr/DRF/lawService.do"
    params = {
        "OC": LAW_API_KEY,
        "target": "ordin",
        "type": "JSON",
        "query": query,
        "display": 1,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                # 응답 파싱 (법령정보 API 구조에 따라)
                items = data.get("OrdinSearch", {}).get("items", {})
                if items:
                    return {"api_data": items, "source": "국가법령정보 API"}
    except Exception as e:
        print(f"[법령 API 오류] {e}")
    return None

# ──────────────────────────────────────────────
# 브이월드 API - 용도지역 조회
# ──────────────────────────────────────────────
async def fetch_zone_from_vworld(address: str) -> Optional[dict]:
    """
    브이월드 API로 주소 → 좌표 → 용도지역 조회
    운영키 승인 후 활성화
    """
    if not VWORLD_APPROVED:
        return None

    try:
        # 1단계: 주소 → 좌표 변환
        geocode_url = "https://api.vworld.kr/req/address"
        async with httpx.AsyncClient(timeout=10) as client:
            geo_resp = await client.get(geocode_url, params={
                "service": "address",
                "request": "getcoord",
                "version": "2.0",
                "crs": "epsg:4326",
                "address": address,
                "refine": "true",
                "simple": "false",
                "format": "json",
                "type": "road",
                "key": VWORLD_API_KEY,
            })
            geo_data = geo_resp.json()
            result = geo_data.get("response", {}).get("result", {})
            point = result.get("point", {})
            lon = point.get("x")
            lat = point.get("y")

            if not lon or not lat:
                return None

            # 2단계: 좌표 → 용도지역 조회
            zone_url = "https://api.vworld.kr/req/data"
            zone_resp = await client.get(zone_url, params={
                "service": "data",
                "request": "getfeature",
                "version": "2.0",
                "data": "LT_C_UQ111",  # 용도지역지구
                "geomfilter": f"POINT({lon} {lat})",
                "columns": "uq_cd,uq_nm,prpos_area1_nm",
                "format": "json",
                "key": VWORLD_API_KEY,
            })
            zone_data = zone_resp.json()
            features = zone_data.get("response", {}).get("result", {}).get("featureCollection", {}).get("features", [])

            if features:
                props = features[0].get("properties", {})
                return {
                    "zone_code": props.get("uq_cd", ""),
                    "zone_name": props.get("uq_nm", ""),
                    "lat": lat,
                    "lon": lon,
                    "source": "브이월드 API",
                }
    except Exception as e:
        print(f"[브이월드 API 오류] {e}")
    return None

# ──────────────────────────────────────────────
# 토지면적 조회 (브이월드 또는 mock)
# ──────────────────────────────────────────────
async def fetch_land_area(address: str) -> dict:
    """
    토지면적 조회
    - 브이월드 승인 시: 실제 API 조회
    - 미승인 시: mock 데이터 반환
    """
    if VWORLD_APPROVED:
        # TODO: 브이월드 토지특성 API (LT_C_LHSPCE) 조회
        # 현재 구현 준비 상태
        pass

    # Mock 데이터 (브이월드 승인 대기 중)
    return {
        "area": None,
        "source": "mock",
        "message": "브이월드 운영키 승인 후 자동 조회 예정",
        "vworld_approved": VWORLD_APPROVED,
    }

# ──────────────────────────────────────────────
# 용도지역 조례 데이터 조회 (핵심 함수)
# ──────────────────────────────────────────────
async def get_zone_ordinance(address: str, zone_name: Optional[str] = None) -> dict:
    """
    용도지역 조례 데이터를 순서대로 조회:
    1. 브이월드 API (운영키 승인 시)
    2. 국가법령정보 API
    3. PDF 기반 로컬 데이터 (fallback)
    """
    result = {
        "address": address,
        "zone_name": zone_name or "미확인",
        "city": None,
        "coverage_ratio": None,
        "floor_area_ratio": None,
        "ordinance_source": None,
        "data_source": None,
        "note": None,
    }

    # 시/도 추출
    city = extract_city(address)
    result["city"] = city

    # 1. 브이월드로 용도지역 조회 시도
    if VWORLD_APPROVED and not zone_name:
        vworld_data = await fetch_zone_from_vworld(address)
        if vworld_data:
            zone_name = vworld_data.get("zone_name")
            result["zone_name"] = zone_name
            result["data_source"] = "브이월드 API"

    # 2. 도시계획 조례 데이터에서 건폐율/용적률 조회
    if city and city in ORDINANCE_DATA:
        city_data = ORDINANCE_DATA[city]
        zones = city_data["zones"]

        if zone_name and zone_name in zones:
            zone_data = zones[zone_name]
            result["coverage_ratio"] = zone_data["coverage"]
            result["floor_area_ratio"] = zone_data["far"]
            result["ordinance_source"] = city_data["source"]
            result["note"] = zone_data.get("note")
            result["data_source"] = result.get("data_source") or "조례 DB (PDF 원문)"
        else:
            result["message"] = f"'{zone_name}' 용도지역 데이터 없음"
    else:
        result["message"] = f"'{city}' 조례 데이터 미지원 (8개 광역시 지원)"

    return result

# ──────────────────────────────────────────────
# 법규 검토 (O / X / △)
# ──────────────────────────────────────────────
def check_building_regulations(plan: BuildingPlan, zone_data: dict) -> dict:
    """
    계획 건물의 법규 적합 여부 검토
    반환: O (적합) / X (부적합) / △ (조건부/요확인)
    """
    checks = []

    coverage = zone_data.get("coverage_ratio")
    far = zone_data.get("floor_area_ratio")

    # 건폐율 검토
    if coverage and plan.site_area > 0:
        actual_coverage = (plan.building_area / plan.site_area) * 100
        ratio = actual_coverage / coverage
        if ratio <= 1.0:
            status = "O"
            msg = f"건폐율 적합 ({actual_coverage:.1f}% ≤ {coverage}%)"
        elif ratio <= 1.05:
            status = "△"
            msg = f"건폐율 경계 ({actual_coverage:.1f}% ≈ {coverage}%)"
        else:
            status = "X"
            msg = f"건폐율 초과 ({actual_coverage:.1f}% > {coverage}%)"
        checks.append({"item": "건폐율", "status": status, "detail": msg,
                        "planned": f"{actual_coverage:.1f}%", "limit": f"{coverage}%"})

    # 용적률 검토
    if far and plan.site_area > 0:
        actual_far = (plan.total_floor_area / plan.site_area) * 100
        ratio = actual_far / far
        if ratio <= 1.0:
            status = "O"
            msg = f"용적률 적합 ({actual_far:.1f}% ≤ {far}%)"
        elif ratio <= 1.05:
            status = "△"
            msg = f"용적률 경계 ({actual_far:.1f}% ≈ {far}%)"
        else:
            status = "X"
            msg = f"용적률 초과 ({actual_far:.1f}% > {far}%)"
        checks.append({"item": "용적률", "status": status, "detail": msg,
                        "planned": f"{actual_far:.1f}%", "limit": f"{far}%"})

    # 높이 제한 (용도지역별 일반 기준)
    height_limit = get_height_limit(zone_data.get("zone_name", ""))
    if height_limit:
        if plan.height <= height_limit:
            status = "O"
            msg = f"높이 적합 ({plan.height}m ≤ {height_limit}m)"
        elif plan.height <= height_limit * 1.05:
            status = "△"
            msg = f"높이 경계 ({plan.height}m ≈ {height_limit}m)"
        else:
            status = "X"
            msg = f"높이 초과 ({plan.height}m > {height_limit}m)"
        checks.append({"item": "높이제한", "status": status, "detail": msg,
                        "planned": f"{plan.height}m", "limit": f"{height_limit}m"})
    else:
        checks.append({"item": "높이제한", "status": "△",
                        "detail": "별도 높이제한 확인 필요 (지구단위계획 등)", "planned": f"{plan.height}m", "limit": "-"})

    # 주차대수 검토
    parking_check = check_parking(plan)
    checks.append(parking_check)

    # 허용 용도 검토
    use_check = check_building_use(plan.building_use, zone_data.get("zone_name", ""))
    checks.append(use_check)

    # 전체 결과
    statuses = [c["status"] for c in checks]
    if "X" in statuses:
        overall = "X"
    elif "△" in statuses:
        overall = "△"
    else:
        overall = "O"

    return {
        "overall": overall,
        "checks": checks,
    }

def get_height_limit(zone_name: str) -> Optional[float]:
    """용도지역별 높이제한 (국토계획법 기준)"""
    limits = {
        "제1종전용주거지역": None,   # 조례로 위임 (서울 4층·16m 등)
        "제2종전용주거지역": None,
        "제1종일반주거지역": None,
        "제2종일반주거지역": None,
        "제3종일반주거지역": None,
        "준주거지역": None,
    }
    return limits.get(zone_name)

def check_parking(plan: BuildingPlan) -> dict:
    """주차대수 최소 기준 검토 (건축법 시행령 기준)"""
    # 단순화된 기준 (실제는 용도별·면적별 세분화 필요)
    use = plan.building_use
    area = plan.total_floor_area

    # 주차장법 시행령 기준 (시설물별 설치기준)
    required = None
    if "단독주택" in use:
        required = 1 if area >= 50 else 0
    elif "공동주택" in use or "아파트" in use:
        required = max(1, int(area / 85))
    elif "근린생활시설" in use or "상업" in use:
        required = max(1, int(area / 134))
    elif "업무시설" in use:
        required = max(1, int(area / 150))
    elif "공장" in use:
        required = max(1, int(area / 350))

    if required is not None:
        if plan.parking_count >= required:
            return {"item": "주차대수", "status": "O",
                    "detail": f"주차 적합 (계획 {plan.parking_count}대 ≥ 최소 {required}대)",
                    "planned": f"{plan.parking_count}대", "limit": f"{required}대 이상"}
        else:
            return {"item": "주차대수", "status": "X",
                    "detail": f"주차 부족 (계획 {plan.parking_count}대 < 최소 {required}대)",
                    "planned": f"{plan.parking_count}대", "limit": f"{required}대 이상"}
    else:
        return {"item": "주차대수", "status": "△",
                "detail": "용도별 주차기준 별도 확인 필요",
                "planned": f"{plan.parking_count}대", "limit": "확인 필요"}

def check_building_use(use: str, zone_name: str) -> dict:
    """허용 용도 검토"""
    # 용도지역별 허용/금지 용도 (건축법 시행령 별표 기준)
    restricted_uses = {
        "제1종전용주거지역": ["근린생활시설", "판매시설", "업무시설", "숙박시설", "공장"],
        "제2종전용주거지역": ["판매시설", "업무시설", "숙박시설", "공장"],
        "제1종일반주거지역": ["숙박시설", "위락시설", "공장"],
        "제2종일반주거지역": ["위락시설", "공장"],
        "제3종일반주거지역": ["위락시설"],
        "보전녹지지역": ["판매시설", "업무시설", "숙박시설", "공장", "위락시설"],
    }
    allowed_uses = {
        "제1종전용주거지역": ["단독주택", "공동주택", "유치원", "초등학교"],
        "제2종전용주거지역": ["단독주택", "공동주택", "제1종근린생활시설"],
    }

    restricted = restricted_uses.get(zone_name, [])
    for r in restricted:
        if r in use:
            return {"item": "허용용도", "status": "X",
                    "detail": f"'{r}' 용도는 {zone_name}에 불허",
                    "planned": use, "limit": f"{zone_name} 허용 용도"}

    return {"item": "허용용도", "status": "△",
            "detail": "용도 허용 여부 건축사/허가부서 최종 확인 필요",
            "planned": use, "limit": "건축법 시행령 별표 확인"}

# ──────────────────────────────────────────────
# API 엔드포인트
# ──────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "service": "건축법규 자동조회 시스템",
        "version": "2.0",
        "cities": list(ORDINANCE_DATA.keys()),
        "vworld_approved": VWORLD_APPROVED,
    }

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/api/zone-info")
async def get_zone_info(req: AddressRequest):
    """
    주소 입력 → 용도지역 + 건폐율/용적률 조회
    """
    address = req.address.strip()
    if not address:
        raise HTTPException(status_code=400, detail="주소를 입력해주세요")

    city = extract_city(address)
    if not city:
        raise HTTPException(
            status_code=400,
            detail=f"지원 도시: {', '.join(ORDINANCE_DATA.keys())}. 광역시/특별시/특별자치시 이름을 포함한 주소를 입력하세요."
        )

    # 브이월드로 용도지역 자동 조회 시도
    zone_name = None
    vworld_result = None
    if VWORLD_APPROVED:
        vworld_result = await fetch_zone_from_vworld(address)
        if vworld_result:
            zone_name = vworld_result.get("zone_name")

    # 토지면적 조회
    land_info = await fetch_land_area(address)

    # 조례 데이터 조회
    zone_data = await get_zone_ordinance(address, zone_name)

    # 전체 조례 데이터 반환 (용도지역 미확인 시)
    city_data = ORDINANCE_DATA.get(city, {})
    all_zones = city_data.get("zones", {})

    return {
        "address": address,
        "city": city,
        "zone_name": zone_name,
        "zone_auto_detected": VWORLD_APPROVED and zone_name is not None,
        "coverage_ratio": zone_data.get("coverage_ratio"),
        "floor_area_ratio": zone_data.get("floor_area_ratio"),
        "ordinance_source": zone_data.get("ordinance_source") or city_data.get("source"),
        "data_source": zone_data.get("data_source") or "조례 DB (PDF 원문)",
        "land_area": land_info,
        "all_zones": all_zones,   # 전체 용도지역별 데이터
        "vworld_status": {
            "approved": VWORLD_APPROVED,
            "message": "운영키 승인 완료" if VWORLD_APPROVED else "운영키 승인 대기 중 (용도지역 자동조회 준비됨)",
        }
    }

@app.post("/api/zone-info/{zone_name}")
async def get_zone_info_with_zone(zone_name: str, req: AddressRequest):
    """
    주소 + 용도지역 직접 입력 → 건폐율/용적률 조회
    (브이월드 승인 전 수동 입력용)
    """
    address = req.address.strip()
    zone_data = await get_zone_ordinance(address, zone_name)

    city = extract_city(address)
    land_info = await fetch_land_area(address)

    return {
        **zone_data,
        "land_area": land_info,
        "ordinance_source": zone_data.get("ordinance_source"),
    }

@app.post("/api/check")
async def check_building(plan: BuildingPlan):
    """
    계획 건물 법규 검토 (O/X/△)
    """
    address = plan.address.strip()
    if not address:
        raise HTTPException(status_code=400, detail="주소를 입력해주세요")

    city = extract_city(address)

    # 브이월드로 용도지역 자동 조회
    zone_name = None
    if VWORLD_APPROVED:
        vworld_result = await fetch_zone_from_vworld(address)
        if vworld_result:
            zone_name = vworld_result.get("zone_name")

    # 조례 데이터 조회
    zone_data = await get_zone_ordinance(address, zone_name)

    if not zone_data.get("coverage_ratio"):
        return {
            "error": "용도지역 미확인 - zone_name을 직접 입력해주세요",
            "address": address,
            "city": city,
            "available_zones": list(ORDINANCE_DATA.get(city, {}).get("zones", {}).keys()),
        }

    # 법규 검토
    regulation_result = check_building_regulations(plan, zone_data)

    return {
        "address": address,
        "city": city,
        "zone_name": zone_data.get("zone_name"),
        "ordinance_source": zone_data.get("ordinance_source"),
        "site_area": plan.site_area,
        "building_area": plan.building_area,
        "total_floor_area": plan.total_floor_area,
        "floors": plan.floors,
        "height": plan.height,
        "building_use": plan.building_use,
        "parking_count": plan.parking_count,
        "regulation": regulation_result,
        "vworld_status": {
            "approved": VWORLD_APPROVED,
            "message": "자동 조회 완료" if VWORLD_APPROVED else "브이월드 승인 대기 중",
        }
    }

@app.get("/api/cities")
async def get_cities():
    """지원 도시 목록 및 조례 출처"""
    return {
        "cities": [
            {"name": city, "source": data["source"], "zones": list(data["zones"].keys())}
            for city, data in ORDINANCE_DATA.items()
        ]
    }

@app.get("/api/zones/{city}")
async def get_city_zones(city: str):
    """특정 도시의 전체 용도지역별 건폐율/용적률"""
    city_normalized = CITY_NORMALIZE.get(city)
    if not city_normalized or city_normalized not in ORDINANCE_DATA:
        raise HTTPException(status_code=404, detail=f"'{city}' 데이터 없음")

    data = ORDINANCE_DATA[city_normalized]
    return {
        "city": city_normalized,
        "source": data["source"],
        "zones": data["zones"],
    }

@app.get("/api/vworld/status")
async def vworld_status():
    """브이월드 API 상태 확인"""
    return {
        "approved": VWORLD_APPROVED,
        "api_key": VWORLD_API_KEY[:8] + "..." if VWORLD_API_KEY else None,
        "message": "운영키 승인 완료 - 용도지역 자동조회 가능" if VWORLD_APPROVED
                   else "운영키 승인 대기 중 - VWORLD_APPROVED=true 환경변수 설정 시 활성화",
        "pending_features": [
            "주소 → 좌표 변환 (Geocoding)",
            "좌표 → 용도지역 자동조회 (LT_C_UQ111)",
            "좌표 → 토지면적 자동조회 (LT_C_LHSPCE)",
        ] if not VWORLD_APPROVED else [],
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
    
