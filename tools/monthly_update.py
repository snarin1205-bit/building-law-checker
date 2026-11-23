"""월간 법령·조례 점검 + 자동 갱신 (네트워크 필요, 로컬 실행 전용).

흐름
 1) law_sync.check_drift() 로 법제처 현행 공포번호·시행일과 저장 사본을 비교
 2) 변경(CHANGED)된 범주만 해당 빌드 도구로 다시 생성 — 대상 범주: urban(도시계획 조례), parking(주차장 조례),
    sunlight(일조)+landscape(조경), greenbelt(개발제한구역)
 3) 전체 단위 테스트 통과 시에만 브랜치·PR·병합(저장소 상시 승인). 실패하면 data/ 변경을 되돌리고 보고만 남긴다
 4) national(건축법령·주차장법령)·daejeon(대전 조례, 코드 내 상수)은 자동 갱신하지 않고 '수동 확인 필요'로 보고
 5) 보고서: data/sync_reports/<YYYY-MM>.md (변경·실패가 있을 때만 커밋), 항상 %LOCALAPPDATA%/law-checker/monthly/ 에도 저장

사용: python tools/monthly_update.py [--dry-run] [--no-merge]
  --dry-run  점검·보고만(재생성·git 없음)    --no-merge  재생성·테스트까지 하고 병합은 하지 않음
종료코드: 0 정상(변경 없음 또는 자동 갱신 완료), 1 수동 확인 필요/실패 있음
"""
import datetime
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 범주 → (빌드 도구, 변경될 수 있는 데이터 경로)
REBUILD = {
    "urban": ("tools/build_ordinance_data.py", ["data/ordinance_zone_limits.json", "data/law_snapshots"]),
    "parking": ("tools/build_parking_data.py", ["data/parking_ordinances.json", "data/law_snapshots"]),
    "sunlight": ("tools/build_sunlight_data.py", ["data/sunlight_ordinances.json", "data/law_snapshots"]),
    "landscape": ("tools/build_landscape_data.py", ["data/landscape_ordinances.json", "data/law_snapshots"]),
    "greenbelt": ("tools/build_greenbelt_data.py", ["data/greenbelt.json", "data/law_snapshots"]),
    "local": ("tools/build_local_ordinances.py", ["data/local_zone_limits.json", "data/local_parking.json", "data/law_snapshots"]),
}
MANUAL = {"national": "건축법·건축법 시행령·주차장법 시행령(사본 재저장·코드 기준값 갱신 필요)",
          "daejeon": "대전 주차장·도시계획·건축 조례(ordinance_daejeon.py 상수와 사본 갱신 필요)"}


def run(cmd, check=False, timeout=3600):
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    if check and r.returncode:
        raise RuntimeError(f"{' '.join(cmd)} 실패: {(r.stdout + r.stderr)[-400:]}")
    return r


def local_names():
    """도·특별자치도 소재 시·군 조례 이름(재생성 도구가 다름)."""
    import json
    names = set()
    for fn in ("local_zone_limits.json", "local_parking.json"):
        f = ROOT / "data" / fn
        if f.exists():
            for r in json.loads(f.read_text(encoding="utf-8"))["regions"].values():
                names.add(r["ordinance"]["name"])
    return names


def groups_of(src):
    return set(src.get("group", "").split("+"))


def classify(results, srcs):
    """results(check_drift) → (auto: 재생성할 범주 집합, manual: 수동 확인 항목 목록, bad: 오류/미확인 목록)"""
    by_name = {}
    local = local_names()
    for s in srcs:
        by_name.setdefault(s["name"], []).append(s)
    auto, manual, bad = set(), [], []
    for r in results:
        if r["status"] == "OK":
            continue
        gs = set()
        for s in by_name.get(r["name"], []):
            gs |= groups_of(s)
        if r["name"] in local:   # 시·군 조례는 광역시용 도구가 아니라 시·군 수집 도구로 다시 만든다
            gs = (gs - {"urban", "parking"}) | {"local"}
        if r["status"] != "CHANGED":
            bad.append(r)
            continue
        if gs & set(MANUAL):
            manual.append((r, sorted(gs & set(MANUAL))))
        for g in gs & set(REBUILD):
            auto.add(g)
        if not (gs & set(MANUAL)) and not (gs & set(REBUILD)):
            manual.append((r, ["unknown"]))
    return auto, manual, bad


