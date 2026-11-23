"""Building Law Checker renewal — Streamlit entry point.

Run: streamlit run app.py
This app is for early design-stage screening, not permitting conclusions.
"""
import streamlit as st
from building_law_checker import LAND_API_KEY
from vworld_client import geocode, lookup_zones, lookup_district_plan, relay_configured
from law_core_v2 import (CORE_PACK_ID, route_laws, preview_area, far_counted_area,
                         FAR_EXCLUSION_KEYS, sort_findings, findings_to_markdown,
                         findings_to_json, parking_required,
                         PARKING_RULES, PARKING_MANUAL_KEYS)
from ordinance_parse import CANON_ZONES
from review_sheet import ReviewInput, USE_LABELS, build_review, review_to_json, review_to_markdown, summary_values
from ordinance_regions import zone_limits_for, region_of, connected_count
from sunlight_regions import setback as sun_setback, note as sun_note, region_data as sun_region_data
from parking_regions import build as pk_build, parking_required_region, region_data as pk_region_data, follows_decree as pk_follows
from ordinance_daejeon import (is_daejeon, parking_required_daejeon, DJ_PARKING_RULES,
                               DJ_MANUAL_KEYS, DJ_UNDEFINED_KEYS, DJ_META, DJ_SUNLIGHT_NOTE, dj_sunlight_setback)

st.set_page_config(page_title="현상설계 법규 분석 v2", page_icon="🏛️", layout="wide")
st.title("현상설계 법규 분석 · Core v2")
st.caption("기존 VWorld 주소 조회 + OpenCrab Core v2 판단 정책 기반 사전 검토")
st.warning("법률 판단 보조 도구입니다. 실무 제출·허가 전 공식 원문, 최신 조례, 지구단위계획 및 전문가 검토가 필수입니다.")
st.caption(f"판단 정책: OpenCrab Core v2 ({CORE_PACK_ID}) · 로컬 정책 어댑터 / 실시간 OpenCrab 연결 아님")

with st.form("site_form"):
    left, right = st.columns(2)
    with left:
        address = st.text_input("주소/지번", placeholder="예: 대전광역시 유성구 ...")
        building_use = st.selectbox("건축물 주용도 (건축법 시행령 별표 1)", USE_LABELS)
        site_area = st.number_input("대지면적 (㎡)", min_value=0.0, value=0.0)
        is_public = st.checkbox("공공건축물")
        total_floor = st.number_input("계획 연면적 (㎡) — 비우면 용적률 상한 기준으로 가정", min_value=0.0, value=0.0)
    with right:
        is_housing = st.checkbox("주택사업/정비사업")
        manual_zone = st.selectbox("용도지역 직접 선택 (자동 조회가 안 될 때만)",
                                   ["자동 조회 결과 사용"] + list(CANON_ZONES))
        district_choice = st.selectbox("지구단위계획 적용 여부(수동 확인)", ["미확인", "적용", "비적용"])
        covered = st.number_input("계획 건축면적 (㎡)", min_value=0.0, value=0.0)
        far_area = st.number_input("용적률 산정용 연면적 (㎡, 검토값)", min_value=0.0, value=0.0)
        use_floor = st.number_input("해당 용도 바닥면적 합계 (㎡) — 비우면 연면적", min_value=0.0, value=0.0)
        typical_floor = st.number_input("3층 이상 대표층의 거실 바닥면적 (㎡) — 직통계단 판정용", min_value=0.0, value=0.0)
        basement_floor = st.number_input("지하층 거실 바닥면적 (㎡) — 직통계단 판정용", min_value=0.0, value=0.0)
    submitted = st.form_submit_button("법규 리스크 분석", type="primary")

