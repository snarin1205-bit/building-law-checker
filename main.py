from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

LAND_API_KEY = "6F8D2670-8C8E-3958-AE79-9645DCE6BB0F"

class QueryRequest(BaseModel):
    address: str
    area: float = None
    plan: dict = None

def get_coordinates(address):
    url = "https://api.vworld.kr/req/address"
    params = {"service":"address","request":"getcoord","key":LAND_API_KEY,"address":address,"type":"parcel","format":"json"}
    data = requests.get(url, params=params).json()
    try:
        x = data["response"]["result"]["point"]["x"]
        y = data["response"]["result"]["point"]["y"]
        return x, y
    except:
        return None, None

def get_land_use(x, y):
    url = "https://api.vworld.kr/req/data"
    params = {"service":"data","request":"GetFeature","data":"LT_C_UQ111","key":LAND_API_KEY,"geomFilter":"POINT("+str(x)+" "+str(y)+")","geometry":"false","attribute":"true","format":"json","size":"10"}
    data = requests.get(url, params=params).json()
    results = []
    try:
        for f in data["response"]["result"]["featureCollection"]["features"]:
            name = f["properties"].get("uname","")
            if name:
                results.append(name)
    except:
        pass
    return results

def get_district_plan(x, y):
    url = "https://api.vworld.kr/req/data"
    params = {"service":"data","request":"GetFeature","data":"LT_C_UQ112","key":LAND_API_KEY,"geomFilter":"POINT("+str(x)+" "+str(y)+")","geometry":"false","attribute":"true","format":"json","size":"10"}
    data = requests.get(url, params=params).json()
    results = []
    try:
        for f in data["response"]["result"]["featureCollection"]["features"]:
            name = f["properties"].get("uname","")
            if name:
                results.append(name)
    except:
        pass
    return results

ZONE_TABLE = {
    "제1종전용주거지역": {"건폐율": 50, "용적률": 100, "최고층수": 2},
    "제2종전용주거지역": {"건폐율": 50, "용적률": 150, "최고층수": 4},
    "제1종일반주거지역": {"건폐율": 60, "용적률": 200, "최고층수": 4},
    "제2종일반주거지역": {"건폐율": 60, "용적률": 250, "최고층수": 18},
    "제3종일반주거지역": {"건폐율": 50, "용적률": 300, "최고층수": 999},
    "준주거지역":        {"건폐율": 70, "용적률": 500, "최고층수": 999},
    "중심상업지역":      {"건폐율": 90, "용적률": 1500,"최고층수": 999},
    "일반상업지역":      {"건폐율": 80, "용적률": 1300,"최고층수": 999},
    "근린상업지역":      {"건폐율": 70, "용적률": 900, "최고층수": 999},
    "전용공업지역":      {"건폐율": 70, "용적률": 300, "최고층수": 999},
    "일반공업지역":      {"건폐율": 70, "용적률": 350, "최고층수": 999},
    "준공업지역":        {"건폐율": 70, "용적률": 400, "최고층수": 999},
    "보전녹지지역":      {"건폐율": 20, "용적률": 80,  "최고층수": 999},
    "생산녹지지역":      {"건폐율": 20, "용적률": 100, "최고층수": 999},
    "자연녹지지역":      {"건폐율": 20, "용적률": 100, "최고층수": 999},
}

HEIGHT_TABLE = {
    "제1종전용주거지역": {"절대높이": 9,  "일조권사선": True,  "도로사선": True},
    "제2종전용주거지역": {"절대높이": 12, "일조권사선": True,  "도로사선": True},
    "제1종일반주거지역": {"절대높이": 0,  "일조권사선": True,  "도로사선": True},
    "제2종일반주거지역": {"절대높이": 0,  "일조권사선": True,  "도로사선": True},
    "제3종일반주거지역": {"절대높이": 0,  "일조권사선": True,  "도로사선": True},
    "준주거지역":        {"절대높이": 0,  "일조권사선": False, "도로사선": True},
    "중심상업지역":      {"절대높이": 0,  "일조권사선": False, "도로사선": True},
    "일반상업지역":      {"절대높이": 0,  "일조권사선": False, "도로사선": True},
    "근린상업지역":      {"절대높이": 0,  "일조권사선": False, "도로사선": True},
    "전용공업지역":      {"절대높이": 0,  "일조권사선": False, "도로사선": True},
    "일반공업지역":      {"절대높이": 0,  "일조권사선": False, "도로사선": True},
    "준공업지역":        {"절대높이": 0,  "일조권사선": False, "도로사선": True},
    "보전녹지지역":      {"절대높이": 0,  "일조권사선": True,  "도로사선": True},
    "생산녹지지역":      {"절대높이": 0,  "일조권사선": True,  "도로사선": True},
    "자연녹지지역":      {"절대높이": 0,  "일조권사선": True,  "도로사선": True},
}

