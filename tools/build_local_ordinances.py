"""도·특별자치도 소재 시·군의 도시계획 조례(건폐율·용적률)와 주차장 조례(부설주차장 설치기준) 수집·구조화 (네트워크 필요, CI 제외).

사용: python tools/build_local_ordinances.py            (LOCAL_ORD_CACHE 로 캐시 폴더 지정 가능, 중단 후 재실행하면 이어서)
산출: data/local_zone_limits.json, data/local_parking.json, data/law_snapshots/local/*.txt, data/local_ordinance_report.json
원문에서 읽은 값만 저장한다. 읽지 못했거나 구조가 달라 검증을 통과하지 못한 지자체는 데이터에 넣지 않고 report 에 사유를 남긴다.
"""
import hashlib
import json
import os
import pathlib
import re
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import build_ordinance_data as bo  # noqa: E402
import build_parking_data as bp  # noqa: E402
from ordinance_parking_parse import completeness, find_follow_decree, parse_parking_annex  # noqa: E402
from ordinance_parse import CANON_ZONES, article_block, parse_ordinance, zone_table  # noqa: E402

TODAY = "2026-11-23"
CACHE = pathlib.Path(os.environ.get("LOCAL_ORD_CACHE", str(ROOT / ".cache_local_ord")))
CACHE.mkdir(parents=True, exist_ok=True)
SIDO = r"(경기도|강원특별자치도|강원도|충청북도|충청남도|전북특별자치도|전라북도|전라남도|경상북도|경상남도|제주특별자치도)"
ORG = re.compile(rf"^{SIDO}( \S+(시|군))?$")
PARK_BAD = ("기금", "특별회계", "요금", "무료", "개방", "지원", "공영", "청사", "시장", "환승", "위원회", "운영", "전용", "공유",
            "태양광", "재생", "관리공단", "시설관리", "민간", "주민", "거주자", "임시", "체납", "교통사업", "규칙", "수탁", "노상", "견인",
            "이륜", "자전거", "화물", "버스", "택시", "캠핑", "공원", "마을", "문화재", "관광지", "장애인")


def cached(fn_name, **p):
    """프록시/네트워크 응답을 디스크에 캐시(재실행 시 이어서)."""
    key = hashlib.sha1((fn_name + json.dumps(p, sort_keys=True, ensure_ascii=False)).encode("utf-8")).hexdigest()
    f = CACHE / f"{key}.txt"
    if f.exists():
        return f.read_text(encoding="utf-8")
    time.sleep(0.3)
    txt = bo.get(**p)
    f.write_text(txt, encoding="utf-8")
    return txt


def cached_hwp(url):
    key = hashlib.sha1(("hwp" + url).encode("utf-8")).hexdigest()
    f = CACHE / f"{key}.hwp.txt"
    if f.exists():
        return f.read_text(encoding="utf-8")
    time.sleep(0.3)
    last = None
    for attempt in range(3):
        try:
            txt = bp.download_hwp_text(url)
            f.write_text(txt, encoding="utf-8")
            return txt
        except Exception as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise last


def enumerate_ordinances(query):
    rows = []
    for pg in range(1, 40):
        s = cached("search", endpoint="ordinSearchList", query=query, numOfRows="100", pageNo=str(pg))
        got = list(re.finditer(r"<law id.*?</law>", s, re.S))
        if not got:
            break
        for m in got:
            b = m.group(0)
            rows.append({"name": bo.field(b, "자치법규명"), "org": bo.field(b, "지자체기관명"),
                         "mst": bo.field(b, "자치법규일련번호"), "pn": bo.field(b, "공포번호"), "eff": bo.field(b, "시행일자")})
    return rows


def slug(org):
    return re.sub(r"\s+", "_", org)


def eff_iso(e):
    return f"{e[:4]}-{e[4:6]}-{e[6:]}"


