"""광역시·특별시 건축 조례의 조경(연면적 구간 비율)·공개공지 조문 → 사본 + data/landscape_ordinances.json (네트워크 필요, CI 제외).

사용: python tools/build_landscape_data.py   — 읽지 못하면 값을 넣지 않고 status 로 표시한다. 수정 금지(재생성).
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import build_ordinance_data as bo  # noqa: E402
from ordinance_landscape_parse import find_open_space_article, parse_landscape  # noqa: E402

TODAY = "2026-11-23"
CITIES = [
    ("서울특별시", "서울특별시 건축 조례", "서울특별시"), ("부산광역시", "부산광역시 건축 조례", "부산광역시"),
    ("대구광역시", "대구광역시 건축 조례", "대구광역시"), ("인천광역시", "인천광역시 건축 조례", "인천광역시"),
    ("광주광역시", "광주광역시 건축 조례", "(구)광주광역시"), ("대전광역시", "대전광역시 건축 조례", "대전광역시"),
    ("울산광역시", "울산광역시 건축 조례", "울산광역시"), ("세종특별자치시", "세종특별자치시 건축 조례", "세종특별자치시"),
]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    snaps = ROOT / "data" / "law_snapshots" / "landscape"
    snaps.mkdir(parents=True, exist_ok=True)
    regions, report = {}, []
    for key, name, org in CITIES:
        f = bo.find(name, org)
        if not f:
            report.append(f"[못찾음] {key}")
            continue
        mst, pn, eff = f
        text = bo.clean(bo.get(endpoint="lawService", target="ordin", MST=mst, type="XML"))
        eff_iso = f"{eff[:4]}-{eff[4:6]}-{eff[6:]}"
        hdr = (f"# 출처: 법제처 국가법령정보센터 자치법규, 조회일 {TODAY}\n# 자치법규: {name} ({org}) 공포번호 {pn}, 시행일 {eff_iso}, 자치법규일련번호 {mst}\n"
               "# {what} 조문 발췌. API 응답에서 태그만 제거한 텍스트. 수정 금지.\n\n")
        r = parse_landscape(text)
        land_rel = None
        if r.get("block"):
            base = f"{key}_건축조례_조경_{eff}"
            (snaps / f"{base}.txt").write_text(hdr.format(what="대지의 조경") + r["block"] + "\n", encoding="utf-8")
            land_rel = f"data/law_snapshots/landscape/{base}.txt"
        open_blk = find_open_space_article(text)
        open_rel, open_title = None, None
        if open_blk:
            base = f"{key}_건축조례_공개공지_{eff}"
            (snaps / f"{base}.txt").write_text(hdr.format(what="공개공지 등의 확보") + open_blk + "\n", encoding="utf-8")
            open_rel = f"data/law_snapshots/landscape/{base}.txt"
            open_title = open_blk.splitlines()[0][:60]
        regions[key] = {"ordinance": {"name": name, "org": org, "mst": mst, "promulgation_no": pn, "effective": eff_iso,
                                      "snapshot": land_rel, "article": r.get("title")},
                        "status": r["status"], "tiers": r["tiers"], "special_notes": r.get("special_notes", []),
                        "open_space": {"snapshot": open_rel, "article": open_title}}
        report.append(f"[{r['status']:20}] {key:8} {eff_iso} 조경={r.get('title', '')[:24]} 구간={[ (t['kind'], t['pct']) for t in r['tiers']]} 특례={len(r.get('special_notes', []))} 공개공지={'O' if open_rel else 'X'}")
    (ROOT / "data" / "landscape_ordinances.json").write_text(json.dumps(
        {"generated": TODAY, "note": "건축 조례 조경 구간·공개공지 조문 발췌(수정 금지, tools/build_landscape_data.py 로 재생성).", "regions": regions},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n".join(report))


if __name__ == "__main__":
    main()
