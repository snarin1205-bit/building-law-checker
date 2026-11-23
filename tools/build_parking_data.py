"""광역시·특별시 주차장 조례의 부설주차장 설치기준 → 사본 + data/parking_ordinances.json (네트워크 필요, CI 제외).

사용: python tools/build_parking_data.py
조례 본문과 설치기준 별표(hwp 첨부 또는 XML 본문)를 법제처에서 받아 사본으로 저장하고, ordinance_parking_parse 로
구조화한다. 단순·명확한 분류만 계산 규칙이 되고 나머지는 원문 텍스트를 manual 로 보관한다. 수정 금지(재생성).
"""
import html
import json
import pathlib
import re
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import build_ordinance_data as bo  # noqa: E402  (get/find/field/clean/hwp_text 재사용)
from ordinance_parking_parse import parse_parking_annex  # noqa: E402

TODAY = "2026-11-23"
CITIES = [
    ("서울특별시", "서울특별시 주차장 설치 및 관리 조례", "서울특별시"),
    ("부산광역시", "부산광역시 주차장 설치 및 관리 조례", "부산광역시"),
    ("대구광역시", "대구광역시 주차장 설치 및 관리 조례", "대구광역시"),
    ("인천광역시", "인천광역시 주차장 설치 및 관리 조례", "인천광역시"),
    ("광주광역시", "광주광역시 주차장 조례", "(구)광주광역시"),
    ("대전광역시", "대전광역시 주차장 조례", "대전광역시"),
    ("울산광역시", "울산광역시 주차장 설치 및 관리 조례", "울산광역시"),
    ("세종특별자치시", "세종특별자치시 주차장 설치 및 관리 조례", "세종특별자치시"),
]
EXCLUDE_TITLE = ("제한", "중ㆍ대형", "중·대형", "예정지역", "배치", "보조", "주차방법", "요금", "서식", "별지")
RELATED_HINT = ("제한", "예정지역", "중ㆍ대형", "중·대형", "특별", "해제")


def slice_annex(text):
    """합본 hwp 등에서 '부설주차장의 설치…' 별표 구간만 잘라낸다."""
    lines = text.splitlines()
    start = None
    for i, l in enumerate(lines):
        if "부설주차장" in l and ("설치대상" in l or "설치기준" in l) and "제한" not in l:
            win = " ".join(lines[i:i + 4])
            if "시설물" in win or "건축물" in win:
                start = i - 1 if i > 0 and re.match(r"^\s*\[?\s*별표", lines[i - 1]) else i
                break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if re.match(r"^\s*\[\s*(별표|별지)", lines[j]):
            end = j
            break
    return "\n".join(lines[start:end])


def annex_units(xml):
    return [m.group(0) for m in re.finditer(r"<별표단위[^>]*>.*?</별표단위>", xml, re.S)]


def download_hwp_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return bo.hwp_text(r.read())


def parking_annex(xml):
    """설치기준 별표 텍스트 찾기. 반환: (제목, 방법, 텍스트, 관련 별표 제목 목록)."""
    units = annex_units(xml)
    related = [bo.field(u, "별표제목") for u in units
               if "주차" in bo.field(u, "별표제목") and any(h in bo.field(u, "별표제목") for h in RELATED_HINT)]
    # 1) 제목으로 식별
    for u in units:
        t = bo.field(u, "별표제목")
        if "설치" in t and ("부설" in t or "시설물" in t) and not any(x in t for x in EXCLUDE_TITLE):
            # hwp 첨부가 있으면 우선(파서를 이 추출 형식으로 검증함), 없을 때만 XML 본문
            if "hwp" in bo.field(u, "별표첨부파일구분").lower():
                txt = download_hwp_text(bo.field(u, "별표첨부파일명"))
                return t, "hwp", slice_annex(txt) or txt, related
            body = bo.field(u, "별표내용")
            plain = html.unescape(re.sub(r"<!\[CDATA\[|\]\]>|<[^>]+>", "", body))
            if len(plain.strip()) > 300:
                return t, "xml본문", plain, related
    # 2) 제목이 '별표'뿐인 합본 hwp 등: 내용으로 식별
    for u in units:
        if "hwp" in bo.field(u, "별표첨부파일구분").lower():
            txt = download_hwp_text(bo.field(u, "별표첨부파일명"))
            cut = slice_annex(txt)
            if cut and "시설면적" in cut:
                return bo.field(u, "별표제목") + "(합본 hwp에서 설치기준 구간 추출)", "hwp", cut, related
    return None, None, None, related


def main():
    snaps = ROOT / "data" / "law_snapshots" / "parking"
    snaps.mkdir(parents=True, exist_ok=True)
    regions, report = {}, []
    for key, name, org in CITIES:
        f = bo.find(name, org)
        if not f:
            report.append(f"[못찾음] {key}")
            continue
        mst, pn, eff = f
        xml = bo.get(endpoint="lawService", target="ordin", MST=mst, type="XML")
        title, method, annex_text, related = parking_annex(xml)
        if not annex_text:
            report.append(f"[별표없음] {key} {name}")
            continue
        eff_iso = f"{eff[:4]}-{eff[4:6]}-{eff[6:]}"
        base = f"{key}_주차장조례_{eff}"
        body_txt = bo.clean(xml)
        hdr = (f"# 출처: 법제처 국가법령정보센터 자치법규, 조회일 {TODAY}\n# 자치법규: {name} ({org}) 공포번호 {pn}, 시행일 {eff_iso}, 자치법규일련번호 {mst}\n"
               "# API 응답에서 태그만 제거한 텍스트. 수정 금지.\n\n")
        (snaps / f"{base}.txt").write_text(hdr + body_txt + "\n", encoding="utf-8")
        annex_rel = f"data/law_snapshots/parking/{base}_설치기준별표.txt"
        (ROOT / annex_rel).write_text(
            f"# 출처: 법제처 자치법규 {name} 의 별표 '{title}' ({method}). 조회일 {TODAY}\n"
            + ("# 추출 방법: hwp 바이너리 본문을 텍스트 추출기로 변환(표 서식이 평문으로 풀림). 의심되면 원본 hwp와 대조.\n" if method == "hwp" else "")
            + "# 수정 금지.\n\n" + annex_text + "\n", encoding="utf-8")
        parsed = parse_parking_annex(annex_text)
        regions[key] = {
            "ordinance": {"name": name, "org": org, "mst": mst, "promulgation_no": pn, "effective": eff_iso,
                          "snapshot": f"data/law_snapshots/parking/{base}.txt", "annex_snapshot": annex_rel,
                          "annex_title": title, "annex_method": method},
            "related_annexes": related,
            **parsed,
        }
        kinds = {}
        for c in parsed["categories"]:
            kinds[c["kind"]] = kinds.get(c["kind"], 0) + 1
        report.append(f"[{method:7}] {key:8} 시행 {eff_iso} 열 {len(parsed['columns']) or 1} 분류 {len(parsed['categories'])} {kinds} 관련별표 {len(related)}")
    out = {"generated": TODAY, "note": "원문에서 읽은 값만 포함. manual 은 원문 텍스트 보관(자동 계산 안 함). 수정 금지(tools/build_parking_data.py 로 재생성).",
           "regions": regions}
    (ROOT / "data" / "parking_ordinances.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(report))


if __name__ == "__main__":
    main()