def ordinance_xml(mst):
    return cached("law", endpoint="lawService", target="ordin", MST=mst, type="XML")


def annex_hwp_cached(xml, hint):
    for m in re.finditer(r"<별표단위[^>]*>.*?</별표단위>", xml, re.S):
        blk = m.group(0)
        title = bo.field(blk, "별표제목")
        if hint in title and "hwp" in bo.field(blk, "별표첨부파일구분").lower():
            return title, cached_hwp(bo.field(blk, "별표첨부파일명"))
    return None, None


def build_urban(report):
    rows = [r for r in enumerate_ordinances("도시계획 조례")
            if ORG.match(r["org"]) and " " in r["org"] and re.search(r"도시계획\s?조례$", r["name"]) and "시행규칙" not in r["name"]
            and "위원회" not in r["name"]]
    best = {}
    for r in rows:  # 기관당 1건(시행일 최신)
        if r["org"] not in best or r["eff"] > best[r["org"]]["eff"]:
            best[r["org"]] = r
    out = {}
    snaps = ROOT / "data" / "law_snapshots" / "local"
    snaps.mkdir(parents=True, exist_ok=True)
    for i, (org, r) in enumerate(sorted(best.items())):
        try:
            xml = ordinance_xml(r["mst"])
            text = bo.clean(xml)
            cov, far, cn, fn, method = parse_ordinance(text)
            annex_title, annex_text = None, None
            if method == "article-partial" or len(cov) < 8 or len(far) < 8:
                annex_title, annex_text = annex_hwp_cached(xml, "건폐율")
                if annex_text:
                    c2, f2, n1, n2, m2 = parse_ordinance(text, annex_text)
                    if m2 == "annex-hwp" or (len(c2) >= len(cov) and len(f2) >= len(far)):
                        cov, far, cn, fn, method = c2, f2, n1, n2, m2
            if len(cov) < 8 or len(far) < 8:
                report["urban_failed"].append({"org": org, "name": r["name"], "cov": len(cov), "far": len(far), "method": method})
                continue
            base = f"{slug(org)}_도시계획조례_{r['eff']}"
            hdr = (f"# 출처: 법제처 국가법령정보센터 자치법규, 조회일 {TODAY}\n# 자치법규: {r['name']} ({org}) 공포번호 {r['pn']}, 시행일 {eff_iso(r['eff'])}, 자치법규일련번호 {r['mst']}\n"
                   "# 용도지역별 건폐율·용적률 조문(또는 별표) 발췌. API 응답에서 태그만 제거한 텍스트. 수정 금지.\n\n")
            if method == "annex-hwp":
                body = f"# 별표 '{annex_title}' (hwp 추출 텍스트)\n" + annex_text
                (snaps / f"{base}.txt").write_text(hdr + body + "\n", encoding="utf-8")
                annex_rel = None
                snap_rel = f"data/law_snapshots/local/{base}.txt"
            else:
                blocks = [article_block(text, "건폐율") or "", article_block(text, "용적률") or ""]
                (snaps / f"{base}.txt").write_text(hdr + "\n".join(b for b in blocks if b) + "\n", encoding="utf-8")
                snap_rel, annex_rel = f"data/law_snapshots/local/{base}.txt", None
            zones = zone_table(cov, far, cn, fn)
            out[org] = {"ordinance": {"name": r["name"], "org": org, "mst": r["mst"], "promulgation_no": r["pn"],
                                      "effective": eff_iso(r["eff"]), "snapshot": snap_rel, "annex_snapshot": annex_rel, "method": method},
                        "zones": zones,
                        "missing": {"coverage": [z for z in CANON_ZONES if zones.get(z, {}).get("coverage") is None],
                                    "far": [z for z in CANON_ZONES if zones.get(z, {}).get("far") is None]}}
        except Exception as e:
            report["urban_failed"].append({"org": org, "name": r["name"], "error": f"{type(e).__name__}: {str(e)[:80]}"})
        if (i + 1) % 10 == 0:
            print(f"  도시계획 {i + 1}/{len(best)} 성공 {len(out)}", flush=True)
    report["urban_candidates"] = len(best)
    return out


