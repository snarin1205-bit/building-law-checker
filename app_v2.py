"""Building Law Checker renewal — Streamlit entry point.

Run: streamlit run app_v2.py
This app is for early design-stage screening, not permitting conclusions.
"""
import streamlit as st
from building_law_checker import (get_coordinates, get_land_use, get_district_plan,
                                  get_region, LAND_API_KEY)
from law_core_v2 import (CORE_PACK_ID, route_laws, preview_area, far_counted_area,
                         FAR_EXCLUSION_KEYS, sort_findings, findings_to_markdown,
                         findings_to_json, parking_required,
                         PARKING_RULES, PARKING_MANUAL_KEYS)

st.set_page_config(page_title="현상설계 법규 분석 v2", page_icon="🏛️", layout="wide")
st.title("현상설계 법규 분석 · Core v2")
st.caption("기존 VWorld 주소 조회 + OpenCrab Core v2 판단 정책 기반 사전 검토")
st.warning("법률 판단 보조 도구입니다. 실무 제출·허가 전 공식 원문, 최신 조례, 지구단위계획 및 전문가 검토가 필수입니다.")
st.caption(f"판단 정책: OpenCrab Core v2 ({CORE_PACK_ID}) · 로컬 정책 어댑터 / 실시간 OpenCrab 연결 아님")

with st.form("site_form"):
    left, right = st.columns(2)
    with left:
        address = st.text_input("주소/지번", placeholder="예: 대전광역시 유성구 ...")
        building_use = st.text_input("건축물 주용도", placeholder="예: 공공업무시설, 도서관")
        site_area = st.number_input("대지면적 (㎡)", min_value=0.0, value=0.0)
        is_public = st.checkbox("공공건축물")
    with right:
        is_housing = st.checkbox("주택사업/정비사업")
        district_choice = st.selectbox("지구단위계획 적용 여부(수동 확인)", ["미확인", "적용", "비적용"])
        covered = st.number_input("계획 건축면적 (㎡)", min_value=0.0, value=0.0)
        far_area = st.number_input("용적률 산정용 연면적 (㎡, 검토값)", min_value=0.0, value=0.0)
    submitted = st.form_submit_button("법규 리스크 분석", type="primary")

if submitted:
    district = {"미확인": None, "적용": True, "비적용": False}[district_choice]
    zones = []
    st.subheader("1. 기본 자료 확인")
    if not LAND_API_KEY:
        st.error("VWORLD_API_KEY 환경변수가 설정되지 않아 주소·용도지역 조회를 건너뜁니다. 모든 대지 조건은 미확인 처리됩니다.")
    elif address.strip():
        st.write(f"입력 주소: {address}")
        try:
            x, y = get_coordinates(address.strip())
            if x is None or y is None:
                st.warning("주소 좌표 조회 실패: 용도지역/지구단위계획은 확인 필요")
            else:
                zones = get_land_use(x, y) or []
                plans = get_district_plan(x, y)
                st.write("VWorld 용도지역 조회:", ", ".join(zones) if zones else "미확인 (조회 실패 또는 데이터 없음)")
                st.write("VWorld 관련 계획 조회:", ", ".join(plans) if plans else "미확인 (없음으로 단정하지 않음)")
                if district is None and plans:
                    district = True
        except Exception:
            zones = []
            st.warning("외부 API 응답 확인 실패: 모든 미확정 항목은 확인 필요로 처리")
    else:
        st.info("주소가 없으므로 대지 관련 법규는 UNKNOWN으로 분류됩니다.")

    st.subheader("2. 법규 검토 우선순위")
    findings = route_laws(
        building_use=building_use, site_address=address,
        site_area=site_area or None, is_public=is_public,
        is_housing_project=is_housing, has_district_plan=district,
        zone_names=zones,
    )
    for f in sort_findings(findings):
        with st.expander(f"[{f.priority}] {f.law_group}", expanded=f.priority == "REQUIRED"):
            st.write("조건:", f.condition)
            st.write("설계 영향:", f.design_impact)
            st.write("대응 전략:", f.action)
            st.caption(f"근거 상태: {f.evidence_status}")
            if f.source_url:
                st.markdown(f"[원문 확인 링크]({f.source_url}) (시행일·조문은 직접 확인)")
    ctx = {"주소": address or "미입력", "주용도": building_use or "미입력",
           "VWorld 용도지역": ", ".join(zones) if zones else "미확인"}
    d1, d2 = st.columns(2)
    d1.download_button("검토 결과 .md 저장", findings_to_markdown(findings, ctx),
                       file_name="law_review.md", mime="text/markdown")
    d2.download_button("검토 결과 .json 저장", findings_to_json(findings, ctx),
                       file_name="law_review.json", mime="application/json")

    st.subheader("3. 규모 시나리오 계산")
    st.info("법규 적용 비율은 자동 확정하지 않습니다. 아래 수치를 직접 확인해서 입력하면 산술 시나리오만 계산합니다.")
    st.session_state["site_snapshot"] = {
        "site_area": site_area, "covered": covered, "far_area": far_area,
    }

