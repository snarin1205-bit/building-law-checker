from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import requests
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

LAND_API_KEY = "6F8D2670-8C8E-3958-AE79-9645DCE6BB0F"

ORDINANCE = {
    "서울특별시": {
        "제1종전용주거지역": {"건폐율": 50, "용적률": 100},
        "제2종전용주거지역": {"건폐율": 40, "용적률": 120},
        "제1종일반주거지역": {"건폐율": 60, "용적률": 150},
        "제2종일반주거지역": {"건폐율": 60, "용적률": 200},
        "제3종일반주거지역": {"건폐율": 50, "용적률": 250},
        "준주거지역":        {"건폐율": 60, "용적률": 400},
        "중심상업지역":      {"건폐율": 60, "용적률": 1000},
        "일반상업지역":      {"건폐율": 60, "용적률": 800},
        "근린상업지역":      {"건폐율": 60, "용적률": 600},
        "유통상업지역":      {"건폐율": 60, "용적률": 600},
        "전용공업지역":      {"건폐율": 60, "용적률": 200},
        "일반공업지역":      {"건폐율": 60, "용적률": 200},
        "준공업지역":        {"건폐율": 60, "용적률": 400},
        "보전녹지지역":      {"건폐율": 20, "용적률": 80},
        "생산녹지지역":      {"건폐율": 20, "용적률": 100},
        "자연녹지지역":      {"건폐율": 20, "용적률": 100},
    },
    "부산광역시": {
        "제1종전용주거지역": {"건폐율": 50, "용적률": 100},
        "제2종전용주거지역": {"건폐율": 40, "용적률": 150},
        "제1종일반주거지역": {"건폐율": 60, "용적률": 200},
        "제2종일반주거지역": {"건폐율": 60, "용적률": 220},
        "제3종일반주거지역": {"건폐율": 50, "용적률": 300},
        "준주거지역":        {"건폐율": 60, "용적률": 400},
        "중심상업지역":      {"건폐율": 80, "용적률": 1300},
        "일반상업지역":      {"건폐율": 60, "용적률": 1000},
        "근린상업지역":      {"건폐율": 70, "용적률": 700},
        "유통상업지역":      {"건폐율": 70, "용적률": 800},
        "전용공업지역":      {"건폐율": 70, "용적률": 300},
        "일반공업지역":      {"건폐율": 70, "용적률": 350},
        "준공업지역":        {"건폐율": 60, "용적률": 400},
        "보전녹지지역":      {"건폐율": 20, "용적률": 80},
        "생산녹지지역":      {"건폐율": 20, "용적률": 100},
        "자연녹지지역":      {"건폐율": 20, "용적률": 100},
    },
    "대구광역시": {
        "제1종전용주거지역": {"건폐율": 50, "용적률": 100},
        "제2종전용주거지역": {"건폐율": 40, "용적률": 120},
        "제1종일반주거지역": {"건폐율": 60, "용적률": 150},
        "제2종일반주거지역": {"건폐율": 60, "용적률": 200},
        "제3종일반주거지역": {"건폐율": 50, "용적률": 250},
        "준주거지역":        {"건폐율": 60, "용적률": 400},
        "중심상업지역":      {"건폐율": 80, "용적률": 1300},
        "일반상업지역":      {"건폐율": 70, "용적률": 1100},
        "근린상업지역":      {"건폐율": 70, "용적률": 700},
        "유통상업지역":      {"건폐율": 70, "용적률": 900},
        "전용공업지역":      {"건폐율": 70, "용적률": 300},
        "일반공업지역":      {"건폐율": 70, "용적률": 350},
        "준공업지역":        {"건폐율": 70, "용적률": 400},
        "보전녹지지역":      {"건폐율": 20, "용적률": 80},
        "생산녹지지역":      {"건폐율": 20, "용적률": 100},
        "자연녹지지역":      {"건폐율": 20, "용적률": 100},
    },
    "인천광역시": {
        "제1종전용주거지역": {"건폐율": 50, "용적률": 100},
        "제2종전용주거지역": {"건폐율": 40, "용적률": 120},
        "제1종일반주거지역": {"건폐율": 60, "용적률": 150},
        "제2종일반주거지역": {"건폐율": 60, "용적률": 200},
        "제3종일반주거지역": {"건폐율": 50, "용적률": 250},
        "준주거지역":        {"건폐율": 60, "용적률": 400},
        "중심상업지역":      {"건폐율": 80, "용적률": 1300},
        "일반상업지역":      {"건폐율": 70, "용적률": 1100},
        "근린상업지역":      {"건폐율": 70, "용적률": 700},
        "유통상업지역":      {"건폐율": 70, "용적률": 900},
        "전용공업지역":      {"건폐율": 70, "용적률": 300},
        "일반공업지역":      {"건폐율": 70, "용적률": 350},
        "준공업지역":        {"건폐율": 70, "용적률": 400},
        "보전녹지지역":      {"건폐율": 20, "용적률": 80},
        "생산녹지지역":      {"건폐율": 20, "용적률": 100},
        "자연녹지지역":      {"건폐율": 20, "용적률": 100},
    },
    "광주광역시": {
        "제1종전용주거지역": {"건폐율": 50, "용적률": 100},
        "제2종전용주거지역": {"건폐율": 40, "용적률": 120},
        "제1종일반주거지역": {"건폐율": 60, "용적률": 150},
        "제2종일반주거지역": {"건폐율": 60, "용적률": 200},
        "제3종일반주거지역": {"건폐율": 50, "용적률": 250},
        "준주거지역":        {"건폐율": 60, "용적률": 400},
        "중심상업지역":      {"건폐율": 80, "용적률": 1300},
        "일반상업지역":      {"건폐율": 70, "용적률": 1000},
        "근린상업지역":      {"건폐율": 70, "용적률": 700},
        "유통상업지역":      {"건폐율": 70, "용적률": 900},
        "전용공업지역":      {"건폐율": 70, "용적률": 300},
        "일반공업지역":      {"건폐율": 70, "용적률": 350},
        "준공업지역":        {"건폐율": 70, "용적률": 400},
        "보전녹지지역":      {"건폐율": 20, "용적률": 80},
        "생산녹지지역":      {"건폐율": 20, "용적률": 100},
        "자연녹지지역":      {"건폐율": 20, "용적률": 100},
    },
    "대전광역시": {
        "제1종전용주거지역": {"건폐율": 50, "용적률": 100},
        "제2종전용주거지역": {"건폐율": 40, "용적률": 120},
        "제1종일반주거지역": {"건폐율": 60, "용적률": 150},
        "제2종일반주거지역": {"건폐율": 60, "용적률": 200},
        "제3종일반주거지역": {"건폐율": 50, "용적률": 250},
        "준주거지역":        {"건폐율": 60, "용적률": 400},
        "중심상업지역":      {"건폐율": 80, "용적률": 1300},
        "일반상업지역":      {"건폐율": 70, "용적률": 1100},
        "근린상업지역":      {"건폐율": 60, "용적률": 700},
        "유통상업지역":      {"건폐율": 70, "용적률": 900},
        "전용공업지역":      {"건폐율": 70, "용적률": 300},
        "일반공업지역":      {"건폐율": 70, "용적률": 350},
        "준공업지역":        {"건폐율": 70, "용적률": 400},
        "보전녹지지역":      {"건폐율": 20, "용적률": 60},
        "생산녹지지역":      {"건폐율": 20, "용적률": 70},
        "자연녹지지역":      {"건폐율": 20, "용적률": 80},
    },
    "울산광역시": {
        "제1종전용주거지역": {"건폐율": 50, "용적률": 100},
        "제2종전용주거지역": {"건폐율": 40, "용적률": 120},
        "제1종일반주거지역": {"건폐율": 60, "용적률": 150},
        "제2종일반주거지역": {"건폐율": 60, "용적률": 200},
        "제3종일반주거지역": {"건폐율": 50, "용적률": 250},
        "준주거지역":        {"건폐율": 60, "용적률": 400},
        "중심상업지역":      {"건폐율": 80, "용적률": 1300},
        "일반상업지역":      {"건폐율": 70, "용적률": 1100},
        "근린상업지역":      {"건폐율": 70, "용적률": 700},
        "유통상업지역":      {"건폐율": 70, "용적률": 900},
        "전용공업지역":      {"건폐율": 70, "용적률": 300},
        "일반공업지역":      {"건폐율": 70, "용적률": 350},
        "준공업지역":        {"건폐율": 70, "용적률": 400},
        "보전녹지지역":      {"건폐율": 20, "용적률": 80},
        "생산녹지지역":      {"건폐율": 20, "용적률": 100},
        "자연녹지지역":      {"건폐율": 20, "용적률": 100},
    },
    "세종특별자치시": {
        "제1종전용주거지역": {"건폐율": 50, "용적률": 100},
        "제2종전용주거지역": {"건폐율": 40, "용적률": 120},
        "제1종일반주거지역": {"건폐율": 60, "용적률": 150},
        "제2종일반주거지역": {"건폐율": 60, "용적률": 200},
        "제3종일반주거지역": {"건폐율": 50, "용적률": 250},
        "준주거지역":        {"건폐율": 60, "용적률": 400},
        "중심상업지역":      {"건폐율": 80, "용적률": 1300},
        "일반상업지역":      {"건폐율": 70, "용적률": 1100},
        "근린상업지역":      {"건폐율": 70, "용적률": 700},
        "유통상업지역":      {"건폐율": 70, "용적률": 900},
        "전용공업지역":      {"건폐율": 70, "용적률": 300},
        "일반공업지역":      {"건폐율": 70, "용적률": 350},
        "준공업지역":        {"건폐율": 70, "용적률": 400},
        "보전녹지지역":      {"건폐율": 20, "용적률": 80},
        "생산녹지지역":      {"건폐율": 20, "용적률": 100},
        "자연녹지지역":      {"건폐율": 20, "용적률": 100},
    },
}