def report_md(today, results, auto, manual, bad, actions):
    n_ok = sum(r["status"] == "OK" for r in results)
    L = [f"# 월간 법령·조례 점검 {today}", "", f"- 감시 대상 {len(results)}건 중 변경 없음 {n_ok}건, 변경 {sum(r['status'] == 'CHANGED' for r in results)}건, 미확인/오류 {len(bad)}건", ""]
    if actions:
        L += ["## 자동 갱신 결과", ""] + [f"- {a}" for a in actions] + [""]
    if manual:
        L += ["## 수동 확인 필요(자동 갱신 안 함)", ""]
        for r, gs in manual:
            L.append(f"- **{r['name']}** — 기대 {r.get('expected')} → 현행 {r.get('found')} ({', '.join(MANUAL.get(g, g) for g in gs)})")
        L.append("")
    changed_auto = [r for r in results if r["status"] == "CHANGED" and r["name"] not in [m[0]["name"] for m in manual]]
    if changed_auto:
        L += ["## 개정 감지(자동 재생성 대상 범주)", ""] + [f"- {r['name']}: {r.get('expected')} → {r.get('found')}" for r in changed_auto] + [""]
    if bad:
        L += ["## 조회 실패·미확인", ""] + [f"- {r['name']}: {r['status']} {r.get('detail', '')}" for r in bad[:40]] + [""]
    return "\n".join(L)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    dry, no_merge = "--dry-run" in sys.argv, "--no-merge" in sys.argv
    import law_sync
    today = datetime.date.today().isoformat()
    srcs = law_sync.sources()
    results = law_sync.check_drift()
    auto, manual, bad = classify(results, srcs)
    actions, failed = [], False

    if auto and not dry:
        branch = f"data-sync-{today}"
        base = run(["git", "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
        if run(["git", "status", "--porcelain"]).stdout.strip():
            actions.append("작업 폴더에 커밋되지 않은 변경이 있어 자동 갱신을 건너뜀(수동 확인)")
            failed = True
        else:
            run(["git", "fetch", "-q", "origin"])
            run(["git", "checkout", "-q", "-B", branch, "origin/main"], check=True)
            try:
                for g in sorted(auto):
                    tool, _ = REBUILD[g]
                    env_cache = None
                    if g == "local":
                        import tempfile
                        env_cache = tempfile.mkdtemp(prefix="local_ord_cache_")
                        os.environ["LOCAL_ORD_CACHE"] = env_cache   # 이전 달 캐시를 쓰면 개정이 반영되지 않는다
                    r = run([sys.executable, tool], timeout=10800)
                    actions.append(f"{g}: {tool} {'완료' if r.returncode == 0 else '실패(' + (r.stdout + r.stderr)[-150:].strip().replace(chr(10), ' ') + ')'}")
                    failed |= r.returncode != 0
                t = run([sys.executable, "-m", "unittest", "discover", "-s", "tests"])
                ok = t.returncode == 0
                actions.append("단위 테스트 " + ("통과" if ok else "실패 — " + (t.stdout + t.stderr)[-300:].strip().replace(chr(10), " ")))
                failed |= not ok
                if ok and not failed:
                    if run(["git", "status", "--porcelain"]).stdout.strip():
                        run(["git", "add", "-A"], check=True)
                        run(["git", "commit", "-q", "-m", f"data: {today} 월간 점검 — {', '.join(sorted(auto))} 재생성\n\nCo-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"], check=True)
                        if no_merge:
                            actions.append("--no-merge: 커밋만 하고 병합하지 않음")
                        else:
                            run(["git", "push", "-q", "-u", "origin", branch], check=True)
                            pr = run(["gh", "pr", "create", "--base", "main", "--head", branch, "--title", f"데이터 월간 갱신 {today}",
                                      "--body", "월간 점검에서 개정이 감지된 범주를 원문에서 다시 생성했고 단위 테스트가 통과했습니다.\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)"])
                            if pr.returncode == 0:
                                url = pr.stdout.strip().splitlines()[-1]
                                mg = run(["gh", "pr", "merge", branch, "--merge"])
                                actions.append(f"PR {url} " + ("병합 완료" if mg.returncode == 0 else "병합 실패: " + mg.stderr[-150:]))
                                failed |= mg.returncode != 0
                            else:
                                actions.append("PR 생성 실패: " + pr.stderr[-200:])
                                failed = True
                    else:
                        actions.append("재생성 결과가 기존 데이터와 같음(변경 없음)")
            finally:
                if failed:  # 실패 시 데이터 변경을 남기지 않는다
                    run(["git", "reset", "-q", "--hard"])
                    run(["git", "clean", "-fdq", "data"])
                run(["git", "checkout", "-q", base])
                if not failed:
                    run(["git", "pull", "-q", "origin", "main"])
    elif auto and dry:
        actions.append("--dry-run: 재생성 범주 " + ", ".join(sorted(auto)) + " (실행 안 함)")

    md = report_md(today, results, auto, manual, bad, actions)
    local = pathlib.Path(os.environ.get("LOCALAPPDATA", str(pathlib.Path.home()))) / "law-checker" / "monthly"
    local.mkdir(parents=True, exist_ok=True)
    (local / f"{today[:7]}.md").write_text(md, encoding="utf-8")
    needs_attention = bool(manual or bad or failed)
    if needs_attention and not dry:
        d = ROOT / "data" / "sync_reports"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{today[:7]}.md").write_text(md, encoding="utf-8")   # 커밋은 사용자 확인 후(자동 병합 대상 아님)
    print(md)
    return 1 if needs_attention else 0


if __name__ == "__main__":
    sys.exit(main())
