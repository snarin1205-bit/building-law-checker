import requests
import sys

LAND_API_KEY = "6F8D2670-8C8E-3958-AE79-9645DCE6BB0F"

BLUE   = "\033[94m"
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def get_coordinates(address):
    url = "https://api.vworld.kr/req/address"
    params = {"service":"address","request":"getcoord","key":LAND_API_KEY,"address":address,"type":"parcel","format":"json"}
    data = requests.get(url, params=params).json()
    try:
        x = data["response"]["result"]["point"]["x"]
        y = data["response"]["result"]["point"]["y"]
        return x, y
    except:
        print("주소를 찾을 수 없습니다: " + address)
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
                results.append({"용도지역": name})
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
    "중심상업지역":      {"건폐율": 90, "용적률": 1500, "최고층수": 999},
    "일반상업지역":      {"건폐율": 80, "용적률": 1300, "최고층수": 999},
    "근린상업지역":      {"건폐율": 70, "용적률": 900,  "최고층수": 999},
    "전용공업지역":      {"건폐율": 70, "용적률": 300,  "최고층수": 999},
    "일반공업지역":      {"건폐율": 70, "용적률": 350,  "최고층수": 999},
    "준공업지역":        {"건폐율": 70, "용적률": 400,  "최고층수": 999},
    "보전녹지지역":      {"건폐율": 20, "용적률": 80,   "최고층수": 999},
    "생산녹지지역":      {"건폐율": 20, "용적률": 100,  "최고층수": 999},
    "자연녹지지역":      {"건폐율": 20, "용적률": 100,  "최고층수": 999},
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
    "제2종전용주거지역": {"허용": ["단독주택", "공동주택(아파트 제외)", "제1종 근린생활시설(일부)", "학교", "노유자시설"], "불허": ["아파트", "숙박시설", "위락시설", "공장"], "별표": "별표3"},
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

# 도로사선 제한 계산 (건축법 제61조 제2항)
# 도로 반대편 경계선까지의 수평거리 × 1.5 = 허용 높이
def calc_road_oblique(road_width):
    return round((road_width / 2 + road_width) * 1.5, 1)

# 일조권 사선제한 계산 (건축법 제61조 제1항)
# 정북방향 인접대지경계선으로부터 높이 × 0.5 이격
def calc_sunlight_oblique(building_height):
    return round(building_height * 0.5, 1)

def match_zone(zone_name, table):
    clean = zone_name.replace(" ", "")
    for key, val in table.items():
        if key.replace(" ", "") in clean or clean in key.replace(" ", ""):
            return val
    return None

def ok(msg):
    return GREEN + "✅ OK  " + RESET + msg

def ng(msg):
    return RED + "❌ NG  " + RESET + msg

def warn(msg):
    return YELLOW + "⚠️  검토 " + RESET + msg

def h(text):
    return BOLD + BLUE + text + RESET