if submitted:
    district = {"미확인": None, "적용": True, "비적용": False}[district_choice]
    zones = []
    st.subheader("1. 기본 자료 확인")
    if not LAND_API_KEY and not relay_configured():
        st.error("VWORLD_API_KEY(또는 중계 설정 VWORLD_RELAY_URL/TOKEN)가 없어 주소·용도지역 조회를 건너뜁니다. 모든 대지 조건은 미확인 처리됩니다.")
    elif address.strip():
        st.write(f"입력 주소: {address}")
        try:
            gc = geocode(address.strip())
            x, y = gc["x"], gc["y"]
            if gc["status"] == "ERROR":
                st.warning(f"주소 좌표 조회 실패: {gc['error']} — 용도지역/지구단위계획은 미확인으로 처리합니다.")
            elif gc["status"] == "NOT_FOUND":
                st.warning("주소를 찾지 못했습니다(지번·도로명 모두 결과 없음). 주소 표기를 확인하세요. 용도지역/지구단위계획은 미확인으로 처리합니다.")
            else:
                zr = lookup_zones(x, y)
                pr = lookup_district_plan(x, y)
                zones = zr["names"]
                plans = pr["names"]
                if zr["status"] == "ERROR":
                    st.warning(f"용도지역 조회 실패: {zr['error']} — 용도지역은 미확인으로 처리합니다.")
                elif zr["status"] == "NOT_FOUND":
                    st.write("VWorld 용도지역 조회: 조회는 되었으나 해당 지점의 용도지역 데이터 없음 (미확인으로 처리)")
                else:
                    st.write("VWorld 용도지역 조회:", ", ".join(zones))
                if pr["status"] == "ERROR":
                    st.warning(f"지구단위계획 조회 실패: {pr['error']} — 미확인으로 처리합니다.")
                elif pr["status"] == "NOT_FOUND":
                    st.write("VWorld 지구단위계획구역 조회: 해당 지점에 구역 데이터 없음 (법적 '비적용' 확정은 아님, 결정도서 확인)")
                else:
                    st.write("VWorld 지구단위계획구역 조회:", ", ".join(plans))
                if district is None and plans:
                    district = True
        except Exception:
            zones = []
            st.warning("외부 API 응답 확인 실패: 모든 미확정 항목은 확인 필요로 처리")
    else:
        st.info("주소가 없으므로 대지 관련 법규는 UNKNOWN으로 분류됩니다.")

    if manual_zone != "자동 조회 결과 사용":
        if zones and [z.replace(" ", "") for z in zones] != [manual_zone]:
            st.warning(f"직접 선택한 용도지역({manual_zone})이 자동 조회 결과({', '.join(zones)})와 다릅니다. 직접 선택값을 사용합니다 — 토지이용계획확인서로 확인하세요.")
        elif not zones:
            st.info(f"자동 조회가 되지 않아 직접 선택한 용도지역({manual_zone})을 사용합니다 — 토지이용계획확인서로 확인하세요.")
        zones = [manual_zone]

    rin = ReviewInput(address=address, zones=tuple(zones), use=building_use, site_area=site_area or None,
                      total_floor_area=total_floor or None, use_floor_area=use_floor or None,
                      typical_floor_area=typical_floor or None, basement_floor_area=basement_floor or None,
                      is_public=is_public, has_district_plan=district)
    review_rows = build_review(rin)
    st.subheader("2. 법규검토서 — 이 대지에서 지켜야 할 기준")
    vals = summary_values(review_rows)
    if vals:
        cols = st.columns(len(vals))
        for c, (label, v) in zip(cols, vals.values()):
            c.metric(label, f"{v:,.0f}" if float(v).is_integer() else f"{v:,.1f}")
        if not total_floor and "max_floor_area" in vals:
            st.caption("연면적을 입력하지 않아 주차·조경·방화구획은 **용적률 상한 기준 최대 연면적을 가정**해 계산했습니다(상태: 조건부).")
    st.table([{"구분": r.section, "항목": r.item, "근거": r.basis, "기준": r.standard, "이 대지 적용값": r.applied,
               "설계 영향": r.impact, "상태": r.status} for r in review_rows])
    st.caption("상태: 확정(원문+입력으로 결정) · 조건부(가정·추가 확인 필요) · 미확인(입력 부족) · 미연결(해당 법규 데이터 없음 — 직접 확인)")
    sel = st.selectbox("항목별 비고·근거 원문 보기", [f"{r.section} · {r.item}" for r in review_rows], key="review_sel")
    chosen = review_rows[[f"{r.section} · {r.item}" for r in review_rows].index(sel)]
    for n in chosen.notes:
        st.write("· " + n)
    if chosen.source:
        try:
            from pathlib import Path
            with st.expander(f"근거 원문 사본: {chosen.source}"):
                st.text(Path(chosen.source).read_text(encoding="utf-8")[:6000])
        except Exception:
            st.caption("원문 사본을 불러오지 못했습니다: " + chosen.source)
    rctx = {"주소": address or "미입력", "용도지역": ", ".join(zones) if zones else "미확인", "주용도": building_use,
            "대지면적(㎡)": site_area or "미입력", "연면적(㎡)": total_floor or "미입력(용적률 상한 가정)"}
    e1, e2 = st.columns(2)
    e1.download_button("법규검토서 .md 저장", review_to_markdown(review_rows, rctx), file_name="law_review_sheet.md", mime="text/markdown")
    e2.download_button("법규검토서 .json 저장(수치 포함)", review_to_json(review_rows, rctx), file_name="law_review_sheet.json", mime="application/json")

    st.subheader("3. 법규군별 검토 우선순위 (참고)")
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

    st.session_state["zones"] = zones
    st.session_state["address"] = address
    zl = zone_limits_for(address, zones)
    if zl["status"] == "NO_REGION":
        if address.strip():
            st.subheader("4. 지자체 도시계획 조례 기준")
            n_all, n_local = connected_count()
            st.info(f"이 주소의 지자체 도시계획 조례는 아직 연결되어 있지 않습니다(연결: 광역시·특별시 8곳과 도 소재 시·군 {n_local}곳). "
                    "건폐율·용적률은 해당 지자체 도시계획 조례 원문으로 직접 확인하세요.")
    else:
        st.subheader(f"4. {zl['region']} 도시계획 조례 기준 (원문 연결)")
        if zl["matches"]:
            st.table([{"용도지역": m["zone"],
                       "건폐율 상한(%)": m["coverage_max_pct"] if m["coverage_max_pct"] is not None else "미확인",
                       "용적률 상한(%)": m["far_max_pct"] if m["far_max_pct"] is not None else "미확인",
                       "조문 단서": m["note"]} for m in zl["matches"]])
        if zl["unmatched"]:
            st.warning("조례 원문에서 값을 읽지 못한(또는 매칭되지 않은) 용도지역 — 미확인: " + ", ".join(zl["unmatched"]))
        if not zones:
            st.info("용도지역을 조회하지 못해 건폐율·용적률 상한을 표시하지 않습니다.")
        for c in zl["caveats"] + zl["notes"]:
            st.caption("※ " + c)
        L = zl["law"]
        st.caption(f"근거: {L['name']} (공포 {L['promulgation_no']}, 시행 {L['effective']}) — 원문 사본 {L['snapshot']}")
    sun_region = region_of(address)
    if address.strip():
        with st.expander(f"일조(정북) 이격거리 — 법 하한" + (f"과 {sun_region} 건축 조례 비교" if sun_region and sun_region_data(sun_region) else "")):
            st.write(sun_note(sun_region if sun_region and sun_region_data(sun_region) else None))
            hs = st.text_input("건축물 부분 높이(m), 쉼표로 여러 개", value="10, 14, 20", key="sun_heights")
            rows = []
            for tok in [t.strip() for t in hs.split(",") if t.strip()]:
                r = sun_setback(sun_region or "", tok)
                if r["status"] == "PREVIEW":
                    rows.append({"높이(m)": r["height_m"], "법 하한(m)": r["law_min_m"],
                                 "조례 문언(m)": r["ordinance_text_m"], "안전측(m)": r["conservative_m"],
                                 "법·조례 불일치": "예" if r["conflict"] else "아니오"})
                elif r["status"] == "NO_DATA":
                    rows.append({"높이(m)": r["height_m"], "법 하한(m)": r["law_min_m"], "조례 문언(m)": "미확인",
                                 "안전측(m)": r["law_min_m"], "법·조례 불일치": "-"})
            if rows:
                st.table(rows)
                st.caption("정북 인접 대지의 용도지역이 전용·일반주거지역이 아니면 적용되지 않습니다(영 제86조제2항). 확정값이 아니라 안전측 제시입니다.")
    if is_daejeon(address):
        st.caption("유성구 조례(주차장·도시계획)에는 건폐율·용적률·부설주차장 설치기준 수치가 없고 "
                   "광역시 조례를 따릅니다. 구 조례의 인근설치 300m, 설치의무 면제 규정은 주차 계산 결과의 참고 항목에 표시됩니다.")

    st.subheader("5. 규모·주차 시나리오 계산 (직접 입력)")
    st.info("법규 적용 비율은 자동 확정하지 않습니다. 아래 수치를 직접 확인해서 입력하면 산술 시나리오만 계산합니다.")
    st.session_state["site_snapshot"] = {
        "site_area": site_area, "covered": covered, "far_area": far_area,
    }

