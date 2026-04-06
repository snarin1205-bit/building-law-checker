import streamlit as st
from building_law_checker import (
    ORDINANCE, NATIONAL_DEFAULT, FLOOR_LIMIT, HEIGHT_LIMIT,
    ZONE_USE, PARKING_TABLE,
    get_region, get_coordinates, get_land_use, get_district_plan,
    match_key
)

st.set_page_config(
    page_title="건축법규 자동조회",
    page_icon="🏢",
    layout="centered"
)

st.title("🏢 건축법규 자동조회 시스템")
st.caption("주소를 입력하면 용도지역, 건폐율, 용적률 등 건축 법규를 자동으로 조회해드립니다.")

st.divider()

# ── 1단계 입력 ──
st.subheader("📍 기본 정보 입력")
address = st.text_input(
    "주소",
    placeholder="예) 서울특별시 강남구 테헤란로 123",
    help="도로명 주소 또는 지번 주소 모두 가능합니다."
)

site_area = st.number_input(
    "대지면적 (m²) — 선택사항",
    min_value=0.0, value=0.0, step=1.0,
    help="입력 시 최대 건축 가능 면적을 계산해드립니다."
)
if site_area == 0.0:
    site_area = None

st.divider()

# ── 2단계 입력 ──
st.subheader("🏗️ 계획 건물 정보 입력 — 선택사항")
st.caption("입력하면 법규 적합 여부(OK/NG)를 자동으로 검토해드립니다.")

use_2nd = st.toggle("계획 건물 정보 입력하기")

plan = None
if use_2nd:
    col1, col2 = st.columns(2)
    with col1:
        p_use    = st.text_input("주용도", placeholder="예) 공동주택, 업무시설")
        p_ba     = st.number_input("건축면적 (m²)", min_value=0.0, value=0.0, step=1.0)
        p_gfa    = st.number_input("연면적 (m²)", min_value=0.0, value=0.0, step=1.0)
        p_height = st.number_input("건물높이 (m)", min_value=0.0, value=0.0, step=0.5)
    with col2:
        p_floors = st.number_input("지상층수", min_value=0, value=0, step=1)
        p_bfloor = st.number_input("지하층수", min_value=0, value=0, step=1)
        p_road   = st.number_input("접도폭원 — 접한 도로 너비 (m)", min_value=0.0, value=0.0, step=0.5)
        p_prk    = st.number_input("계획 주차대수 (대)", min_value=0, value=0, step=1)

    plan = {}
    if p_use:    plan["주용도"]       = p_use
    if p_ba:     plan["건축면적"]     = p_ba
    if p_gfa:    plan["연면적"]       = p_gfa
    if p_height: plan["건물높이"]     = p_height
    if p_floors: plan["지상층수"]     = p_floors
    if p_bfloor: plan["지하층수"]     = p_bfloor
    if p_road:   plan["접도폭원"]     = p_road
    if p_prk:    plan["계획주차대수"] = p_prk
    if not plan: plan = None

st.divider()

