"""광역시·특별시 도시계획 조례 원문 → 사본 + data/ordinance_zone_limits.json 생성 (네트워크 필요, CI 제외).

사용: python tools/build_ordinance_data.py
환경변수 LAW_PROXY_URL (기본: 법제처 프록시). 조례 원문은 법제처 자치법규 API(ordinSearchList/lawService)에서 받고,
별표가 첨부파일(hwp)인 경우 해당 파일에서 텍스트를 추출한다(olefile 필요, 선택).
읽지 못한 값은 넣지 않는다. 출력 파일은 사람이 수정하지 말 것.
"""
import html
import json
import os
import pathlib
import re
import struct
import sys
import urllib.parse
import urllib.request
import zlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ordinance_parse import CANON_ZONES, parse_ordinance, zone_table  # noqa: E402

PROXY = os.environ.get("LAW_PROXY_URL", "https://law-proxy-nine.vercel.app/api/law")
TODAY = "2026-11-23"
CITIES = [
    # (지역 키, 조례명, 지자체기관명)
    ("서울특별시", "서울특별시 도시계획 조례", "서울특별시"),
    ("부산광역시", "부산광역시 도시계획 조례", "부산광역시"),
    ("대구광역시", "대구광역시 도시계획 조례", "대구광역시"),
    ("인천광역시", "인천광역시 도시계획 조례", "인천광역시"),
    ("광주광역시", "광주광역시 도시계획 조례", "(구)광주광역시"),
    ("대전광역시", "대전광역시 도시계획 조례", "대전광역시"),
    ("울산광역시", "울산광역시 도시계획 조례", "울산광역시"),
    ("세종특별자치시", "세종특별자치시 도시계획 조례", "세종특별자치시"),
]


def get(**p):
    import time
    last = None
    for attempt in range(4):  # 프록시의 일시적 502/네트워크 오류 재시도
        try:
            with urllib.request.urlopen(PROXY + "?" + urllib.parse.urlencode(p), timeout=120) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise last


def field(b, t):
    m = re.search(rf"<{t}[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{t}>", b, re.S)
    return m.group(1).strip() if m else ""


def clean(x):
    t = re.sub(r"<!\[CDATA\[|\]\]>", "", x)
    t = html.unescape(re.sub(r"<[^>]+>", "\n", t))
    return "\n".join(l.strip() for l in t.splitlines() if l.strip())


def find(name, org):
    for q in (name, name.replace(org + " ", "")):
        for pg in range(1, 4):
            s = get(endpoint="ordinSearchList", query=q, numOfRows="50", pageNo=str(pg))
            for m in re.finditer(r"<law id.*?</law>", s, re.S):
                b = m.group(0)
                if field(b, "자치법규명") == name and field(b, "지자체기관명") == org:
                    return field(b, "자치법규일련번호"), field(b, "공포번호"), field(b, "시행일자")
    return None


def hwp_text(data):
    import olefile
    import io
    ole = olefile.OleFileIO(io.BytesIO(data))
    hdr = ole.openstream("FileHeader").read()
    compressed = bool(struct.unpack("<I", hdr[36:40])[0] & 1)
    out = []
    for n in sorted(x for x in ole.listdir() if x[0] == "BodyText"):
        d = ole.openstream(n).read()
        if compressed:
            d = zlib.decompress(d, -15)
        i = 0
        while i + 4 <= len(d):
            h = struct.unpack("<I", d[i:i + 4])[0]
            tag, size = h & 0x3FF, (h >> 20) & 0xFFF
            i += 4
            if size == 0xFFF:
                size = struct.unpack("<I", d[i:i + 4])[0]
                i += 4
            rec = d[i:i + size]
            i += size
            if tag == 67:
                t, j = [], 0
                while j + 2 <= len(rec):
                    c = struct.unpack("<H", rec[j:j + 2])[0]
                    if c < 32:
                        if c in (1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 14, 15, 16, 17, 18, 21, 22, 23):
                            j += 16
                            continue
                        if c in (10, 13):
                            t.append("\n")
                        else:
                            t.append(" ")
                    else:
                        t.append(chr(c))
                    j += 2
                out.append("".join(t))
    return "\n".join(l for l in "\n".join(out).splitlines() if l.strip())