def pick_parking(rows):
    """기관별로 부설주차장 설치기준이 있을 법한 주차장 조례 1건 선택."""
    by_org = {}
    for r in rows:
        if not ORG.match(r["org"]) or " " not in r["org"]:
            continue
        n = r["name"]
        if "주차장" not in n or not n.endswith("조례") or "시행규칙" in n or any(x in n for x in PARK_BAD):
            continue
        by_org.setdefault(r["org"], []).append(r)
    chosen = {}
    for org, lst in by_org.items():
        lst.sort(key=lambda r: (0 if "설치 및 관리" in r["name"] or "설치및관리" in r["name"] else 1, len(r["name"]), r["name"]))
        chosen[org] = lst  # 후보 목록(우선순위순)
    return chosen


def annex_for_parking(xml):
    units = bp.annex_units(xml)
    related = [bo.field(u, "별표제목") for u in units
               if "주차" in bo.field(u, "별표제목") and any(h in bo.field(u, "별표제목") for h in bp.RELATED_HINT)]
    for u in units:
        t = bo.field(u, "별표제목")
        if "설치" in t and ("부설" in t or "시설물" in t) and not any(x in t for x in bp.EXCLUDE_TITLE):
            if "hwp" in bo.field(u, "별표첨부파일구분").lower():
                txt = cached_hwp(bo.field(u, "별표첨부파일명"))
                return t, "hwp", bp.slice_annex(txt) or txt, related
            plain = re.sub(r"<!\[CDATA\[|\]\]>|<[^>]+>", "", bo.field(u, "별표내용"))
            if len(plain.strip()) > 300:
                import html
                return t, "xml본문", html.unescape(plain), related
    for u in units:
        if "hwp" in bo.field(u, "별표첨부파일구분").lower() and not bo.field(u, "별표제목").startswith("별지"):
            txt = cached_hwp(bo.field(u, "별표첨부파일명"))
            cut = bp.slice_annex(txt)
            if cut and "시설면적" in cut:
                return bo.field(u, "별표제목") + "(합본 hwp에서 설치기준 구간 추출)", "hwp", cut, related
    return None, None, None, related