if "site_snapshot" in st.session_state:
    data = st.session_state["site_snapshot"]
    addr = st.session_state.get("address", "")
    zl_all = zone_limits_for(addr, st.session_state.get("zones", []))
    with st.expander("부설주차장 산정"):
        mode_j = st.radio("적용 기준", ["자동(주소 기준)", "지역 조례(주소 지역)", "주차장법 시행령 별표 1만"],
                          horizontal=True, key="pk_mode")
        pk_region = region_of(addr)
        use_local = mode_j != "주차장법 시행령 별표 1만"
        basis = "national"
        if use_local and pk_region == "대전광역시":
            basis = "daejeon"
        elif use_local and pk_region and pk_follows(pk_region):
            basis = "follows"
        elif use_local and pk_region and pk_region_data(pk_region):
            basis = "region"
        if use_local and basis == "national":
            st.info("이 주소 지역의 주차장 조례는 아직 연결되어 있지 않아 주차장법 시행령 별표 1 기준만 계산합니다(조례가 강화·완화할 수 있음).")

        if basis == "daejeon":
            st.caption(f"{DJ_META['parking']['name']} 별표 6 (공포 {DJ_META['parking']['promulgation_no']}, "
                       f"시행 {DJ_META['parking']['effective']}) 기준 신축 산술 시나리오. 용도변경·증축은 반영하지 않습니다.")
            rules, manual, undefined = DJ_PARKING_RULES, DJ_MANUAL_KEYS, DJ_UNDEFINED_KEYS
            opts = {k: f"{v[0]}호 {v[1]}" for k, v in rules.items()}
            opts.update({k: f"5호 {v}" for k, v in manual.items()})
            opts.update({k: f"(자동 산정 불가) {k}" for k in undefined})
            variant = 0
        elif basis == "region":
            pr = pk_region_data(pk_region)
            o = pr["ordinance"]
            st.caption(f"{o['name']} 설치기준 별표 (공포 {o['promulgation_no']}, 시행 {o['effective']}) 기준 신축 산술 시나리오. "
                       "용도변경·증축은 반영하지 않습니다. 공동주택·오피스텔 등 별도 규정을 인용하는 분류는 계산하지 않고 원문 표를 보여줍니다.")
            if pr.get("incomplete") or pr.get("manual_heavy"):
                st.warning("이 조례의 별표는 일부만 자동으로 읽었습니다. 목록에 없는 용도는 아래 '조례 별표 원문'으로 직접 확인하세요.")
            with st.expander("조례 별표 원문"):
                try:
                    from pathlib import Path
                    st.text(Path(pr["ordinance"]["annex_snapshot"]).read_text(encoding="utf-8"))
                except Exception:
                    st.caption("원문 사본을 불러오지 못했습니다: " + str(pr["ordinance"]["annex_snapshot"]))
            variant = 0
            if pr["columns"]:
                variant = st.radio("조례 표의 열(대지 구역)", list(range(len(pr["columns"]))), horizontal=True,
                                   format_func=lambda i: pr["columns"][i], key=f"pk_variant_{pk_region}")
            rules, manual, special_fn, opts = pk_build(pk_region, variant)
        else:
            if basis == "follows":
                fd = pk_follows(pk_region)
                st.success(f"{fd['ordinance']['name']}는 자체 기준표 없이 주차장법 시행령 별표 1을 따릅니다 ({fd['article']}).")
                if fd.get("proviso"):
                    st.warning("조례 단서(계산에 반영되지 않음): " + fd["proviso"])
            st.caption("주차장법 시행령 별표 1 (시행 2026-08-28) 기준 신축 산술 시나리오. 지자체 조례가 강화·완화할 수 있고 "
                       "이 모드는 조례를 반영하지 않습니다." if basis == "national" else
                       "주차장법 시행령 별표 1 (시행 2026-08-28) 기준 신축 산술 시나리오. 조례의 단서·예외는 반영하지 않습니다.")
            rules, manual, undefined = PARKING_RULES, PARKING_MANUAL_KEYS, {}
            opts = {k: f"{v[0]}호 {v[1]}" for k, v in rules.items()}
            opts.update({k: f"5호 {v}" for k, v in manual.items()})
            variant = 0
        n = st.number_input("용도 개수", min_value=1, max_value=8, value=1, step=1, key="pk_n")
        pk_items = []
        tag = f"{basis}_{pk_region}_{variant}"
        for i in range(int(n)):
            c1, c2 = st.columns([3, 1])
            k = c1.selectbox("용도", list(opts), format_func=opts.get, key=f"pk_k{i}_{tag}")
            unit = rules[k][2] if k in rules else "해당 없음"
            q = c2.number_input(unit, min_value=0.0, value=0.0, key=f"pk_q{i}_{tag}")
            pk_items.append((k, q))
        if basis == "daejeon":
            pk = parking_required_daejeon(pk_items)
        elif basis == "region":
            pk = parking_required_region(pk_region, pk_items, variant)
            raw_cats = [c for c in pk_region_data(pk_region)["categories"] if c["kind"] == "manual"
                        and any(k == c["id"] for k, _ in pk_items)]
            for c in raw_cats:
                with st.expander(f"원문 표: {c['no']}. {c['label'][:40]}"):
                    st.text(c["raw"])
        else:
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
    # 용도지역이 하나로 특정되고 조례 원문에서 두 값을 모두 읽었으면 그 상한을 기본값으로 제안(사용자가 바꿀 수 있음)
    d_cov, d_far, sig = 0.0, 0.0, "none"
    if (zl_all["status"] == "OK" and len(zl_all["matches"]) == 1 and not zl_all["unmatched"]):
        m0 = zl_all["matches"][0]
        d_cov, d_far, sig = float(m0["coverage_max_pct"]), float(m0["far_max_pct"]), f"{zl_all['region']}_{m0['zone']}"
        st.caption(f"{zl_all['law']['name']} 상한을 기본값으로 제안했습니다({m0['zone']}). 단서·특례는 위 표의 주의사항을 확인하세요.")
    c1, c2 = st.columns(2)
    with c1:
        coverage = st.number_input("검토용 건폐율 (%)", min_value=0.0, max_value=100.0, value=d_cov, step=1.0,
                                   key=f"cov_{sig}")
    with c2:
        far_pct = st.number_input("검토용 용적률 (%)", min_value=0.0, value=d_far, step=10.0, key=f"far_{sig}")
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
st.caption("현재 제한: 조례는 광역시·특별시 8곳(서울·부산·대구·인천·광주·대전·울산·세종)의 도시계획 조례 건폐율·용적률과 대전의 주차·일조만 연결(그 밖의 지자체·조례는 직접 확인). 정북일조는 법 하한과 조례 문언을 비교한 안전측 값만 제시(조례의 법 개정 반영 여부는 조례별로 표시), 3D 검토·피난 산정 미구현. 법령 개정 감지는 law_sync.py 실행. 기존 app.py는 레거시로 보존.")