NATIONAL_DEFAULT = {
    "제1종전용주거지역": {"건폐율": 50, "용적률": 100, "최고층수": 2},
    "제2종전용주거지역": {"건폐율": 50, "용적률": 150, "최고층수": 4},
    "제1종일반주거지역": {"건폐율": 60, "용적률": 200, "최고층수": 4},
    "제2종일반주거지역": {"건폐율": 60, "용적률": 250, "최고층수": 18},
    "제3종일반주거지역": {"건폐율": 50, "용적률": 300, "최고층수": 999},
    "준주거지역":        {"건폐율": 70, "용적률": 500, "최고층수": 999},
    "중심상업지역":      {"건폐율": 90, "용적률": 1500, "최고층수": 999},
    "일반상업지역":      {"건폐율": 80, "용적률": 1300, "최고층수": 999},
    "근린상업지역":      {"건폐율": 70, "용적률": 900, "최고층수": 999},
    "유통상업지역":      {"건폐율": 80, "용적률": 1100, "최고층수": 999},
    "전용공업지역":      {"건폐율": 70, "용적률": 300, "최고층수": 999},
    "일반공업지역":      {"건폐율": 70, "용적률": 350, "최고층수": 999},
    "준공업지역":        {"건폐율": 70, "용적률": 400, "최고층수": 999},
    "보전녹지지역":      {"건폐율": 20, "용적률": 80,  "최고층수": 999},
    "생산녹지지역":      {"건폐율": 20, "용적률": 100, "최고층수": 999},
    "자연녹지지역":      {"건폐율": 20, "용적률": 100, "최고층수": 999},
}

