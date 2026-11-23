"""법규검토서: 주소·용도·면적 입력으로 '이 대지에서 무엇을 지켜야 하는가'를 항목별 표로 만든다 (네트워크 없음).

행(Row)마다 근거 조문·기준 수치·이 대지 적용값(계산)·설계 영향·상태를 담는다.
상태: 확정(원문 + 입력으로 결정) / 조건부(가정·추가 확인 필요) / 미확인(입력 부족·원문 미정) / 미연결(해당 법규 데이터 없음).
수치는 모두 법령·조례 원문에서 읽은 값이며, 원문에 없거나 해석이 갈리는 부분은 상태와 비고로 드러낸다.
"""
import json
import math
import pathlib
from dataclasses import dataclass, field, asdict
from typing import List, Optional

from law_core_v2 import PARKING_RULES, classify_zones, parking_required, north_light_law_minimum
from ordinance_daejeon import DJ_META, DJ_PARKING_RULES, parking_required_daejeon
from ordinance_regions import region_of, zone_limits_for
from parking_regions import build as pk_build, follows_decree, parking_required_region, region_data as pk_region_data
from sunlight_regions import region_data as sun_region_data, setback as sun_setback
from ordinance_landscape_parse import pct_at

ROOT = pathlib.Path(__file__).resolve().parent
_LAND = None


_GB = None


def _greenbelt():
    global _GB
    if _GB is None:
        f = ROOT / "data" / "greenbelt.json"
        _GB = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    return _GB


def _landscape():
    global _LAND
    if _LAND is None:
        _LAND = json.loads((ROOT / "data" / "landscape_ordinances.json").read_text(encoding="utf-8"))["regions"]
    return _LAND


STATUSES = ("확정", "조건부", "미확인", "미연결")


@dataclass
class Row:
    section: str
    item: str
    basis: str          # 근거 조문
    standard: str       # 기준(원문 수치)
    applied: str        # 이 대지 적용값(계산 결과)
    impact: str         # 설계에 미치는 영향
    status: str
    notes: List[str] = field(default_factory=list)
    source: Optional[str] = None  # 원문 사본 경로
    key: Optional[str] = None     # 기계가 읽는 식별자(예: max_floor_area)
    value: Optional[float] = None  # 그 수치(㎡·대 등)

    def as_dict(self):
        return asdict(self)


# ---------------------------------------------------------------------------
# 용도 분류(건축법 시행령 별표 1 용도 기준) → 주차 분류 키워드 / 직통계단 2개소 기준 / 공개공지 대상
# egress: (호, 임계 ㎡, 3층 이상 층 한정 여부)  — 영 제34조제2항 각 호
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Use:
    label: str
    parking_kw: tuple = ()
    parking_manual: bool = False
    egress: tuple = (4, 400, True)
    open_space: bool = False   # 영 제27조의2제1항제1호 열거 용도
    prefer_sub: tuple = ()     # 주차 하위 라벨 우선어(예: 학교)


USES = {u.label: u for u in (
    Use("업무시설", ("업무시설", "업무("), egress=(4, 400, True), open_space=True),
    Use("문화 및 집회시설(전시장·동식물원 제외)", ("문화 및 집회시설", "문화집회"), egress=(1, 200, False), open_space=True),
    Use("문화 및 집회시설 중 전시장·동식물원", ("문화 및 집회시설", "문화집회"), egress=(4, 400, True), open_space=True),
    Use("종교시설", ("종교",), egress=(1, 200, False), open_space=True),
    Use("판매시설", ("판매",), egress=(2, 200, True), open_space=True),
    Use("운수시설(여객용)", ("운수",), egress=(2, 200, True), open_space=True),
    Use("의료시설", ("의료",), egress=(2, 200, True)),
    Use("교육연구시설(학교)", (), egress=(4, 400, True), prefer_sub=("학교",)),
    Use("교육연구시설 중 학원", (), egress=(2, 200, True)),
    Use("노유자시설(아동·노인·장애인 관련)", (), egress=(2, 200, True)),
    Use("수련시설", ("수련시설",), egress=(4, 400, True)),
    Use("숙박시설", ("숙박",), egress=(2, 200, True), open_space=True),
    Use("제1종 근린생활시설", ("근린생활",), egress=(4, 400, True)),
    Use("제2종 근린생활시설(일반)", ("근린생활",), egress=(4, 400, True)),
    Use("위락시설(주점영업)", ("위락시설",), egress=(1, 200, False)),
    Use("위락시설(주점영업 외)", ("위락시설",), egress=(4, 400, True)),
    Use("운동시설", ("운동",), egress=(4, 400, True)),
    Use("공장", ("공장",), egress=(4, 400, True)),
    Use("창고시설", ("창고",), egress=(4, 400, True)),
    Use("공동주택(아파트 등)", (), parking_manual=True, egress=(3, 300, False)),
    Use("업무시설 중 오피스텔", (), parking_manual=True, egress=(3, 300, False)),
    Use("그 밖의 시설(방송통신·발전·자동차 관련 등)", (), egress=(4, 400, True)),
)}
USE_LABELS = list(USES)

_HO_TEXT = {
    1: "영 제34조제2항제1호(문화·집회·종교·주점영업 등: 해당 용도 층 바닥면적 합계)",
    2: "영 제34조제2항제2호(판매·운수·의료·숙박 등: 3층 이상 층의 해당 용도 거실 바닥면적 합계)",
    3: "영 제34조제2항제3호(공동주택·오피스텔: 해당 용도 층의 거실 바닥면적 합계)",
    4: "영 제34조제2항제4호(그 밖의 용도: 3층 이상 층의 거실 바닥면적 합계)",
}
OPEN_SPACE_ZONES = ("일반주거", "준주거", "상업", "준공업")


def _n(x, digits=0):
    if x is None:
        return "-"
    if digits == 0 and abs(x - round(x)) < 1e-9:
        return f"{int(round(x)):,}"
    return f"{x:,.{digits or 1}f}"