USE_TABLE = {
    "제1종전용주거지역": {"허용": ["단독주택", "제1종 근린생활시설(일부)", "유치원/초중고", "노유자시설"], "불허": ["아파트", "숙박시설", "위락시설", "공장"], "별표": "별표2"},
    "제2종전용주거지역": {"허용": ["단독주택", "공동주택(아파트 제외)", "제1종 근린생활시설(일부)", "학교"], "불허": ["아파트", "숙박시설", "위락시설", "공장"], "별표": "별표3"},
    "제1종일반주거지역": {"허용": ["단독주택", "공동주택(4층 이하)", "제1종 근린생활시설", "학교", "종교시설"], "불허": ["아파트(5층 이상)", "숙박시설", "위락시설", "공장"], "별표": "별표4"},
    "제2종일반주거지역": {"허용": ["단독주택", "공동주택(아파트 포함)", "제1,2종 근린생활시설", "학교", "종교시설", "판매시설(일부)"], "불허": ["숙박시설", "위락시설", "공장", "대형 판매시설"], "별표": "별표5"},
    "제3종일반주거지역": {"허용": ["단독주택", "공동주택", "제1,2종 근린생활시설", "학교", "판매시설(일부)", "업무시설(일부)"], "불허": ["숙박시설", "위락시설", "공장"], "별표": "별표6"},
    "준주거지역":        {"허용": ["주거시설 전반", "근린생활시설", "판매시설", "업무시설", "숙박시설(일부)"], "불허": ["위락시설", "공장(일부)", "위험물저장시설"], "별표": "별표7"},
    "중심상업지역":      {"허용": ["근린생활시설", "판매시설", "업무시설", "숙박시설", "위락시설"], "불허": ["공장(일부)", "위험물저장시설", "묘지관련시설"], "별표": "별표8"},
    "일반상업지역":      {"허용": ["근린생활시설", "판매시설", "업무시설", "숙박시설"], "불허": ["공장(일부)", "위험물저장시설"], "별표": "별표9"},
    "근린상업지역":      {"허용": ["단독주택", "공동주택", "근린생활시설", "판매시설(일부)"], "불허": ["대형 판매시설", "위락시설", "공장"], "별표": "별표10"},
    "전용공업지역":      {"허용": ["공장", "창고시설", "위험물저장시설"], "불허": ["주거시설", "학교", "의료시설", "판매시설"], "별표": "별표12"},
    "일반공업지역":      {"허용": ["공장", "창고시설", "근린생활시설(일부)", "주거시설(일부)"], "불허": ["대규모 주거시설", "위락시설"], "별표": "별표13"},
    "준공업지역":        {"허용": ["공장", "근린생활시설", "업무시설", "주거시설(일부)"], "불허": ["위락시설", "대형 위험물시설"], "별표": "별표14"},
    "보전녹지지역":      {"허용": ["단독주택(일부)", "농업/임업 시설", "종교시설(일부)"], "불허": ["공동주택", "공장", "판매시설", "위락시설"], "별표": "별표15"},
    "생산녹지지역":      {"허용": ["단독주택", "농업/임업 시설", "창고(농업용)"], "불허": ["공동주택(일부)", "공장", "위락시설"], "별표": "별표16"},
    "자연녹지지역":      {"허용": ["단독주택", "공동주택(일부)", "제1종 근린생활시설", "농업/임업 시설"], "불허": ["대형 공동주택", "공장(일부)", "위락시설"], "별표": "별표17"},
}

PARKING_TABLE = {
    "단독주택":          {"기준": "50m²당 1대", "계산": lambda a: max(1, int(a/50)) if a > 50 else 0},
    "공동주택":          {"기준": "60m²당 1대", "계산": lambda a: max(1, int(a/60))},
    "제1종근린생활시설": {"기준": "134m²당 1대", "계산": lambda a: max(1, int(a/134))},
    "제2종근린생활시설": {"기준": "134m²당 1대", "계산": lambda a: max(1, int(a/134))},
    "업무시설":          {"기준": "150m²당 1대", "계산": lambda a: max(1, int(a/150))},
    "판매시설":          {"기준": "150m²당 1대", "계산": lambda a: max(1, int(a/150))},
    "의료시설":          {"기준": "100m²당 1대", "계산": lambda a: max(1, int(a/100))},
    "운동시설":          {"기준": "150m²당 1대", "계산": lambda a: max(1, int(a/150))},
    "공장":              {"기준": "350m²당 1대", "계산": lambda a: max(1, int(a/350))},
}

def match_zone(zone_name, table):
    clean = zone_name.replace(" ", "")
    for key, val in table.items():
        if key.replace(" ", "") in clean or clean in key.replace(" ", ""):
            return val
    return None

def calc_road_oblique(road_width):
    return round((road_width / 2 + road_width) * 1.5, 1)