FLOOR_LIMIT = {
    "제1종전용주거지역": 2,
    "제2종전용주거지역": 4,
    "제1종일반주거지역": 4,
    "제2종일반주거지역": 18,
}

HEIGHT_LIMIT = {
    "제1종전용주거지역": {"절대높이": "9m 이하",  "일조권사선": True},
    "제2종전용주거지역": {"절대높이": "12m 이하", "일조권사선": True},
    "제1종일반주거지역": {"절대높이": "없음",      "일조권사선": True},
    "제2종일반주거지역": {"절대높이": "없음",      "일조권사선": True},
    "제3종일반주거지역": {"절대높이": "없음",      "일조권사선": True},
    "준주거지역":        {"절대높이": "없음",      "일조권사선": False},
}

ZONE_USE = {
    "제1종전용주거지역": {"허용": ["단독주택(다가구 제외)", "제1종근린생활시설(일부)"], "불허": ["공동주택", "제2종근린생활시설", "상업시설", "공장", "숙박시설", "위락시설"], "근거": "별표2"},
    "제2종전용주거지역": {"허용": ["단독주택", "공동주택(아파트 제외)", "제1종근린생활시설"], "불허": ["아파트", "상업시설", "공장", "숙박시설", "위락시설"], "근거": "별표3"},
    "제1종일반주거지역": {"허용": ["단독주택", "공동주택(아파트 제외)", "제1,2종근린생활시설", "학교"], "불허": ["아파트", "숙박시설", "위락시설", "공장"], "근거": "별표4"},
    "제2종일반주거지역": {"허용": ["단독주택", "공동주택(아파트 포함)", "제1,2종근린생활시설", "학교", "종교시설"], "불허": ["숙박시설", "위락시설", "공장"], "근거": "별표5"},
    "제3종일반주거지역": {"허용": ["단독주택", "공동주택(아파트 포함)", "제1,2종근린생활시설", "학교", "판매시설"], "불허": ["숙박시설", "위락시설", "공장"], "근거": "별표5"},
    "준주거지역":        {"허용": ["주택", "근린생활시설", "판매시설", "업무시설", "숙박시설(일부)"], "불허": ["위락시설", "공장(일부)"], "근거": "별표6"},
    "중심상업지역":      {"허용": ["근린생활시설", "판매시설", "업무시설", "숙박시설", "공동주택(일부)"], "불허": ["공장", "위험물저장처리시설"], "근거": "별표7"},
    "일반상업지역":      {"허용": ["근린생활시설", "판매시설", "업무시설", "숙박시설", "공동주택(일부)"], "불허": ["공장", "위험물저장처리시설"], "근거": "별표8"},
    "근린상업지역":      {"허용": ["근린생활시설", "판매시설(일부)", "업무시설(일부)", "의료시설"], "불허": ["위락시설", "공장", "숙박시설(일부)"], "근거": "별표9"},
    "전용공업지역":      {"허용": ["공장", "창고시설", "위험물저장처리시설"], "불허": ["주택", "상업시설", "의료시설"], "근거": "별표11"},
    "일반공업지역":      {"허용": ["공장", "창고시설", "근린생활시설(일부)"], "불허": ["주택(일부)", "위락시설"], "근거": "별표12"},
    "준공업지역":        {"허용": ["공장", "주택", "근린생활시설", "판매시설(일부)"], "불허": ["위락시설"], "근거": "별표13"},
    "보전녹지지역":      {"허용": ["단독주택(농가)", "농수산시설", "공공시설(일부)"], "불허": ["공동주택", "상업시설", "공장"], "근거": "별표14"},
    "생산녹지지역":      {"허용": ["단독주택", "농수산시설", "근린생활시설(일부)"], "불허": ["공동주택(일부)", "상업시설"], "근거": "별표15"},
    "자연녹지지역":      {"허용": ["단독주택", "공동주택(일부)", "근린생활시설", "의료시설(일부)"], "불허": ["숙박시설", "위락시설", "공장(일부)"], "근거": "별표16"},
}