# ---------------------------------------------------------------------------
@dataclass
class ReviewInput:
    address: str = ""
    zones: tuple = ()
    use: str = "업무시설"
    site_area: Optional[float] = None
    total_floor_area: Optional[float] = None      # 계획 연면적(없으면 용적률 상한 기준 최대 연면적을 가정)
    use_floor_area: Optional[float] = None        # 해당 용도 바닥면적 합계(없으면 연면적)
    typical_floor_area: Optional[float] = None    # 3층 이상 대표층의 거실 바닥면적
    basement_floor_area: Optional[float] = None   # 지하층 거실 바닥면적 합계(층별 최대)
    is_public: bool = False
    has_district_plan: Optional[bool] = None
    parking_variant: int = 0
    planned_building_area: Optional[float] = None  # 계획 건축면적(설계안)
    planned_parking: Optional[int] = None          # 계획 주차대수(설계안)
    in_greenbelt: bool = False                    # 개발제한구역 안(VWorld 조회 또는 직접 선택)
    guideline_parking: Optional[int] = None        # 공모지침이 제시한 법정 주차대수(있으면 지침값을 함께 비교)


def pick_parking(rules, spec, is_public=False):
    """규칙표(key → (no,label,unit,mult,div))에서 용도에 맞는 시설면적 기준 규칙 키와, 후보 여러 개일 때의 메모를 고른다."""
    cands = []
    for key, (no, label, unit, mult, div) in rules.items():
        if unit != "시설면적㎡" or mult is None:
            continue
        if spec.parking_kw and any(k in label for k in spec.parking_kw):
            cands.append((key, label))
    note = None
    if cands:
        if is_public:
            pub = [c for c in cands if "공공" in c[1]]
            if pub:
                return pub[0][0], None
        if len(cands) > 1:
            note = "같은 용도에 여러 기준이 있음: " + "; ".join(c[1][:40] for c in cands) + " — 첫 항목으로 계산"
        return cands[0][0], note
    # 조례 표에 용도가 열거된 경우(parking_kw 있음)인데 계산 가능한 분류가 없으면 대체하지 않는다(수동 분류일 수 있음)
    if spec.parking_kw:
        return None, "해당 용도의 분류를 조례 별표에서 자동으로 읽지 못함(수동 처리된 분류) — 원문 별표 확인"
    # 표에 열거되지 않는 용도(교육연구·노유자 등)는 '그 밖의 건축물' 계열(하위 라벨 우선어 적용)
    others = [(k, lab) for k, (no, lab, unit, mult, div) in rules.items()
              if unit == "시설면적㎡" and mult is not None and "그 밖의 건축물" in lab]
    if spec.prefer_sub:
        pref = [o for o in others if any(p in o[1] for p in spec.prefer_sub)]
        if pref:
            return pref[0][0], None
    plain = [o for o in others if "학생용" not in o[1] and "학교" not in o[1]]
    if plain:
        return plain[0][0], None
    return (others[0][0] if others else None), None


def _rule_standard(rules, key):
    no, label, unit, mult, div = rules[key]
    m, d = float(mult), float(div)
    return f"시설면적 {d:g}㎡당 {m:g}대" if m != 1 else f"시설면적 {d:g}㎡당 1대"


def _parking_basis(region):
    """(기준 이름, rules, 계산 함수, 메모) — 대전 → 지역 조례 → 시행령 준용 → 지역 데이터 없음(시행령만) 순."""
    if region == "대전광역시":
        m = DJ_META["parking"]
        return (f"{m['name']} 별표 6 (시행 {m['effective']})", DJ_PARKING_RULES, lambda items, v: parking_required_daejeon(items), [])
    fd = follows_decree(region) if region else None
    if fd:
        n = [f"{fd['ordinance']['name']}는 자체 기준표 없이 주차장법 시행령 별표 1을 따름({fd['article']})"]
        if fd.get("proviso"):
            n.append("조례 단서(계산에 반영되지 않음): " + fd["proviso"][:200])
        return ("주차장법 시행령 별표 1 (조례 준용)", PARKING_RULES, lambda items, v: parking_required(items), n)
    if region and pk_region_data(region):
        r = pk_region_data(region)
        o = r["ordinance"]
        rules, manual, special, display = pk_build(region, 0)
        n = []
        if r.get("incomplete") or r.get("manual_heavy"):
            n.append("조례 별표의 일부 분류만 자동으로 읽었음 — 해당 용도가 목록에 없으면 원문 별표로 확인")
        return (f"{o['name']} 별표 (시행 {o['effective']})", rules, lambda items, v: parking_required_region(region, items, v), n)
    return ("주차장법 시행령 별표 1 (조례 미연결 — 조례가 강화·완화할 수 있음)", PARKING_RULES, lambda items, v: parking_required(items), [])


def _fmt_parking(res):
    if res.get("status") != "PREVIEW":
        return res.get("reason", "산정 불가")
    if res.get("ambiguous"):
        return f"{' 또는 '.join(str(c) for c in res['candidates'])}대 (끝수 처리 방식이 원문에 정해져 있지 않아 확정 불가)"
    return f"{res['count']}대"