def calc_sunlight_oblique(building_height):
    return round(building_height * 0.5, 1)

@app.post("/analyze")
def analyze(req: QueryRequest):
    x, y = get_coordinates(req.address)
    if not x:
        return {"error": "주소를 찾을 수 없습니다."}

    zones     = get_land_use(x, y)
    districts = get_district_plan(x, y)

    if not zones:
        return {"error": "용도지역 조회 실패. 잠시 후 다시 시도해주세요."}

    results = []
    for zone_name in zones:
        ratio  = match_zone(zone_name, ZONE_TABLE)
        height = match_zone(zone_name, HEIGHT_TABLE)
        uses   = match_zone(zone_name, USE_TABLE)

        max_bc  = round(req.area * ratio["건폐율"] / 100, 2) if ratio and req.area else None
        max_far = round(req.area * ratio["용적률"] / 100, 2) if ratio and req.area else None

        parking_base = {}
        if max_far:
            for use, info in PARKING_TABLE.items():
                parking_base[use] = {"대수": info["계산"](max_far), "기준": info["기준"]}

        plan_review = None
        if req.plan:
            p = req.plan
            plan_review = {}

            if p.get("건축면적") and max_bc:
                bc_rate = round(p["건축면적"] / req.area * 100, 1)
                plan_review["건축면적"] = {
                    "계획": p["건축면적"], "허용": max_bc, "건폐율": bc_rate,
                    "ok": p["건축면적"] <= max_bc,
                    "여유": round(max_bc - p["건축면적"], 1)
                }

            if p.get("연면적") and max_far:
                far_rate = round(p["연면적"] / req.area * 100, 1)
                plan_review["연면적"] = {
                    "계획": p["연면적"], "허용": max_far, "용적률": far_rate,
                    "ok": p["연면적"] <= max_far,
                    "여유": round(max_far - p["연면적"], 1)
                }

            if p.get("지상층수") and ratio:
                max_fl = ratio.get("최고층수", 999)
                plan_review["층수"] = {
                    "계획": p["지상층수"],
                    "허용": max_fl if max_fl < 999 else "제한없음",
                    "ok": p["지상층수"] <= max_fl
                }

            if p.get("건물높이") and height:
                plan_review["절대높이"] = {
                    "계획": p["건물높이"],
                    "허용": str(height["절대높이"]) + "m 이하" if height["절대높이"] > 0 else "제한없음",
                    "ok": height["절대높이"] == 0 or p["건물높이"] <= height["절대높이"]
                }
                if height["일조권사선"]:
                    plan_review["일조권사선"] = {
                        "필요": True,
                        "최소이격": calc_sunlight_oblique(p["건물높이"])
                    }
                if p.get("접도폭원"):
                    allowed_h = calc_road_oblique(p["접도폭원"])
                    plan_review["도로사선"] = {
                        "계획높이": p["건물높이"], "허용높이": allowed_h,
                        "ok": p["건물높이"] <= allowed_h
                    }

            if p.get("주용도") and uses:
                allowed = any(p["주용도"] in u or u in p["주용도"] for u in uses["허용"])
                denied  = any(p["주용도"] in u or u in p["주용도"] for u in uses["불허"])
                plan_review["용도"] = {
                    "계획": p["주용도"],
                    "ok": allowed and not denied,
                    "상태": "불허" if denied else ("허용" if allowed else "확인필요")
                }

            calc_area = p.get("연면적") or max_far or 0
            if p.get("주용도") and calc_area:
                for key, val in PARKING_TABLE.items():
                    if p["주용도"] in key or key in p["주용도"]:
                        legal = val["계산"](calc_area)
                        plan_review["주차"] = {
                            "법정": legal, "계획": p.get("계획주차대수"),
                            "기준": val["기준"],
                            "ok": p.get("계획주차대수", 0) >= legal if p.get("계획주차대수") else None
                        }
                        break

        results.append({
            "용도지역": zone_name,
            "지구단위계획": districts,
            "건폐율": ratio["건폐율"] if ratio else None,
            "용적률": ratio["용적률"] if ratio else None,
            "최대건축면적": max_bc,
            "최대연면적": max_far,
            "최고층수": ratio.get("최고층수") if ratio else None,
            "높이제한": {
                "절대높이": str(height["절대높이"]) + "m 이하" if height and height["절대높이"] > 0 else "없음",
                "일조권사선": height["일조권사선"] if height else None,
                "도로사선": height["도로사선"] if height else None,
            } if height else None,
            "허용용도": uses["허용"] if uses else [],
            "불허용도": uses["불허"] if uses else [],
            "용도근거": uses["별표"] if uses else "",
            "주차기준": parking_base,
            "계획검토": plan_review,
        })

    return {"address": req.address, "area": req.area, "results": results}

@app.get("/")
def root():
    return {"status": "ok", "message": "건축법규 조회 API"}