# ── 조회 버튼 ──
if st.button("🔍 법규 조회", type="primary", use_container_width=True):
    if not address.strip():
        st.warning("주소를 입력해주세요.")
    else:
        with st.spinner("조회 중..."):

            x, y = get_coordinates(address)

            if not x:
                st.error("❌ 주소를 찾을 수 없습니다. 정확한 주소를 입력해주세요.")
            else:
                zones     = get_land_use(x, y)
                districts = get_district_plan(x, y)

                if not zones:
                    st.error("❌ 용도지역 조회에 실패했습니다. 잠시 후 다시 시도해주세요.")
                else:
                    zone_name = zones[0]
                    region    = get_region(address)

                    bc_ratio = far_ratio = None
                    ordinance_label = ""
                    zone_key = None

                    if region and region in ORDINANCE:
                        zone_key = match_key(zone_name, ORDINANCE[region])
                        if zone_key:
                            bc_ratio        = ORDINANCE[region][zone_key]["건폐율"]
                            far_ratio       = ORDINANCE[region][zone_key]["용적률"]
                            ordinance_label = f"{region} 도시계획 조례"
                        else:
                            ordinance_label = f"{region} 조례 미매칭 → 국토계획법 시행령 적용"
                    else:
                        ordinance_label = "국토계획법 시행령 (조례 DB 미등록 지역 → 참고용)"

                    if bc_ratio is None:
                        nk = match_key(zone_name, NATIONAL_DEFAULT)
                        if nk:
                            bc_ratio  = NATIONAL_DEFAULT[nk]["건폐율"]
                            far_ratio = NATIONAL_DEFAULT[nk]["용적률"]

                    use_key    = match_key(zone_name, ZONE_USE)
                    max_floor  = FLOOR_LIMIT.get(zone_key or use_key or "", 999)
                    height_inf = HEIGHT_LIMIT.get(zone_key or use_key or "", {"절대높이": "없음", "일조권사선": True})
                    use_info   = ZONE_USE.get(use_key)
                    abs_h      = height_inf.get("절대높이", "없음")
                    illo       = height_inf.get("일조권사선", True)

                    # ════════════════════════════
                    # 1단계 결과
                    # ════════════════════════════
                    st.success(f"✅ 조회 완료: {address}")
                    if site_area:
                        st.info(f"📐 대지면적: {site_area} m²  ({site_area/3.3058:.1f} 평)")

                    st.divider()
                    st.subheader("【1단계】 토지 법규 현황 분석")

                    st.markdown("#### 1. 용도지역 및 지구")
                    st.markdown(f"**용도지역:** `{zone_name}`")
                    st.caption("근거: 국토계획법 제36조")
                    if districts:
                        for d in districts:
                            st.markdown(f"**지구단위계획:** `{d}` ⚠️ 별도 완화기준 적용 가능")
                    else:
                        st.markdown("**지구단위계획:** 해당 없음")

                    st.markdown("#### 2. 건축 가능 규모")
                    st.caption(f"근거: {ordinance_label}")
                    if bc_ratio:
                        col1, col2 = st.columns(2)
                        with col1:
                            st.metric("건폐율", f"{bc_ratio}% 이하")
                            if site_area:
                                max_bc = round(site_area * bc_ratio / 100, 2)
                                st.caption(f"최대 건축면적: {max_bc} m² ({max_bc/3.3058:.1f}평)")
                        with col2:
                            st.metric("용적률", f"{far_ratio}% 이하")
                            if site_area:
                                max_far = round(site_area * far_ratio / 100, 2)
                                st.caption(f"최대 연면적: {max_far} m² ({max_far/3.3058:.1f}평)")

                    st.markdown("#### 3. 높이 제한")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("절대높이", abs_h)
                    with col2:
                        st.metric("일조권사선", "필요" if illo else "불필요")
                    with col3:
                        st.metric("최고층수", f"{max_floor}층 이하" if max_floor < 999 else "제한 없음")
                    st.caption("근거: 건축법 제61조, 건축법 시행령 제82조")

                    if use_info:
                        st.markdown("#### 4. 허용 건축물 용도")
                        st.caption(f"근거: 국토계획법 시행령 {use_info['근거']}")
                        col1, col2 = st.columns(2)
                        with col1:
                            st.success("✅ 허용\n\n" + "\n\n".join(f"• {u}" for u in use_info["허용"]))
                        with col2:
                            st.error("❌ 불허\n\n" + "\n\n".join(f"• {u}" for u in use_info["불허"]))

                    if site_area and bc_ratio:
                        st.markdown("#### 5. 주차대수 기준")
                        max_far_v = round(site_area * far_ratio / 100, 2)
                        st.caption(f"최대 연면적 {max_far_v} m² 기준 | 근거: 주차장법 시행령 별표1")
                        parking_data = []
                        for use_nm, info in PARKING_TABLE.items():
                            cnt = max(1, int(max_far_v / info["calc_area"]))
                            parking_data.append({"용도": use_nm, "법정주차대수": f"{cnt}대", "기준": info["기준"]})
                        st.table(parking_data)

                    # ════════════════════════════
                    # 2단계 결과
                    # ════════════════════════════
                    if plan:
                        st.divider()
                        st.subheader("【2단계】 계획 건물 법규 검토")

                        ba     = plan.get("건축면적")
                        gfa    = plan.get("연면적")
                        height = plan.get("건물높이")
                        floors = plan.get("지상층수")
                        bfloor = plan.get("지하층수", 0)
                        road_w = plan.get("접도폭원")
                        use    = plan.get("주용도")
                        prk    = plan.get("계획주차대수")

                        st.markdown("#### 1. 규모 검토")
                        if site_area and bc_ratio and ba:
                            max_bc = site_area * bc_ratio / 100
                            a_bc   = round(ba / site_area * 100, 1)
                            ok     = ba <= max_bc
                            sur_bc = round(abs(max_bc - ba), 2)
                            if ok:
                                st.success(f"✅ 건축면적: {ba}m²  건폐율 {a_bc}% (허용 {bc_ratio}% 이하)  여유 {sur_bc}m²")
                            else:
                                st.error(f"❌ 건축면적: {ba}m²  건폐율 {a_bc}% (허용 {bc_ratio}% 초과!)  초과 {sur_bc}m²")
                            st.caption("근거: 국토계획법 시행령 제84조")

                        if site_area and far_ratio and gfa:
                            max_far = site_area * far_ratio / 100
                            a_far   = round(gfa / site_area * 100, 1)
                            ok      = gfa <= max_far
                            sur_far = round(abs(max_far - gfa), 2)
                            if ok:
                                st.success(f"✅ 연면적: {gfa}m²  용적률 {a_far}% (허용 {far_ratio}% 이하)  여유 {sur_far}m²")
                            else:
                                st.error(f"❌ 연면적: {gfa}m²  용적률 {a_far}% (허용 {far_ratio}% 초과!)  초과 {sur_far}m²")
                            st.caption("근거: 국토계획법 시행령 제85조")

                        st.markdown("#### 2. 높이 및 층수 검토")
                        if height:
                            if "없음" in abs_h:
                                st.success("✅ 절대높이: 제한 없음")
                            else:
                                lim = int("".join(filter(str.isdigit, abs_h)))
                                ok  = height <= lim
                                if ok:
                                    st.success(f"✅ 절대높이: {height}m  허용 {abs_h} 만족")
                                else:
                                    st.error(f"❌ 절대높이: {height}m  허용 {abs_h} 초과!")
                                st.caption("근거: 건축법 시행령 제82조")

                        if floors:
                            if max_floor >= 999:
                                st.success(f"✅ 지상층수: {floors}층  최고층수 제한 없음")
                            elif floors <= max_floor:
                                st.success(f"✅ 지상층수: {floors}층  최고 {max_floor}층 이하 만족")
                            else:
                                st.error(f"❌ 지상층수: {floors}층  최고 {max_floor}층 초과!")
                            st.caption("근거: 국토계획법 시행령")
                            if bfloor:
                                st.info(f"ℹ️ 지하층수: {bfloor}층  용도지역 층수제한 적용 제외")

                        if height and illo:
                            min_dist = round(height / 2, 1)
                            st.warning(f"⚠️ 일조권 사선제한: 정북방향 인접대지경계선에서 최소 {min_dist}m 이격 필요")
                            st.caption("근거: 건축법 제61조 제1항")

                        if height and road_w:
                            allow_h = road_w * 1.5 + 4
                            ok = height <= allow_h
                            if ok:
                                st.success(f"✅ 도로사선: 건물높이 {height}m  도로 {road_w}m 기준 허용높이 {allow_h}m 만족")
                            else:
                                st.error(f"❌ 도로사선: 건물높이 {height}m  도로 {road_w}m 기준 허용높이 {allow_h}m 초과!")
                            st.caption("근거: 건축법 제61조 제2항")

                        if use and use_info:
                            st.markdown("#### 3. 용도 적합성 검토")
                            cu       = use.replace(" ", "")
                            is_allow = any(cu in a.replace(" ", "") or a.replace(" ", "") in cu for a in use_info["허용"])
                            is_deny  = any(cu in d.replace(" ", "") or d.replace(" ", "") in cu for d in use_info["불허"])
                            if is_deny:
                                st.error(f"❌ 주용도 '{use}'  {zone_name} 불허 용도!")
                            elif is_allow:
                                st.success(f"✅ 주용도 '{use}'  {zone_name} 허용 용도")
                            else:
                                st.warning(f"⚠️ 주용도 '{use}'  허용 여부 별도 확인 필요")
                            st.caption(f"근거: 국토계획법 시행령 {use_info['근거']}")

                        if gfa:
                            st.markdown("#### 4. 주차대수 검토")
                            matched = None
                            cu = (use or "").replace(" ", "")
                            for k, v in PARKING_TABLE.items():
                                if k.replace(" ", "") in cu or cu in k.replace(" ", ""):
                                    matched = (k, v)
                                    break
                            if not matched:
                                matched = ("공동주택", PARKING_TABLE["공동주택"])
                            pk_nm, pk_info = matched
                            legal = max(1, int(gfa / pk_info["calc_area"]))
                            if prk is not None and prk > 0:
                                ok = prk >= legal
                                if ok:
                                    st.success(f"✅ 계획 {prk}대  ≥  법정 {legal}대 ({pk_info['기준']})  여유 {prk-legal}대")
                                else:
                                    st.error(f"❌ 계획 {prk}대  <  법정 {legal}대 ({pk_info['기준']})  {legal-prk}대 부족!")
                            else:
                                st.info(f"ℹ️ 법정주차대수: {legal}대  ({pk_info['기준']})")
                            st.caption("근거: 주차장법 시행령 별표1")

                    st.divider()
                    st.caption("⚠️ 지자체 조례에 따라 달라질 수 있습니다. 정확한 검토는 전문가에게 문의하세요.")

st.divider()
st.caption("© 건축법규 자동조회 시스템 | 브이월드 API 기반")