def hwpx_text(data):
    """HWPX(zip+XML) 본문 텍스트: 문단(hp:p)마다 한 줄. 표 셀 안의 문단도 문서 순서대로 한 줄씩."""
    import io
    import xml.etree.ElementTree as ET
    import zipfile
    z = zipfile.ZipFile(io.BytesIO(data))
    names = sorted((n for n in z.namelist() if re.match(r"Contents/section\d+\.xml$", n)),
                   key=lambda n: int(re.search(r"(\d+)\.xml$", n).group(1)))
    out = []
    for n in names:
        root = ET.fromstring(z.read(n))
        ns_p = next((t[: t.index("}") + 1] for t in (e.tag for e in root.iter()) if t.endswith("}p")), "")
        for p in root.iter(ns_p + "p"):
            parts = []
            for run in p.findall(ns_p + "run"):  # 직접 자식 run 만(중첩 표의 문단은 별도로 순회)
                for t in run.findall(ns_p + "t"):
                    parts.append("".join(t.itertext()))
            line = "".join(parts).strip()
            if line:
                out.append(line)
    return "\n".join(out)


def annex_hwp_for(xml, article_no_hint="건폐율"):
    """별표 중 제목에 '건폐율'이 들어간 hwp 첨부를 내려받아 텍스트로."""
    for m in re.finditer(r"<별표단위[^>]*>.*?</별표단위>", xml, re.S):
        blk = m.group(0)
        title = field(blk, "별표제목")
        if article_no_hint in title and "hwp" in field(blk, "별표첨부파일구분").lower():
            url = field(blk, "별표첨부파일명")
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=120) as r:
                return title, hwp_text(r.read())
    return None, None


def main():
    snaps = ROOT / "data" / "law_snapshots" / "ordinances"
    snaps.mkdir(parents=True, exist_ok=True)
    regions, report = {}, []
    for key, name, org in CITIES:
        f = find(name, org)
        if not f:
            report.append(f"[못찾음] {key}")
            continue
        mst, pn, eff = f
        xml = get(endpoint="lawService", target="ordin", MST=mst, type="XML")
        text = clean(xml)
        annex_title, annex_text = (None, None)
        cov, far, cnote, fnote, method = parse_ordinance(text)
        if method == "article-partial":
            annex_title, annex_text = annex_hwp_for(xml)
            if annex_text:
                cov, far, cnote, fnote, method = parse_ordinance(text, annex_text)
        eff_iso = f"{eff[:4]}-{eff[4:6]}-{eff[6:]}"
        base = f"{key}_도시계획조례_{eff}"
        hdr = (f"# 출처: 법제처 국가법령정보센터 자치법규, 조회일 {TODAY}\n# 자치법규: {name} ({org}) 공포번호 {pn}, 시행일 {eff_iso}, 자치법규일련번호 {mst}\n"
               f"# API 응답에서 태그만 제거한 텍스트. 수정 금지.\n\n")
        (snaps / f"{base}.txt").write_text(hdr + text + "\n", encoding="utf-8")
        snap_rel = f"data/law_snapshots/ordinances/{base}.txt"
        annex_rel = None
        if annex_text:
            annex_rel = f"data/law_snapshots/ordinances/{base}_{re.sub(r'[^0-9가-힣A-Za-z]+', '', annex_title)[:12]}.txt"
            (ROOT / annex_rel).write_text(
                f"# 출처: 법제처 자치법규 {name} 의 첨부 별표 '{annex_title}' (hwp). 조회일 {TODAY}\n"
                "# 추출 방법: hwp 바이너리 본문을 텍스트 추출기로 변환(표 서식이 평문으로 풀림). 의심되면 원본 hwp와 대조.\n"
                "# 수정 금지.\n\n" + annex_text + "\n", encoding="utf-8")
        zones = zone_table(cov, far, cnote, fnote)
        missing_cov = [z for z in CANON_ZONES if zones.get(z, {}).get("coverage") is None]
        missing_far = [z for z in CANON_ZONES if zones.get(z, {}).get("far") is None]
        regions[key] = {
            "ordinance": {"name": name, "org": org, "mst": mst, "promulgation_no": pn, "effective": eff_iso,
                          "snapshot": snap_rel, "annex_snapshot": annex_rel, "method": method},
            "zones": zones,
            "missing": {"coverage": missing_cov, "far": missing_far},
        }
        report.append(f"[{method:14}] {key:8} 시행 {eff_iso} 건폐율 {21 - len(missing_cov)}/21 용적률 {21 - len(missing_far)}/21")
    out = {"generated": TODAY, "note": "원문에서 읽은 값만 포함. 없는 항목은 미확인. 수정 금지(tools/build_ordinance_data.py 로 재생성).",
           "regions": regions}
    (ROOT / "data" / "ordinance_zone_limits.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n".join(report))


if __name__ == "__main__":
    main()