def check_building_law(address, site_area, plan):
    x, y = get_coordinates(address)
    if not x:
        return
    zones = get_land_use(x, y)
    districts = get_district_plan(x, y)

    print("")
    print(BOLD + "=" * 65 + RESET)
    print(BOLD + "  📍 분석 주소: " + RESET + address)
    if site_area:
        print(BOLD + "  대지면적:    " + RESET + str(site_area) + " m²  (" + str(round(site_area/3.3058,1)) + " 평)")
    print(BOLD + "=" * 65 + RESET)

    for zone in zones:
        zone_name = zone["용도지역"]
        ratio  = match_zone(zone_name, ZONE_TABLE)
        height = match_zone(zone_name, HEIGHT_TABLE)
        uses   = match_zone(zone_name, USE_TABLE)

        # ──────────────────────────────────────
        print("")
        print(h("## 1. 용도지역 및 지구"))
        print("- [x] 용도지역: " + GREEN + zone_name + RESET + "  (국토계획법 제36조)")
        if districts:
            for d in districts:
                print("- [x] 지구단위계획: " + GREEN + d + RESET + "  ※ 별도 완화기준 적용 가능")
        else:
            print("- [ ] 지구단위계획: 해당 없음")

        # ──────────────────────────────────────
        if ratio and site_area:
            max_bc  = round(site_area * ratio["건폐율"] / 100, 2)
            max_far = round(site_area * ratio["용적률"] / 100, 2)

            print("")
            print(h("## 2. 규모 검토"))

            # 건축면적 검토
            if plan.get("건축면적"):
                bc_rate = round(plan["건축면적"] / site_area * 100, 1)
                if plan["건축면적"] <= max_bc:
                    print("- " + ok("건축면적: " + str(plan["건축면적"]) + " m²  →  건폐율 " + str(bc_rate) + "% (허용 " + str(ratio["건폐율"]) + "% 이하)  여유 " + str(round(max_bc - plan["건축면적"],1)) + " m²"))
                else:
                    over = round(plan["건축면적"] - max_bc, 1)
                    print("- " + ng("건축면적: " + str(plan["건축면적"]) + " m²  →  건폐율 " + str(bc_rate) + "% (허용 " + str(ratio["건폐율"]) + "% 초과!)  " + str(over) + " m² 초과"))
                print("       근거: 국토계획법 시행령 제84조 | https://www.law.go.kr/법령/국토의계획및이용에관한법률시행령")
            else:
                print("- [ ] 건축면적: 미입력  →  최대 " + GREEN + str(max_bc) + " m²" + RESET + " (" + str(ratio["건폐율"]) + "%) 가능")

            # 연면적 검토
            if plan.get("연면적"):
                far_rate = round(plan["연면적"] / site_area * 100, 1)
                if plan["연면적"] <= max_far:
                    print("- " + ok("연면적: " + str(plan["연면적"]) + " m²  →  용적률 " + str(far_rate) + "% (허용 " + str(ratio["용적률"]) + "% 이하)  여유 " + str(round(max_far - plan["연면적"],1)) + " m²"))
                else:
                    over = round(plan["연면적"] - max_far, 1)
                    print("- " + ng("연면적: " + str(plan["연면적"]) + " m²  →  용적률 " + str(far_rate) + "% (허용 " + str(ratio["용적률"]) + "% 초과!)  " + str(over) + " m² 초과"))
                print("       근거: 국토계획법 시행령 제85조 | https://www.law.go.kr/법령/국토의계획및이용에관한법률시행령")
            else:
                print("- [ ] 연면적: 미입력  →  최대 " + GREEN + str(max_far) + " m²" + RESET + " (" + str(ratio["용적률"]) + "%) 가능")

        # ──────────────────────────────────────
        if height:
            print("")
            print(h("## 3. 높이 및 층수 검토"))

            # 절대높이
            if height["절대높이"] > 0:
                if plan.get("건물높이"):
                    if plan["건물높이"] <= height["절대높이"]:
                        print("- " + ok("건물높이: " + str(plan["건물높이"]) + "m  →  절대높이 " + str(height["절대높이"]) + "m 이하 만족"))
                    else:
                        over = round(plan["건물높이"] - height["절대높이"], 1)
                        print("- " + ng("건물높이: " + str(plan["건물높이"]) + "m  →  절대높이 " + str(height["절대높이"]) + "m 초과!  " + str(over) + "m 초과"))
                    print("       근거: 건축법 시행령 제82조 | https://www.law.go.kr/법령/건축법시행령")
                else:
                    print("- [!] 절대높이: " + YELLOW + str(height["절대높이"]) + "m 이하" + RESET + " 제한 있음  (건축법 시행령 제82조)")
            else:
                print("- " + ok("절대높이: 제한 없음  (용적률로 관리)"))

            # 층수 검토
            if ratio and plan.get("지상층수"):
                max_floors = ratio.get("최고층수", 999)
                if max_floors < 999:
                    if plan["지상층수"] <= max_floors:
                        print("- " + ok("지상층수: " + str(plan["지상층수"]) + "층  →  최고 " + str(max_floors) + "층 이하 만족"))
                    else:
                        print("- " + ng("지상층수: " + str(plan["지상층수"]) + "층  →  최고 " + str(max_floors) + "층 초과!"))
                    print("       근거: 국토계획법 시행령 | https://www.law.go.kr/법령/국토의계획및이용에관한법률시행령")
                else:
                    print("- " + ok("지상층수: " + str(plan["지상층수"]) + "층  →  층수 제한 없음"))

            if plan.get("지하층수"):
                print("- [x] 지하층수: " + str(plan["지하층수"]) + "층  →  용도지역 층수제한 적용 제외")

            # 일조권 사선제한
            if height["일조권사선"] and plan.get("건물높이"):
                required_setback = calc_sunlight_oblique(plan["건물높이"])
                print("- " + warn("일조권 사선제한 적용  →  정북방향 인접대지경계선에서 최소 " + str(required_setback) + "m 이격 필요"))
                print("       근거: 건축법 제61조 제1항 | https://www.law.go.kr/법령/건축법")
            elif not height["일조권사선"]:
                print("- " + ok("일조권 사선제한: 해당 없음  (" + zone_name + " 적용 제외)"))
                print("       근거: 건축법 제61조 제1항 | https://www.law.go.kr/법령/건축법")

            # 도로사선 제한
            if plan.get("접도폭원") and plan.get("건물높이"):
                allowed_height = calc_road_oblique(plan["접도폭원"])
                if plan["건물높이"] <= allowed_height:
                    print("- " + ok("도로사선: 건물높이 " + str(plan["건물높이"]) + "m  →  도로 " + str(plan["접도폭원"]) + "m 기준 허용높이 " + str(allowed_height) + "m 이하 만족"))
                else:
                    print("- " + ng("도로사선: 건물높이 " + str(plan["건물높이"]) + "m  →  도로 " + str(plan["접도폭원"]) + "m 기준 허용높이 " + str(allowed_height) + "m 초과!"))
                print("       근거: 건축법 제61조 제2항 | https://www.law.go.kr/법령/건축법")
            elif plan.get("접도폭원"):
                allowed_height = calc_road_oblique(plan["접도폭원"])
                print("- " + warn("도로사선: 접도 " + str(plan["접도폭원"]) + "m 기준 허용높이 최대 " + str(allowed_height) + "m"))
                print("       근거: 건축법 제61조 제2항 | https://www.law.go.kr/법령/건축법")

        # ──────────────────────────────────────
        if uses and plan.get("주용도"):
            print("")
            print(h("## 4. 용도 적합성 검토"))
            allowed = any(plan["주용도"] in u or u in plan["주용도"] for u in uses["허용"])
            denied  = any(plan["주용도"] in u or u in plan["주용도"] for u in uses["불허"])
            if denied:
                print("- " + ng("주용도 '" + plan["주용도"] + "'  →  " + zone_name + " 불허 용도!"))
            elif allowed:
                print("- " + ok("주용도 '" + plan["주용도"] + "'  →  " + zone_name + " 허용 용도"))
            else:
                print("- " + warn("주용도 '" + plan["주용도"] + "'  →  허용 여부 별도 확인 필요"))
            print("       근거: 국토계획법 시행령 " + uses["별표"] + " | https://www.law.go.kr/법령/국토의계획및이용에관한법률시행령")

        # ──────────────────────────────────────
        print("")
        print(h("## 5. 주차대수 검토"))
        print("       근거: 주차장법 시행령 별표1 | https://www.law.go.kr/법령/주차장법시행령")

        calc_area = plan.get("연면적") or (site_area * ratio["용적률"] / 100 if ratio and site_area else 0)
        if plan.get("주용도") and calc_area:
            # 주용도에 맞는 주차기준 찾기
            matched_parking = None
            for key, val in PARKING_TABLE.items():
                if plan["주용도"] in key or key in plan["주용도"]:
                    matched_parking = (key, val)
                    break

            if matched_parking:
                use_name, p_info = matched_parking
                legal_count = p_info["계산"](calc_area)
                if plan.get("계획주차대수"):
                    if plan["계획주차대수"] >= legal_count:
                        print("- " + ok("계획 " + str(plan["계획주차대수"]) + "대  ≥  법정 " + str(legal_count) + "대 (" + p_info["기준"] + ")  여유 " + str(plan["계획주차대수"] - legal_count) + "대"))
                    else:
                        short = legal_count - plan["계획주차대수"]
                        print("- " + ng("계획 " + str(plan["계획주차대수"]) + "대  <  법정 " + str(legal_count) + "대 (" + p_info["기준"] + ")  " + str(short) + "대 부족!"))
                else:
                    print("- [x] 법정주차대수: " + GREEN + str(legal_count) + "대" + RESET + " (" + p_info["기준"] + ", 연면적 " + str(calc_area) + "m² 기준)")
            else:
                # 전체 용도별 출력
                for use, info in PARKING_TABLE.items():
                    count = info["계산"](calc_area)
                    print("- [x] " + use + ": " + GREEN + str(count) + "대" + RESET + "  (" + info["기준"] + ")")

        print("")
        print("  ※ 지자체 조례에 따라 달라질 수 있음")
        print("  ※ 일조권/도로사선은 정확한 검토를 위해 배치도 검토 필요")

    print(BOLD + "=" * 65 + RESET)

if __name__ == "__main__":
    # ────────────────────────────────────────────
    # 토지 정보
    address   = "대전광역시 유성구 반석동 644-4"
    site_area = 330.0  # 대지면적 (m²)

    # ────────────────────────────────────────────
    # 계획 건물 정보 (없으면 None)
    plan = {
        "주용도":      "공동주택",   # 계획 주용도
        "건축면적":    180.0,        # 계획 건축면적 (m²)
        "연면적":      750.0,        # 계획 연면적 (m²)
        "건물높이":    40.0,         # 계획 건물높이 (m)
        "지상층수":    12,           # 지상 층수
        "지하층수":    2,            # 지하 층수
        "접도폭원":    8.0,          # 접하는 도로 폭원 (m)
        "계획주차대수": 15,          # 계획 주차대수 (대)
    }
    # ────────────────────────────────────────────

    check_building_law(address, site_area, plan)