# ---------------------------------------------------------------------------
def build_review(inp: ReviewInput):
    rows: List[Row] = []
    vals = {}
    spec = USES.get(inp.use) or USES["그 밖의 시설(방송통신·발전·자동차 관련 등)"]
    region = region_of(inp.address)
    zones = [z for z in (inp.zones or ()) if z]
    gb = bool(inp.in_greenbelt) or any("개발제한구역" in z for z in zones)
    zones = [z for z in zones if "개발제한구역" not in z]   # 개발제한구역은 용도구역 — 건폐율·용적률은 별도 기준
    GB = _greenbelt()
    gb_ok = bool(gb and GB.get("annex2", {}).get("status") == "ok")
    zinfo = classify_zones(zones)
    cats = zinfo["categories"]
    zl = zone_limits_for(inp.address, zones)

    # --- 1. 대지 개요 -----------------------------------------------------
    rows.append(Row("대지 개요", "용도지역", "국토계획법 / 토지이용계획", "—",
                    (", ".join(zones) if zones else "미확인") + (" + 개발제한구역(용도구역)" if gb else ""),
                    "건폐율·용적률·일조·공개공지 적용 여부의 기준", "조건부" if (zones or gb) else "미확인",
                    ["VWorld 조회 또는 직접 선택한 값 — 토지이용계획확인서로 확인",
                     "필지가 둘 이상의 용도지역에 걸치면 면적·위치별로 따로 검토"] if zones else ["용도지역이 없으면 아래 대지 기준 항목이 미확인으로 남음"]))
    dp = {True: "지구단위계획구역 — 결정도서·시행지침 우선 확인(건폐율·용적률·높이·건축선·용도 제한)", False: "해당 없음으로 입력됨(법적 비적용 확정은 아님)",
          None: "미확인 — 결정도서 확인"}[inp.has_district_plan]
    rows.append(Row("대지 개요", "지구단위계획", "국토계획법 제49조 이하", "—", dp,
                    "지구단위계획이 있으면 아래 일반 기준보다 지침이 우선하거나 추가 제한", "조건부" if inp.has_district_plan else "미확인"))

    # --- 2. 규모: 건폐율·용적률 -------------------------------------------
    cov = far = None
    law_name = f"{region} 도시계획 조례" if region else "지자체 도시계획 조례"
    if gb_ok:
        A = GB["annex2"]; g_ = A["general"]; dec_ = GB["decree"]
        cov, far = g_["coverage_pct"], g_["far_pct"]
        basis_gb = f"개발제한구역법 제12조, 시행령 제22조·[별표 2] 제2호가목 (시행 {dec_['effective_iso']})"
        hs = A.get("housing") or []
        h_note = ("주택·근린생활시설은 별도 기준(별표 2 제2호나목): " + " 또는 ".join(
            f"건폐율 {h['coverage_pct']}% 이하·{h['max_floors']}층 이하·용적률 {h['far_pct']}% 이하" + (f"·연면적 {h['max_floor_area_m2']}㎡(지정당시거주자 {h['max_floor_area_designated_resident_m2']}㎡) 이하" if "max_floor_area_m2" in h else "")
            for h in hs)) if hs else None
        gb_notes = ["개발제한구역에서는 법 제12조제1항 단서·시행령 별표 1에 열거된 건축물만 허가를 받아 건축할 수 있음 — 계획 시설이 허용 시설인지, 관리계획(법 제11조)에 적합한지는 허가청 확인(이 프로그램에 미연결)",
                    "국토계획법상 용도지역(자연녹지 등) 조례 상한과의 관계는 허가청 확인 — 여기서는 개발제한구역법 기준을 표시"]
        if h_note:
            gb_notes.insert(0, h_note)
        zref = zone_limits_for(inp.address, zones) if zones else None
        if zref and len(zref.get("matches", [])) == 1 and zref["matches"][0]["coverage_max_pct"] is not None:
            m0 = zref["matches"][0]
            gb_notes.append(f"참고: 같은 필지의 용도지역({m0['zone']}) 조례 상한은 건폐율 {m0['coverage_max_pct']}% / 용적률 {m0['far_max_pct']}%")
        ca = fa = "대지면적 입력 필요"
        if inp.site_area:
            ca = f"대지 × {cov}% = {_n(inp.site_area * cov / 100)}㎡"
            fa = f"대지 × {far}% = {_n(inp.site_area * far / 100)}㎡"
            vals["max_building_area"] = round(inp.site_area * cov / 100, 2)
            vals["max_floor_area"] = round(inp.site_area * far / 100, 2)
            if inp.planned_building_area:
                ca += f" | 계획 건축면적 {_n(inp.planned_building_area)}㎡ (건폐율 {inp.planned_building_area / inp.site_area * 100:.2f}%) → " + ("적합" if inp.planned_building_area <= inp.site_area * cov / 100 + 1e-6 else "초과(부적합)")
            if inp.total_floor_area:
                fa += f" | 계획 연면적 {_n(inp.total_floor_area)}㎡ (용적률 {inp.total_floor_area / inp.site_area * 100:.2f}%) → " + ("적합" if inp.total_floor_area <= inp.site_area * far / 100 + 1e-6 else "초과(제외 면적 확인)")
        gsrc = A["snapshot"]
        rows.append(Row("규모", "건폐율 → 최대 건축면적", basis_gb, f"개발제한구역 건폐율 {cov}% 이하", ca, "건축면적 상한 → 배치 가능한 매스 크기", "조건부" if inp.site_area else "미확인", gb_notes, gsrc))
        rows.append(Row("규모", "용적률 → 최대 연면적", basis_gb, f"개발제한구역 용적률 {far}% 이하", fa, "연면적 상한 → 층수·규모 계획", "조건부" if inp.site_area else "미확인", gb_notes[-2:], gsrc))
        rows.append(Row("규모", "높이(층수)", basis_gb, f"높이 {g_['max_floors']}층 이하", f"{g_['max_floors']}층 이하 (계획 층수는 입력 대상이 아님)", "층수 상한 → 매스 높이 계획", "조건부", (["주택·근린생활시설은 " + str(hs[0]['max_floors']) + "층 이하"] if hs else []), gsrc))
        ms = A.get("min_site_area_m2")
        if ms:
            if inp.site_area is not None and inp.site_area < ms:
                ap, st_ = f"대지면적 {_n(inp.site_area)}㎡ < {ms}㎡ → 건축 불허(기존 건축물 개축·재축 제외)", "확정"
            elif inp.site_area:
                ap, st_ = f"대지면적 {_n(inp.site_area)}㎡ ≥ {ms}㎡ → 해당 없음", "확정"
            else:
                ap, st_ = "대지면적 입력 필요", "미확인"
            rows.append(Row("규모", "최소 대지면적", f"개발제한구역법 시행령 [별표 2] 제1호사목", f"건축물을 건축하기 위한 대지면적 {ms}㎡ 미만이면 건축 불허", ap, "소규모 필지 건축 불가", st_, [], gsrc))
        a20 = GB.get("art20") or {}
        if a20.get("floor_area_m2"):
            thr = a20["floor_area_m2"]
            _fa2 = inp.total_floor_area or ((inp.site_area * far / 100) if inp.site_area else None)
            lab = "" if inp.total_floor_area else "(연면적 미입력 — 용적률 상한 가정)"
            if _fa2:
                ap = (f"연면적 {_n(_fa2)}㎡{lab} ≥ {thr:,}㎡ → 주민 의견청취 대상: 시·군·구·읍·면·동 게시판에 {a20['notice_days']}일 이상 게시·열람" if _fa2 >= thr
                      else f"연면적 {_n(_fa2)}㎡{lab} < {thr:,}㎡ → 해당 없음")
                st_ = "조건부"
            else:
                ap, st_ = "연면적 입력 필요", "미확인"
            rows.append(Row("인허가", "주민 의견청취", f"개발제한구역법 제12조제6항, 시행령 제20조", f"연면적 {thr:,}㎡ 이상 건축 시 주민 의견청취(게시 {a20['notice_days']}일 이상)", ap,
                            "허가 절차 기간·일정에 반영", st_, ["법 제11조제1항제5호 본문에 따른 건축은 제외"], a20["snapshot"]))
    elif gb:
        rows.append(Row("규모", "건폐율·용적률(개발제한구역)", "개발제한구역법 시행령 [별표 2]", "원문 사본을 읽지 못함", "자동 계산 불가", "최대 건축면적·연면적의 기준", "미확인", ["data/greenbelt.json 이 없거나 파싱 실패 — tools/build_greenbelt_data.py 재실행"]))
    if gb:
        pass
    elif zl["status"] == "NO_REGION":
        for it in ("건폐율", "용적률"):
            rows.append(Row("규모", it, "국토계획법 제77·78조, 지자체 도시계획 조례", "조례로 정함", "이 지역 조례 미연결", "최대 건축면적·연면적의 기준", "미연결",
                            ["해당 지자체 도시계획 조례 원문으로 직접 확인"]))
    else:
        law = zl["law"]
        src = law.get("snapshot")
        base = f"{law['name']} (시행 {law['effective']})"
        if len(zl["matches"]) == 1 and not zl["unmatched"] and zl["matches"][0]["coverage_max_pct"] is not None and zl["matches"][0]["far_max_pct"] is not None:
            m = zl["matches"][0]
            cov, far = m["coverage_max_pct"], m["far_max_pct"]
            if inp.site_area:
                vals["max_building_area"] = round(inp.site_area * cov / 100, 2)
                vals["max_floor_area"] = round(inp.site_area * far / 100, 2)
            ca = f"{_n(inp.site_area * cov / 100)}㎡" if inp.site_area else "대지면적 입력 필요"
            fa = f"{_n(inp.site_area * far / 100)}㎡" if inp.site_area else "대지면적 입력 필요"
            note = list(zl["notes"])
            if m["note"]:
                note.append("조문 단서: " + m["note"])
            note.append("상한값(이하) — 지구단위계획·정비구역·시장정비사업구역 등 특례와 용도지구별 비율은 별도 확인")
            st = "확정" if inp.site_area and not inp.has_district_plan else "조건부"
            if inp.planned_building_area and inp.site_area:
                lim = inp.site_area * cov / 100
                pc = inp.planned_building_area / inp.site_area * 100
                ca += f" | 계획 건축면적 {_n(inp.planned_building_area)}㎡ (건폐율 {pc:.2f}%) → " + ("적합" if inp.planned_building_area <= lim + 1e-6 else "초과(부적합)")
            rows.append(Row("규모", "건폐율 → 최대 건축면적", base, f"{m['zone']} {cov}% 이하",
                            f"대지 × {cov}% = {ca}", "건축면적(1층 바닥 투영면적)의 상한 → 배치 가능한 매스 크기", st, note, src))
            far_notes = ["용적률 산정에서 제외되는 면적은 건축법 시행령 제119조제1항제4호(지하층, 지상층 주차용(부속용도), 피난안전구역, 경사지붕 아래 대피공간)"]
            if inp.total_floor_area and inp.site_area and inp.total_floor_area > inp.site_area * far / 100 + 1e-6:
                far_notes.insert(0, f"입력한 계획 연면적 {_n(inp.total_floor_area)}㎡가 용적률 상한 {_n(inp.site_area * far / 100)}㎡를 넘음 — 지하층·지상 주차용 등 "
                                    "용적률 산정 제외 면적을 뺀 값인지 확인(제외 면적을 빼고도 넘으면 계획 축소 필요)")
                st = "조건부"
            if inp.total_floor_area and inp.site_area:
                fa += f" | 계획 연면적 {_n(inp.total_floor_area)}㎡ (용적률 {inp.total_floor_area / inp.site_area * 100:.2f}%) → " + ("적합" if inp.total_floor_area <= inp.site_area * far / 100 + 1e-6 else "초과(제외 면적 확인)")
            rows.append(Row("규모", "용적률 → 최대 연면적", base, f"{m['zone']} {far}% 이하",
                            f"대지 × {far}% = {fa} (용적률 산정용 연면적 기준: 지하층·지상층 주차용 등 제외)", "연면적(용적률 산정)의 상한 → 층수·규모 계획", st,
                            far_notes, src))
        else:
            txt = "; ".join(f"{m['zone']}: 건폐율 {m['coverage_max_pct'] if m['coverage_max_pct'] is not None else '미확인'}% / 용적률 {m['far_max_pct'] if m['far_max_pct'] is not None else '미확인'}%" for m in zl["matches"]) or "용도지역 미확인"
            n = ["용도지역이 둘 이상이거나 값을 읽지 못함 — 자동 계산하지 않음. 필지가 걸치면 면적 비율로 가중 검토"] + zl["notes"]
            if zl["unmatched"]:
                n.append("조례 원문에서 읽지 못한 용도지역: " + ", ".join(zl["unmatched"]))
            for it in ("건폐율", "용적률"):
                rows.append(Row("규모", it, base, txt, "자동 계산 불가", "최대 건축면적·연면적의 기준", "미확인", n, src))

    # 연면적(계획 또는 용적률 상한 가정)
    assumed_far_area = None
    if inp.total_floor_area:
        floor_area, floor_label = inp.total_floor_area, "계획 연면적"
    elif far and inp.site_area:
        floor_area, floor_label = inp.site_area * far / 100, "용적률 상한 기준 최대 연면적(가정)"
        assumed_far_area = floor_area
    else:
        floor_area, floor_label = None, None
    use_area = inp.use_floor_area or floor_area

    # --- 2-1. 대지와 도로 / 구조 안전 ---------------------------------------
    _fa = inp.total_floor_area or floor_area
    _fa_note = "" if inp.total_floor_area else "(연면적 미입력 — 용적률 상한 가정)"
    is_factory = inp.use == "공장"
    road_thr = 3000 if is_factory else 2000
    if _fa:
        applied = (f"연면적 {_n(_fa)}㎡{_fa_note} ≥ {road_thr:,}㎡ → 너비 6m 이상 도로에 4m 이상 접해야 함" if _fa >= road_thr
                   else f"연면적 {_n(_fa)}㎡{_fa_note} < {road_thr:,}㎡ → 영 제28조제2항 비대상(법 제44조제1항의 2m 접도는 별도)")
        st = "조건부"
    else:
        applied, st = "연면적 입력 필요", "미확인"
    rows.append(Row("대지·도로", "대지와 도로와의 관계", "건축법 제44조, 영 제28조제2항",
                    f"연면적 합계 {road_thr:,}㎡ 이상(공장 3,000㎡): 너비 6m 이상 도로에 4m 이상 접할 것", applied,
                    "진입도로 너비와 접도 길이로 대지 선정·출입구 계획 제한", st,
                    ["실제 접한 도로 너비·접도 길이는 입력 대상이 아님 — 지적도·도로대장으로 확인", "축사·작물 재배사 등 건축조례가 정한 건축물은 제외"],
                    "data/law_snapshots/bldg_decree_art28_road_20261112.txt"))
    if _fa:
        sub = _fa >= 200 and inp.use != "창고시설"
        applied = (f"설계자가 국토교통부령 구조기준에 따라 구조안전 확인(모든 건축물). 연면적 {_n(_fa)}㎡{_fa_note} → "
                   + ("착공신고 시 구조안전 확인서류 제출 대상(연면적 200㎡ 이상)" if sub else "연면적 기준으로는 서류 제출 대상 아님(층수·높이 등 다른 호는 별도)"))
        st = "조건부"
    else:
        applied, st = "설계자 구조안전 확인 필요", "미확인"
    rows.append(Row("구조", "구조 안전의 확인", "건축법 제48조, 영 제32조", "국토교통부령 구조기준에 따른 구조안전 확인. 층수 2층 이상·연면적 200㎡ 이상·높이 13m 이상·처마높이 9m 이상·기둥 간격 10m 이상 등은 확인서류 제출",
                    applied, "구조 시스템·스팬 계획의 기준(구조설계기준 KDS 등은 부령·고시 — 미연결)", st,
                    ["제출 대상 호 일부(층수·높이·스팬)는 입력하지 않아 판정하지 않음 — 영 제32조제2항 각 호 확인"],
                    "data/law_snapshots/bldg_decree_art32_structure_20261112.txt"))

    # --- 3. 일조(정북) ------------------------------------------------------
    sun_zone = [c for c in cats if c in ("전용주거", "일반주거")]
    if zinfo["known"] and sun_zone:
        hs = (10, 17, 20)
        parts = []
        for h in hs:
            r = sun_setback(region or "", h)
            if r["status"] == "PREVIEW":
                parts.append(f"{h}m 부분 법 {r['law_min_m']:g}m" + (f"/조례 {r['ordinance_text_m']:g}m→안전측 {r['conservative_m']:g}m" if r["conflict"] else ""))
            else:
                law = north_light_law_minimum(h)
                parts.append(f"{h}m 부분 법 하한 {law['law_min_m']:g}m(조례 미연결)")
        stale = [sun_region_data(region)["cites"] == "영 제86조제1항"] if region and sun_region_data(region) else [False]
        n = ["정북 인접 대지가 전용·일반주거지역이 아니면 적용되지 않음(영 제86조제2항) — 인접 대지 용도지역 확인",
             "법 하한 = 10m 이하 1.5m / 10~17m 5m / 17m 초과 부분 높이의 1/2"]
        if stale[0]:
            n.append("조례가 영 제86조제1항(2026-11-12 삭제)을 인용하는 채로 남아 있어 법 개정 반영 여부 확인 필요")
        rows.append(Row("높이·일조", "정북방향 일조 이격", "건축법 제61조제1항, 영 제86조, " + (f"{region} 건축 조례 일조 조문" if region and sun_region_data(region) else "건축 조례"),
                        "전용·일반주거지역 안 건축물: 정북 인접 대지경계선에서 높이별 이격", "; ".join(parts),
                        "북측 경계에서 높이에 따라 매스를 후퇴(사선) — 최대 높이와 북측 배치에 직접 영향", "조건부", n,
                        "data/law_snapshots/bldg_act_art61_20261112.txt"))
    elif zinfo["known"]:
        rows.append(Row("높이·일조", "정북방향 일조 이격", "건축법 제61조제1항", "전용·일반주거지역 안 건축물만 대상",
                        f"용도지역({', '.join(cats)})은 대상이 아님", "정북 일조 사선은 적용되지 않음(공동주택 채광 이격 등 다른 규정은 별도)", "확정",
                        ["필지가 걸치거나 용도지역 조회가 불완전하면 재확인", "건축법 시행령 제86조제3항(공동주택 채광)은 별도 검토"],
                        "data/law_snapshots/bldg_act_art61_20261112.txt"))
    else:
        rows.append(Row("높이·일조", "정북방향 일조 이격", "건축법 제61조제1항", "전용·일반주거지역 안 건축물만 대상", "용도지역 미확인", "용도지역을 알아야 적용 여부 판단", "미확인"))

    # --- 4. 주차 ------------------------------------------------------------
    basis_name, rules, fn, pnotes = _parking_basis(region)
    if spec.parking_manual:
        rows.append(Row("주차", "부설주차장 법정 대수", basis_name, "「주택건설기준 등에 관한 규정」 제27조 등 별도 규정 인용(세대수·전용면적 기준)",
                        "자동 산정하지 않음", "주택 규모(세대수·전용면적)로 산정 — 별도 계산 필요", "미확인", pnotes + ["조례 별표 제5호 원문 참조"]))
        pk_count = None
    else:
        key, multi_note = pick_parking(rules, spec, inp.is_public)
        if key is None:
            rows.append(Row("주차", "부설주차장 법정 대수", basis_name, "해당 용도의 기준을 자동으로 찾지 못함", "자동 산정하지 않음(다른 분류로 대체하지 않음)",
                            "조례 별표 원문으로 용도별 기준 확인", "미확인", list(pnotes) + ([multi_note] if multi_note else [])))
            pk_count = None
        else:
            std = _rule_standard(rules, key)
            n = list(pnotes) + ([multi_note] if multi_note else [])
            n.append("시설면적 = 공용면적 포함 바닥면적의 합계(시설물 안 주차용 면적 제외) — 입력한 면적이 이에 맞는지 확인")
            if region and pk_region_data(region) and len(pk_region_data(region)["columns"]) > 1:
                n.append("조례 표가 대지 구역별 두 열(도시지역·지구단위계획구역 / 관리지역)로 나뉨 — 도시지역 열 기준으로 계산")
            if use_area:
                res = fn([(key, use_area)], inp.parking_variant)
                applied = f"{_fmt_parking(res)} (시설면적 {_n(use_area)}㎡" + (f" — {floor_label}" if not inp.use_floor_area and floor_label else "") + ")"
                for x in res.get("notes", []):
                    if x not in n:
                        n.append(x)
                pk_count = res.get("count")
                if res.get("count") is not None and not res.get("ambiguous"):
                    ref = res["count"]
                    if inp.guideline_parking:
                        applied += f" | 공모지침 법정 {inp.guideline_parking}대"
                        ref = max(ref, inp.guideline_parking)
                        n.append("공모지침 값과 조례 계산값 중 큰 값을 기준으로 계획을 판정함 — 지침 우선 여부는 공고문 확인")
                    if inp.planned_parking is not None:
                        applied += f" | 계획 {inp.planned_parking}대 → " + ("적합" if inp.planned_parking >= ref else f"부족({ref - inp.planned_parking}대)")
                if pk_count is not None:
                    vals["parking_count"] = pk_count
                status = "확정" if (res.get("status") == "PREVIEW" and not res.get("ambiguous") and inp.total_floor_area) else "조건부"
            else:
                applied, pk_count, status = "시설면적(연면적) 입력 필요", None, "미확인"
            rows.append(Row("주차", "부설주차장 법정 대수", basis_name, std, applied,
                            "지상·지하 주차 면적과 차량 동선·진출입구 계획의 기준(용도변경·증축은 별도)", status, n))
    # 장애인 전용주차
    if pk_count:
        if region == "대전광역시":
            exact = pk_count * 0.03
            vals["accessible_parking_min"] = math.ceil(exact)
            rows.append(Row("주차", "장애인 전용주차구획", f"{DJ_META['parking']['name']} 제18조제1항 (주차장법 시행령 별표 1 비고 10)",
                            "부설주차장 주차대수의 100분의 3 이상(10대 미만은 제외)", f"{pk_count}대 × 3% = {exact:.2f}대 → 최소 {math.ceil(exact)}대(올림, 끝수 처리 규정은 원문에 없음)",
                            "주출입구 인접 위치·면적 확보", "조건부", ["세부 기준은 장애인등편의법 시행규칙 별표 1"]))
        else:
            lo, hi = math.ceil(pk_count * 0.02), math.ceil(pk_count * 0.04)
            rows.append(Row("주차", "장애인 전용주차구획", "주차장법 시행령 별표 1 비고 10", "주차대수의 2%~4% 범위에서 조례로 정하는 비율 이상(10대 미만은 제외)",
                            f"{pk_count}대 기준 {lo}~{hi}대 범위(조례 비율 확인)", "주출입구 인접 위치·면적 확보", "미연결", ["조례의 장애인 전용주차구획 비율은 이 지역에 연결되어 있지 않음"]))

    # --- 5. 조경 -------------------------------------------------------------
    land = _landscape().get(region) if region else None
    green = [z for z in zones if "녹지지역" in z.replace(" ", "")]
    if inp.site_area is not None and inp.site_area < 200:
        rows.append(Row("대지 안 시설", "조경", "건축법 제42조제1항", "면적 200㎡ 이상 대지에 건축하는 경우 조경", f"대지면적 {_n(inp.site_area)}㎡ — 200㎡ 미만이라 대상 아님", "조경면적 확보 의무 없음", "확정", [],
                        "data/law_snapshots/bldg_act_art42_landscape.txt"))
    elif green:
        rows.append(Row("대지 안 시설", "조경", "건축법 시행령 제27조제1항제1호", "녹지지역에 건축하는 건축물은 조경 등의 조치를 하지 않을 수 있음", f"용도지역 {', '.join(green)} — 면제 대상", "조경면적 확보 의무 없음", "확정", [],
                        "data/law_snapshots/bldg_decree_art27_landscape_20261112.txt"))
    elif land and land["status"] == "ok":
        o = land["ordinance"]
        tiers = land["tiers"]
        std = f"{o['name']} {o['article']}: 연면적 {_n(tiers[0]['max'])}㎡ 미만 {tiers[0]['pct']}% / {_n(tiers[1]['lo'])}~{_n(tiers[1]['hi'])}㎡ {tiers[1]['pct']}% / {_n(tiers[2]['min'])}㎡ 이상 {tiers[2]['pct']}% (대지면적 대비)"
        n = ["옥상 조경은 옥상조경면적의 2/3를 산입하되 법정 조경면적의 50%를 초과할 수 없음(영 제27조제3항)",
             "영 제27조제1항 면제 대상(공장·축사·산업단지 등)과 조례가 정하는 면제 건축물은 별도 확인"] + land["special_notes"]
        if floor_area and inp.site_area:
            pct = pct_at(tiers, floor_area)
            vals["landscape_min_area"] = round(inp.site_area * pct / 100, 2)
            applied = f"연면적 {_n(floor_area)}㎡({floor_label}) → 대지면적의 {pct}% = {_n(inp.site_area * pct / 100)}㎡ 이상"
            status = "조건부" if assumed_far_area else "확정"
        else:
            applied, status = "대지면적·연면적 입력 필요", "미확인"
        rows.append(Row("대지 안 시설", "조경 → 최소 조경면적", f"건축법 제42조제1항, 영 제27조, {o['name']} (시행 {o['effective']})", std, applied,
                        "대지 안에 확보해야 하는 조경 면적 → 배치·지하주차 상부 처리에 영향", status, n, o.get("snapshot")))
    else:
        rows.append(Row("대지 안 시설", "조경", "건축법 제42조제1항, 영 제27조", "면적 200㎡ 이상 대지: 용도지역·규모에 따라 조례로 정하는 기준", "이 지역 조례 미연결", "조경면적 확보 의무", "미연결",
                        ["해당 지자체 건축 조례의 '대지의 조경' 조문 확인"], "data/law_snapshots/bldg_act_art42_landscape.txt"))

    # --- 6. 공개공지 ---------------------------------------------------------
    in_zone = [c for c in cats if c in OPEN_SPACE_ZONES]
    open_std = "대지면적의 10% 이하 범위에서 건축조례로 정함. 설치 시 용적률·높이 제한을 1.2배 이하 범위에서 완화(영 제27조의2제4항, 조례 기준이 더 크면 조례)"
    on = list(land["open_space"].items()) if land and land.get("open_space", {}).get("snapshot") else []
    open_src = land["open_space"]["snapshot"] if on else None
    quotes = []
    if open_src:
        txt = (ROOT / open_src).read_text(encoding="utf-8").splitlines()
        quotes = [l.strip()[:150] for l in txt if ("퍼센트" in l or "100분의" in l) and not l.startswith("#")][:3]
    n = []
    if quotes:
        n.append("조례 원문 발췌(비율·대상은 조문 참조): " + " / ".join(quotes))
    elif region:
        n.append("조례 조문을 읽지 못함 — 건축 조례 '공개공지 등의 확보' 조문 확인")
    if not zinfo["known"]:
        applied, status = "용도지역 미확인", "미확인"
    elif not in_zone:
        applied, status = f"용도지역({', '.join(cats)})은 법 제43조 대상 지역(일반주거·준주거·상업·준공업)이 아님 — 시장·군수가 지정·공고한 지역이면 대상", "조건부"
    elif spec.open_space:
        if use_area and use_area >= 5000:
            applied, status = f"해당 용도 바닥면적 {_n(use_area)}㎡ ≥ 5,000㎡ → 법정 대상(영 제27조의2제1항제1호): 공개공지 설치 의무", "조건부" if not inp.use_floor_area else "확정"
        elif use_area:
            applied, status = f"해당 용도 바닥면적 {_n(use_area)}㎡ < 5,000㎡ → 영 기준 비대상(조례가 정하는 다중이용시설이면 대상)", "조건부"
        else:
            applied, status = "해당 용도 바닥면적 입력 필요(5,000㎡ 이상이면 대상)", "미확인"
    else:
        applied, status = "영 제27조의2제1항제1호 열거 용도가 아님 — 조례가 정하는 다중이용시설(의료·운동·위락 등)이면 대상", "조건부"
    rows.append(Row("대지 안 시설", "공개공지 등", "건축법 제43조, 영 제27조의2, " + (f"{land['ordinance']['name']}" if land else "건축 조례"), open_std, applied,
                    "대상이면 대지 일부를 일반이 쓰는 공지로 계획(조경면적과 겸용 가능) — 용적률·높이 완화 혜택", status, n, open_src or "data/law_snapshots/bldg_decree_art27_2_openspace_20261112.txt"))

    # --- 7. 피난·방화 --------------------------------------------------------
    rows.append(Row("피난·방화", "직통계단까지 보행거리", "건축법 시행령 제34조제1항",
                    "거실 각 부분에서 직통계단까지 30m 이하. 주요구조부가 내화구조·불연재료이면 50m(16층 이상 공동주택의 16층 이상은 40m), 자동화 공장 75m(무인화 100m)",
                    "내화·불연 구조(통상의 철근콘크리트·철골조)면 50m 이하", "코어(계단) 배치 간격과 복도 길이의 상한", "조건부",
                    ["지하층에 설치하는 바닥면적 300㎡ 이상 공연장·집회장·관람장·전시장은 50m 완화 대상에서 제외"], "data/law_snapshots/bldg_decree_art34_stairs_20261112.txt"))
    ho, thr, f3 = spec.egress
    cond = f"{thr}㎡ 이상" + (" (3층 이상의 층)" if f3 else "")
    applied = f"{_HO_TEXT[ho]}: {cond}이면 직통계단 2개소 이상"
    st = "미확인"
    if inp.typical_floor_area:
        need = inp.typical_floor_area >= thr
        applied += f" → 입력한 대표층 {_n(inp.typical_floor_area)}㎡ {'≥' if need else '<'} {thr}㎡ → " + ("2개소 이상 필요" if need else "2개소 의무 대상 아님(1개소 가능)")
        st = "조건부"
    else:
        applied += " (대표층 거실 바닥면적을 입력하면 판정)"
    if inp.basement_floor_area is not None:
        applied += f"; 지하층 거실 {_n(inp.basement_floor_area)}㎡ → " + ("지하층 2개소 이상(영 제34조제2항제5호 200㎡ 이상)" if inp.basement_floor_area >= 200 else "지하층 2개소 의무 대상 아님")
    else:
        applied += "; 지하층 거실 바닥면적 200㎡ 이상이면 지하층도 2개소 이상(영 제34조제2항제5호)"
    rows.append(Row("피난·방화", "직통계단 2개소 이상 설치 대상", "건축법 시행령 제34조제2항 · 국토교통부령(설치 기준)", cond, applied,
                    "코어 수·위치(양방향 피난) 결정", st, ["계단 위치·거리 등 세부 설치 기준은 국토교통부령(피난·방화구조 규칙) — 미연결"], "data/law_snapshots/bldg_decree_art34_stairs_20261112.txt"))
    if floor_area:
        applied = ("연면적 1,000㎡ 초과 → 주요구조부가 내화구조·불연재료이면 방화구획 대상" if floor_area > 1000 else "연면적 1,000㎡ 이하 → 방화구획 대상 아님") + f" (연면적 {_n(floor_area)}㎡ — {floor_label})"
        st = "조건부"
    else:
        applied, st = "연면적 입력 필요", "미확인"
    rows.append(Row("피난·방화", "방화구획", "건축법 시행령 제46조제1항", "연면적 1,000㎡ 초과, 주요구조부가 내화구조·불연재료: 내화구조 바닥·벽, 방화문·자동방화셔터로 구획", applied,
                    "층·면적별 구획 계획(코어·샤프트 배치에 영향)", st,
                    ["구획 면적 기준(예: 10층 이하 층 바닥면적 1,000㎡, 스프링클러 설치 시 3,000㎡)은 국토교통부령 — 이 프로그램에 미연결, 완화 대상(영 제46조제2항)도 별도 확인"],
                    "data/law_snapshots/bldg_decree_art46_firecompart_20261112.txt"))

    # --- 8. 미연결 항목(드러내기) ---------------------------------------------
    for it, basis, how in (
        ("가로구역별 높이·도로 사선", "건축법 제60조·제61조 외, 지구단위계획", "도로 너비별 사선 제한·가로구역 최고높이는 미연결 — 지구단위계획 지침과 함께 확인"),
        ("대지 안의 공지·건축선", "건축법 제46조, 영 제31조, 건축 조례", "이격 거리(용도지역·용도별)와 건축선 후퇴는 미연결 — 건축 조례 확인"),
        ("장애인 편의시설", "장애인등편의법 시행령 별표 2", "대상 시설·설치 기준은 미연결"),
        ("신·재생에너지 공급의무·녹색건축 인증·제로에너지건축물 인증", "신에너지 및 재생에너지 개발·이용·보급 촉진법 시행령 제15조, 녹색건축 인증에 관한 규칙, 제로에너지건축물 인증에 관한 규칙", "공급 비율·인증 등급은 용도·규모·공공 여부에 따라 달라 미연결 — 원문 확인"),
        ("심의·평가 대상", "건축위원회 심의, 교통영향평가, 경관 심의", "규모별 대상 기준은 미연결"),
    ):
        rows.append(Row("미연결 항목", it, basis, "—", "자동 검토하지 않음", "설계 초기에 별도 확인 필요", "미연결", [how]))
    _ITEM_KEY = {"건폐율 → 최대 건축면적": "max_building_area", "용적률 → 최대 연면적": "max_floor_area", "부설주차장 법정 대수": "parking_count",
                 "장애인 전용주차구획": "accessible_parking_min", "조경 → 최소 조경면적": "landscape_min_area"}
    for r in rows:
        k = _ITEM_KEY.get(r.item)
        if k and k in vals:
            r.key, r.value = k, vals[k]
    return rows


