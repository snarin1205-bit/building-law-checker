"""개발제한구역법·시행령(별표 2 제2호, 제20조, 제22조, 법 제12조) → 사본 + data/greenbelt.json (네트워크 필요, CI 제외).

사용: python tools/build_greenbelt_data.py   — 읽지 못한 값은 넣지 않고 status 로 표시한다. 수정 금지(재생성).
"""
import html
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import build_ordinance_data as bo  # noqa: E402
from greenbelt_parse import parse_resident_opinion, parse_standard  # noqa: E402

TODAY = "2026-11-23"
NAME_DEC = "개발제한구역의 지정 및 관리에 관한 특별조치법 시행령"
NAME_ACT = "개발제한구역의 지정 및 관리에 관한 특별조치법"


def _clean(b):
    t = re.sub(r"<!\[CDATA\[|\]\]>", "", b)
    t = re.sub(r"<[^>]+>", "\n", t)
    t = html.unescape(t)
    return "\n".join(l.strip() for l in t.splitlines() if l.strip())


def _law(name):
    srch = bo.get(endpoint="lawSearchList", target="law", query=name, numOfRows="10", pageNo="1")
    for m in re.finditer(r"<law id.*?</law>", srch, re.S):
        b = m.group(0)
        g = lambda t: (re.search(rf"<{t}>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{t}>", b, re.S) or [0, ""])[1]
        if g("법령명한글").strip() == name and g("현행연혁코드") == "현행":
            return {"mst": g("법령일련번호"), "promulgation_no": g("공포번호"), "effective": g("시행일자")}
    return None


def _article(xml, no):
    for m in re.finditer(r"<조문단위[^>]*>.*?</조문단위>", xml, re.S):
        b = m.group(0)
        if re.search(rf"<조문번호>{no}</조문번호>", b) and "<조문여부>조문</조문여부>" in b and not re.search(r"<조문가지번호>", b):
            return _clean(b)
    return None


def _annex(xml, no):
    for m in re.finditer(r"<별표단위[^>]*>.*?</별표단위>", xml, re.S):
        b = m.group(0)
        if f"<별표번호>{no}<" in b:
            c = re.search(r"<별표내용>(.*?)</별표내용>", b, re.S)
            return html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", c.group(1))) if c else None
    return None


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    snaps = ROOT / "data" / "law_snapshots"
    dec, act = _law(NAME_DEC), _law(NAME_ACT)
    if not dec or not act:
        raise SystemExit("법령을 찾지 못함")
    xd = bo.get(endpoint="lawService", target="law", MST=dec["mst"], type="XML")
    xa = bo.get(endpoint="lawService", target="law", MST=act["mst"], type="XML")

    def iso(e):
        return f"{e[:4]}-{e[4:6]}-{e[6:]}"

    def save(fn, title, meta, body):
        hdr = (f"# 출처: 법제처 국가법령정보센터 (law.go.kr), 조회일 {TODAY}\n# 법령: {title}\n"
               f"# 공포번호 {meta['promulgation_no']}, 시행 {iso(meta['effective'])}(현행), 법령일련번호 {meta['mst']}\n"
               "# API 응답에서 태그만 제거한 텍스트(조문 번호·항 번호 줄이 중복 표기됨). 수정 금지.\n\n")
        (snaps / fn).write_text(hdr + body + "\n", encoding="utf-8")
        return f"data/law_snapshots/{fn}"

    annex = _annex(xd, "0002")
    a20, a22, a12 = _article(xd, "20"), _article(xd, "22"), _article(xa, "12")
    out = {"generated": TODAY, "note": "개발제한구역법 시행령 별표 2 제2호 등 원문 파싱값(수정 금지, tools/build_greenbelt_data.py 로 재생성).",
           "decree": {"name": NAME_DEC, **dec, "effective_iso": iso(dec["effective"])},
           "act": {"name": NAME_ACT, **act, "effective_iso": iso(act["effective"])}}
    if annex:
        out["annex2"] = {"snapshot": save("greenbelt_decree_annex2_20260918.txt", f"{NAME_DEC} [별표 2] 허가 또는 신고의 세부기준(제22조 관련)", dec, annex.strip()),
                         **parse_standard(annex)}
    if a22:
        out["art22"] = save("greenbelt_decree_art22.txt", f"{NAME_DEC} 제22조(허가 또는 신고의 기준)", dec, a22)
    if a20:
        out["art20"] = {"snapshot": save("greenbelt_decree_art20_resident.txt", f"{NAME_DEC} 제20조(주민의 의견청취 등의 대상 및 절차)", dec, a20),
                        **parse_resident_opinion(a20)}
    if a12:
        out["act12"] = save("greenbelt_act_art12.txt", f"{NAME_ACT} 제12조(개발제한구역에서의 행위제한)", act, a12)
    (ROOT / "data" / "greenbelt.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k in ("annex2", "art20")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
