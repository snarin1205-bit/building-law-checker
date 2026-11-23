"""정북일조 이격거리: 법 하한(건축법 제61조제1항 현행)과 지역 건축 조례 문언 값 비교 (data/sunlight_ordinances.json 기반).

조례가 법 개정(2026-11-12 시행: 영 제86조제1항 삭제, 법 제61조제1항이 10m/17m 3단계)에 맞춰 개정되었는지는 조례마다 다르다.
조례가 '영 제86조제1항'을 인용하는 채로 남아 있으면 stale_basis=True 로 표시한다. 안전측(더 큰 값)을 제시하되 확정하지 않는다.
"""
import json
import pathlib

from law_core_v2 import NORTH_LIGHT_LAW_META, north_light_law_minimum
from ordinance_sunlight_parse import value_at

DATA_FILE = pathlib.Path(__file__).resolve().parent / "data" / "sunlight_ordinances.json"
_cache = None


def load():
    global _cache
    if _cache is None:
        _cache = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return _cache


def region_data(region):
    r = load()["regions"].get(region)
    return r if r and r["status"] == "ok" else None


def setback(region, part_height_m):
    law = north_light_law_minimum(part_height_m)
    if law["status"] != "PREVIEW":
        return law
    r = region_data(region)
    if not r:
        return {"status": "NO_DATA", "height_m": law["height_m"], "law_min_m": law["law_min_m"],
                "reason": f"{region} 건축 조례의 일조 조문을 읽지 못함(또는 미연결) — 조례로 직접 확인"}
    h = law["height_m"]
    ordv = round(value_at(r["tiers"], h), 3)
    lawv = law["law_min_m"]
    stale = r["cites"] == "영 제86조제1항"
    return {"status": "PREVIEW", "height_m": h, "law_min_m": lawv, "ordinance_text_m": ordv,
            "conservative_m": max(lawv, ordv), "conflict": abs(lawv - ordv) > 1e-9, "stale_basis": stale,
            "law": NORTH_LIGHT_LAW_META, "ordinance": r["ordinance"], "proviso": r.get("proviso", ""),
            "reason": "법 하한(건축법 제61조제1항)과 조례 문언 값을 비교한 안전측 값. 정북 인접 대지 용도지역 등 영 제86조제2항 예외는 반영하지 않음"}


def note(region):
    r = region_data(region)
    base = ("건축법 제61조제1항(현행, 시행 2026-11-12)은 전용·일반주거지역 안 건축물에 대해 정북방향 인접 대지경계선으로부터 "
            "높이 10m 이하 부분 1.5m 이상, 10m 초과 17m 이하 부분 5m 이상, 17m 초과 부분 높이의 1/2 이상의 범위에서 "
            "지방자치단체 조례로 정하는 거리 이상을 띄우도록 한다.")
    if not r:
        return base + f" {region or '이 지역'} 건축 조례의 일조 조문은 연결되어 있지 않아 조례 값 비교를 제공하지 않는다(법 하한만 표시)."
    o = r["ordinance"]
    s = f" {o['name']}(시행 {o['effective']}) {o['article']}"
    if r["cites"] == "영 제86조제1항":
        s += ("은 '영 제86조제1항에 따라' 이격거리를 정하고 있는데, 영 제86조제1항은 2026-11-12 삭제되었다. 조례가 법 개정에 맞춰 "
              "개정되지 않았을 수 있어, 조례 문언 값과 법 하한이 다른 구간이 있으면 큰 값을 안전측으로 보이되 조례 현행본·허가권자로 확인할 것.")
    elif r["cites"] == "법 제61조제1항":
        s += "은 법 제61조제1항에 따라 이격거리를 정하며 법 하한과 같은 구간 기준이다."
    else:
        s += "의 인용 근거를 확인하지 못했다."
    if r.get("proviso"):
        s += f" 조례 단서: {r['proviso'][:160]}"
    return base + s