if "site_snapshot" in st.session_state:
    data = st.session_state["site_snapshot"]
    with st.expander("부설주차장 산정 (주차장법 시행령 별표 1, 2026-08-28 시행)"):
        st.caption("법령 원문 기준 신축 산술 시나리오입니다. 조례 강화·완화, 용도변경·증축, 장애인전용구획은 "
                   "반영하지 않습니다. 표 제5호(공동주택·오피스텔 등)는 자동 산정하지 않습니다.")
        opts = {k: f"{v[0]}호 {v[1]}" for k, v in PARKING_RULES.items()}
        opts.update({k: f"5호 {v}" for k, v in PARKING_MANUAL_KEYS.items()})
        n = st.number_input("용도 개수", min_value=1, max_value=8, value=1, step=1, key="pk_n")
        pk_items = []
        for i in range(int(n)):
            c1, c2 = st.columns([3, 1])
            k = c1.selectbox("용도", list(opts), format_func=opts.get, key=f"pk_k{i}")
            unit = PARKING_RULES[k][2] if k in PARKING_RULES else "해당 없음"
            q = c2.number_input(unit, min_value=0.0, value=0.0, key=f"pk_q{i}")
            pk_items.append((k, q))
        pk = parking_required(pk_items)
        st.json(pk)
        if pk.get("ambiguous"):
            st.warning("원문이 정하지 않은 부분이 있어 최종 대수를 확정하지 않았습니다. 사유를 확인하세요.")
    with st.expander("용적률 산정용 연면적 계산기 (제외면적 직접 입력)"):
        total_fa = st.number_input("전체 연면적 (㎡)", min_value=0.0, value=0.0, key="total_fa")
        ex_in = {k: st.number_input(label + " (㎡)", min_value=0.0, value=0.0, key="ex_" + k)
                 for k, label in FAR_EXCLUSION_KEYS.items()}
        if total_fa > 0:
            res = far_counted_area(total_fa, ex_in)
            st.json(res)
            st.caption("제외 가능 여부·범위는 조문·조례로 확인 후, 결과를 위 '용적률 산정용 연면적'에 반영하세요.")
    c1, c2 = st.columns(2)
    with c1:
        coverage = st.number_input("검토용 건폐율 (%)", min_value=0.0, max_value=100.0, value=0.0, step=1.0)
    with c2:
        far_pct = st.number_input("검토용 용적률 (%)", min_value=0.0, value=0.0, step=10.0)
    confirmed = st.checkbox("입력한 비율의 적용 조례·시행일·예외 여부를 별도로 확인했습니다")
    if coverage <= 0 or far_pct <= 0:
        st.warning("건폐율과 용적률을 입력해야 계산됩니다. 0은 미입력으로 처리합니다.")
    else:
        preview = preview_area(
            data["site_area"] or None,
            data["covered"] or None,
            data["far_area"] or None,
            coverage, far_pct, verified_source=confirmed,
        )
        st.json(preview)
        st.warning("WITHIN_INPUT_LIMIT는 입력된 비율에 대한 산술 판정일 뿐, 법적 적합 판정이 아닙니다.")
st.divider()
st.caption("현재 제한: 공식 법령 실시간 동기화·지자체 조례 확인·정북일조 3D 검토·정확한 주차/피난 산정 미구현. 기존 app.py는 레거시로 보존.")