def build_parking(report):
    rows = enumerate_ordinances("주차장 조례")
    chosen = pick_parking(rows)
    out = {}
    snaps = ROOT / "data" / "law_snapshots" / "local"
    snaps.mkdir(parents=True, exist_ok=True)
    for i, (org, cands) in enumerate(sorted(chosen.items())):
        done = False
        for r in cands[:3]:
            try:
                xml = ordinance_xml(r["mst"])
                title, method, annex, related = annex_for_parking(xml)
                if not annex:
                    fd = find_follow_decree(bo.clean(xml))
                    if fd:
                        base = f"{slug(org)}_주차장조례_{r['eff']}"
                        hdr = (f"# 출처: 법제처 국가법령정보센터 자치법규, 조회일 {TODAY}\n# 자치법규: {r['name']} ({org}) 공포번호 {r['pn']}, 시행일 {eff_iso(r['eff'])}, 자치법규일련번호 {r['mst']}\n"
                               "# 부설주차장 설치기준이 주차장법 시행령 별표 1을 따른다고 정한 조문 발췌. 수정 금지.\n\n")
                        (snaps / f"{base}_설치기준조문.txt").write_text(hdr + fd["excerpt"] + "\n", encoding="utf-8")
                        out[org] = {"ordinance": {"name": r["name"], "org": org, "mst": r["mst"], "promulgation_no": r["pn"],
                                                  "effective": eff_iso(r["eff"]), "snapshot": f"data/law_snapshots/local/{base}_설치기준조문.txt",
                                                  "annex_snapshot": None, "annex_title": None, "annex_method": "article"},
                                    "follows_decree": True, "article": fd["title"], "proviso": fd["proviso"],
                                    "related_annexes": related, "columns": [], "categories": [], "notes": [],
                                    "small_house_rule": False, "rounding_half_rule": False,
                                    "incomplete": False, "manual_heavy": False}
                        done = True
                        break
                    continue
                parsed = parse_parking_annex(annex)
                n_ok = sum(1 for c in parsed["categories"] if c["kind"] in ("area", "per_unit", "detached"))
                if n_ok < 3:
                    report["parking_failed"].append({"org": org, "name": r["name"], "ok_categories": n_ok, "total": len(parsed["categories"])})
                    done = True
                    break
                base = f"{slug(org)}_주차장조례_{r['eff']}"
                hdr = (f"# 출처: 법제처 국가법령정보센터 자치법규, 조회일 {TODAY}\n# 자치법규: {r['name']} ({org}) 공포번호 {r['pn']}, 시행일 {eff_iso(r['eff'])}, 자치법규일련번호 {r['mst']}\n"
                       f"# 부설주차장 설치기준 별표 '{title}' ({method}) 발췌.\n"
                       + ("# 추출 방법: hwp 바이너리 본문을 텍스트 추출기로 변환(표 서식이 평문으로 풀림). 의심되면 원본 hwp와 대조.\n" if method == "hwp" else "")
                       + "# 수정 금지.\n\n")
                (snaps / f"{base}_설치기준별표.txt").write_text(hdr + annex + "\n", encoding="utf-8")
                out[org] = {"ordinance": {"name": r["name"], "org": org, "mst": r["mst"], "promulgation_no": r["pn"],
                                          "effective": eff_iso(r["eff"]), "snapshot": None,
                                          "annex_snapshot": f"data/law_snapshots/local/{base}_설치기준별표.txt",
                                          "annex_title": title, "annex_method": method},
                            "related_annexes": related, **parsed, **completeness(parsed["categories"])}
                done = True
                break
            except Exception as e:
                report["parking_failed"].append({"org": org, "name": r["name"], "error": f"{type(e).__name__}: {str(e)[:80]}"})
        if not done:
            report["parking_failed"].append({"org": org, "reason": "설치기준 별표를 찾지 못함", "tried": [c["name"] for c in cands[:3]]})
        if (i + 1) % 10 == 0:
            print(f"  주차장 {i + 1}/{len(chosen)} 성공 {len(out)}", flush=True)
    report["parking_candidates"] = len(chosen)
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    report = {"generated": TODAY, "urban_failed": [], "parking_failed": []}
    print("도시계획 조례 수집 시작", flush=True)
    urban = build_urban(report)
    (ROOT / "data" / "local_zone_limits.json").write_text(json.dumps(
        {"generated": TODAY, "note": "도·특별자치도 소재 시·군 도시계획 조례. 원문에서 읽은 값만(수정 금지, tools/build_local_ordinances.py 로 재생성).", "regions": urban},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"도시계획 조례 완료: {len(urban)}곳 / 후보 {report['urban_candidates']}", flush=True)
    print("주차장 조례 수집 시작", flush=True)
    parking = build_parking(report)
    (ROOT / "data" / "local_parking.json").write_text(json.dumps(
        {"generated": TODAY, "note": "도·특별자치도 소재 시·군 주차장 조례. 원문에서 읽은 값만(수정 금지, tools/build_local_ordinances.py 로 재생성).", "regions": parking},
        ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "data" / "local_ordinance_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"주차장 조례 완료: {len(parking)}곳 / 후보 {report['parking_candidates']}", flush=True)
    print(f"실패(도시계획 {len(report['urban_failed'])}, 주차장 {len(report['parking_failed'])}) — data/local_ordinance_report.json", flush=True)


if __name__ == "__main__":
    main()