PARKING_TABLE = {
    "단독주택":          {"기준": "50m²당 1대",  "calc_area": 50},
    "공동주택":          {"기준": "60m²당 1대",  "calc_area": 60},
    "제1종근린생활시설": {"기준": "134m²당 1대", "calc_area": 134},
    "제2종근린생활시설": {"기준": "134m²당 1대", "calc_area": 134},
    "업무시설":          {"기준": "150m²당 1대", "calc_area": 150},
    "판매시설":          {"기준": "150m²당 1대", "calc_area": 150},
    "의료시설":          {"기준": "100m²당 1대", "calc_area": 100},
    "운동시설":          {"기준": "150m²당 1대", "calc_area": 150},
    "공장":              {"기준": "350m²당 1대", "calc_area": 350},
}


def get_region(address):
    for r in ORDINANCE:
        short = r.replace("특별자치시","").replace("광역시","").replace("특별시","")
        if r in address or short in address:
            return r
    return None


def match_key(zone_name, table):
    clean = zone_name.replace(" ", "")
    for key in table:
        if key.replace(" ", "") in clean or clean in key.replace(" ", ""):
            return key
    return None


def get_coordinates(address):
    url = "https://api.vworld.kr/req/address"
    for t in ["parcel", "road"]:
        try:
            r = requests.get(url, params={
                "service": "address", "request": "getcoord",
                "key": LAND_API_KEY, "address": address,
                "type": t, "format": "json"
            }, timeout=10)
            pt = r.json()["response"]["result"]["point"]
            return float(pt["x"]), float(pt["y"])
        except:
            continue
    return None, None