# ---------------------------------------------------------------------------
def summary_values(rows):
    """주요 수치 {key: (라벨, 값)} — 화면 요약·다른 도구 연계용."""
    labels = {"max_building_area": "최대 건축면적(㎡)", "max_floor_area": "최대 연면적(㎡)", "parking_count": "법정 주차대수(대)",
              "accessible_parking_min": "장애인 전용 최소(대)", "landscape_min_area": "최소 조경면적(㎡)"}
    return {r.key: (labels[r.key], r.value) for r in rows if r.key in labels and r.value is not None}


def review_to_markdown(rows, context=None):
    L = ["# 법규검토서", ""]
    for k, v in (context or {}).items():
        L.append(f"- {k}: {v}")
    L += ["", "> 사전 검토용입니다. 법적 적합 판정·인허가 검토를 대체하지 않습니다. 상태: 확정 / 조건부 / 미확인 / 미연결", ""]
    cur = None
    for r in rows:
        if r.section != cur:
            cur = r.section
            L += ["", f"## {cur}", "", "| 법규명 및 조항 | 대상 | 법적 기준 | 설계기준(이 대지 적용·계획) | 설계 영향 | 상태 |", "|---|---|---|---|---|---|"]
        esc = lambda s: str(s).replace("|", "/").replace("\n", " ")
        L.append(f"| {esc(r.basis)} | {esc(r.item)} | {esc(r.standard)} | {esc(r.applied)} | {esc(r.impact)} | {r.status} |")
    L += ["", "## 비고(항목별)", ""]
    for r in rows:
        if r.notes:
            L.append(f"- **{r.item}**: " + " / ".join(r.notes))
    return "\n".join(L)


def review_to_json(rows, context=None):
    return json.dumps({"context": context or {}, "rows": [r.as_dict() for r in rows]}, ensure_ascii=False, indent=2)
