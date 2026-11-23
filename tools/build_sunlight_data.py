"""광역시·특별시 건축 조례의 정북일조 조문 → 사본 + data/sunlight_ordinances.json (네트워크 필요, CI 제외).

사용: python tools/build_sunlight_data.py
조문을 읽지 못하면 값을 넣지 않고 status 로 표시한다. 수정 금지(재생성).
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import build_ordinance_data as bo  # noqa: E402
from ordinance_sunlight_parse import parse  # noqa: E402

TODAY = "2026-11-23"
CITIES = [
    ("서울특별시", "서울특별시 건축 조례", "서울특별시"), ("부산광역시", "부산광역시 건축 조례", "부산광역시"),
    ("대구광역시", "대구광역시 건축 조례", "대구광역시"), ("인천광역시", "인천광역시 건축 조례", "인천광역시"),
    ("광주광역시", "광주광역시 건축 조례", "(구)광주광역시"), ("대전광역시", "대전광역시 건축 조례", "대전광역시"),
    ("울산광역시", "울산광역시 건축 조례", "울산광역시"), ("세종특별자치시", "세종특별자치시 건축 조례", "세종특별자치시"),
]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    snaps = ROOT / "data" / "law_snapshots" / "sunlight"
    snaps.mkdir(parents=True, exist_ok=True)
    regions, report = {}, []
    for key, name, org in CITIES:
        f = bo.find(name, org)
        if not f:
            report.append(f"[못찾음] {key}")
            continue
        mst, pn, eff = f
        text = bo.clean(bo.get(endpoint="lawService", target="ordin", MST=mst, type="XML"))
        r = parse(text)
        eff_iso = f"{eff[:4]}-{eff[4:6]}-{eff[6:]}"
        snap_rel = None
        if r.get("block"):
            base = f"{key}_건축조례_일조_{eff}"
            hdr = (f"# 출처: 법제처 국가법령정보센터 자치법규, 조회일 {TODAY}\n# 자치법규: {name} ({org}) 공포번호 {pn}, 시행일 {eff_iso}, 자치법규일련번호 {mst}\n"
                   "# 일조 등의 확보를 위한 건축물의 높이 제한 조문 발췌. API 응답에서 태그만 제거한 텍스트. 수정 금지.\n\n")
            (snaps / f"{base}.txt").write_text(hdr + r["block"] + "\n", encoding="utf-8")
            snap_rel = f"data/law_snapshots/sunlight/{base}.txt"
        regions[key] = {"ordinance": {"name": name, "org": org, "mst": mst, "promulgation_no": pn, "effective": eff_iso, "snapshot": snap_rel,
                                      "article": r.get("title")},
                        "status": r["status"], "tiers": r["tiers"], "cites": r.get("cites"), "proviso": r.get("proviso", "")}
        report.append(f"[{r['status']:22}] {key:8} 시행 {eff_iso} {r.get('title', '')[:30]} 인용={r.get('cites')} 구간={len(r['tiers'])}")
    (ROOT / "data" / "sunlight_ordinances.json").write_text(json.dumps(
        {"generated": TODAY, "note": "건축 조례 일조 조문에서 읽은 값만(수정 금지, tools/build_sunlight_data.py 로 재생성).", "regions": regions},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n".join(report))


if __name__ == "__main__":
    main()