def get_land_use(x, y):
    try:
        r = requests.get("https://api.vworld.kr/req/data", params={
            "service": "data", "request": "GetFeature",
            "data": "LT_C_UQ111", "key": LAND_API_KEY,
            "geomFilter": f"POINT({x} {y})",
            "geometry": "false", "attribute": "true",
            "format": "json", "size": "10"
        }, timeout=10)
        features = r.json()["response"]["result"]["featureCollection"]["features"]
        return [f["properties"].get("uname", "") for f in features if f["properties"].get("uname")]
    except:
        return []


def get_district_plan(x, y):
    try:
        r = requests.get("https://api.vworld.kr/req/data", params={
            "service": "data", "request": "GetFeature",
            "data": "LT_C_UQ112", "key": LAND_API_KEY,
            "geomFilter": f"POINT({x} {y})",
            "geometry": "false", "attribute": "true",
            "format": "json", "size": "10"
        }, timeout=10)
        features = r.json()["response"]["result"]["featureCollection"]["features"]
        return [f["properties"].get("uname", "") for f in features if f["properties"].get("uname")]
    except:
        return []


class AnalyzeRequest(BaseModel):
    address: str
    area: float = None
    plan: dict = None


@app.get("/")
def root():
    return FileResponse("index.html")


@app.get("/health")
def health():
    return {"status": "ok", "message": "건축법규 조회 API"}


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    address   = req.address
    site_area = req.area
    plan      = req.plan

    x, y = get_coordinates(address)
    if not x:
        return {"error": f"주소를 찾을 수 없습니다: {address}"}

    zones     = get_land_use(x, y)
    districts = get_district_plan(x, y)

    if not zones:
        return {"error": "용도지역 조회 실패. 잠시 후 다시 시도해주세요."}

    zone_name = zones[0]
    region    = get_region(address)

    bc_ratio = far_ratio = None
    ordinance_label = "국토계획법 시행령 (참고용)"
    zone_key = None

    if region and region in ORDINANCE:
        zone_key = match_key(zone_name, ORDINANCE[region])
        if zone_key:
            bc_ratio        = ORDINANCE[region][zone_key]["건폐율"]
            far_ratio       = ORDINANCE[region][zone_key]["용적률"]
            ordinance_label = f"{region} 도시계획 조례"

    if bc_ratio is None:
        nk = match_key(zone_name, NATIONAL_DEFAULT)
        if nk:
            bc_ratio  = NATIONAL_DEFAULT[nk]["건폐율"]
            far_ratio = NATIONAL_DEFAULT[nk]["용적률"]

    use_key   = match_key(zone_name, ZONE_USE)
    max_floor = FLOOR_LIMIT.get(zone_key or use_key or "", 999)
    h_info    = HEIGHT_LIMIT.get(zone_key or use_key or "", {"절대높이": "없음", "일조권사선": True})
    use_info  = ZONE_USE.get(use_key, {"허용": [], "불허": [], "근거": ""})

    max_bc  = round(site_area * bc_ratio  / 100, 2) if site_area and bc_ratio  else None
    max_far = round(site_area * far_ratio / 100, 2) if site_area and far_ratio else None

    parking_result = {}
    if max_far:
        for use_nm, info in PARKING_TABLE.items():
            parking_result[use_nm] = {
                "대수": max(1, int(max_far / info["calc_area"])),
                "기준": info["기준"]
            }

    result = {
        "용도지역":     zone_name,
        "지구단위계획": districts,
        "건폐율":       bc_ratio,
        "용적률":       far_ratio,
        "ordinance":    ordinance_label,
        "최대건축면적": max_bc,
        "최대연면적":   max_far,
        "절대높이":     h_info.get("절대높이", "없음"),
        "일조권사선":   h_info.get("일조권사선", True),
        "최고층수":     max_floor,
        "허용용도":     use_info["허용"],
        "불허용도":     use_info["불허"],
        "용도근거":     use_info["근거"],
        "주차기준":     parking_result,
        "계획검토":     None,
    }

    if plan:
        ba     = plan.get("건축면적")
        gfa    = plan.get("연면적")
        height = plan.get("건물높이")
        floors = plan.get("지상층수")
        bfloor = plan.get("지하층수", 0)
        road_w = plan.get("접도폭원")
        use    = plan.get("주용도")
        prk    = plan.get("계획주차대수")

        review = {}

        if site_area and bc_ratio and ba:
            max_bc_v = site_area * bc_ratio / 100
            review["건축면적"] = {
                "계획": ba, "건폐율": round(ba/site_area*100,1),
                "ok": ba <= max_bc_v, "여유": round(max_bc_v - ba, 2)
            }

        if site_area and far_ratio and gfa:
            max_far_v = site_area * far_ratio / 100
            review["연면적"] = {
                "계획": gfa, "용적률": round(gfa/site_area*100,1),
                "ok": gfa <= max_far_v, "여유": round(max_far_v - gfa, 2)
            }

        if height:
            ah = h_info.get("절대높이", "없음")
            if "없음" not in ah:
                lim = int("".join(filter(str.isdigit, ah)))
                review["절대높이"] = {"계획": height, "허용": ah, "ok": height <= lim}

        if floors:
            review["층수"] = {
                "계획": floors,
                "허용": str(max_floor) if max_floor < 999 else "제한없음",
                "ok": floors <= max_floor
            }

        if height and h_info.get("일조권사선"):
            review["일조권사선"] = {"최소이격": round(height/2, 1)}

        if height and road_w:
            allow_h = road_w * 1.5 + 4
            review["도로사선"] = {
                "계획높이": height, "허용높이": allow_h, "ok": height <= allow_h
            }

        if use and use_info:
            cu = use.replace(" ", "")
            is_allow = any(cu in a.replace(" ","") or a.replace(" ","") in cu for a in use_info["허용"])
            is_deny  = any(cu in d.replace(" ","") or d.replace(" ","") in cu for d in use_info["불허"])
            review["용도"] = {
                "계획": use, "ok": is_allow and not is_deny,
                "상태": "불허" if is_deny else ("허용" if is_allow else "확인필요")
            }

        if gfa:
            cu = (use or "").replace(" ", "")
            matched = None
            for k, v in PARKING_TABLE.items():
                if k.replace(" ","") in cu or cu in k.replace(" ",""):
                    matched = (k, v); break
            if not matched:
                matched = ("공동주택", PARKING_TABLE["공동주택"])
            pk_nm, pk_info = matched
            legal = max(1, int(gfa / pk_info["calc_area"]))
            review["주차"] = {
                "법정": legal, "기준": pk_info["기준"],
                "계획": prk, "ok": prk >= legal if prk is not None else None
            }

        result["계획검토"] = review

    return {"address": address, "area": site_area, "results": [result]}
