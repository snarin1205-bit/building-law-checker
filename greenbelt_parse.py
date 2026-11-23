"""개발제한구역법 시행령 별표 2(허가 또는 신고의 세부기준) 제2호(건축물의 건축 또는 공작물의 설치) 파서 (네트워크 없음).

원문에서 읽은 숫자만 반환한다. 문장 구조가 달라 읽지 못하면 status 로 표시하고 값을 넣지 않는다.
"""
import re


def flat(text):
    return re.sub(r"\s+", "", text or "")


def kn(s):
    """'1천500'·'232'·'5천' → int."""
    s = s.replace(",", "")
    m = re.fullmatch(r"(?:(\d+)천)?(\d+)?", s)
    if not m or not (m.group(1) or m.group(2)):
        return None
    return (int(m.group(1)) * 1000 if m.group(1) else 0) + (int(m.group(2)) if m.group(2) else 0)


def section2(text):
    """별표 2 의 '2. 건축물의 건축 또는 공작물의 설치' 단락(다음 '3. 토지의 형질변경' 앞까지)."""
    f = flat(text)
    a = f.find("2.건축물의건축또는공작물의설치")
    b = f.find("3.토지의형질변경", a + 1)
    return f[a:b] if a >= 0 and b > a else None


def parse_standard(text):
    """반환: {"status","general":{coverage_pct,max_floors,far_pct}, "housing":[{...}], "min_site_area_m2"}"""
    sec = section2(text)
    if not sec:
        return {"status": "section-not-found"}
    out = {"status": "ok"}
    m = re.search(r"가\.건폐율100분의(\d+)이하로건축하되높이(\d+)층이하,용적률(\d+)퍼센트이하", sec)
    if not m:
        return {"status": "general-not-parsed"}
    out["general"] = {"coverage_pct": int(m.group(1)), "max_floors": int(m.group(2)), "far_pct": int(m.group(3))}
    # 나목(주택·근린생활시설): 1) 건폐율 60 ... 연면적 232(지정당시거주자 300) / 2) 건폐율 20 ...
    nb = re.search(r"나\.가목에도불구하고주택또는근린생활시설을건축하는경우에는(.*?)다\.가목에도불구하고", sec)
    housing = []
    if nb:
        body = nb.group(1)
        h1 = re.search(r"1\)건폐율100분의(\d+)이하로건축하는경우:높이(\d+)층이하,용적률(\d+)퍼센트이하로서기존면적을포함하여연면적(\d+)제곱미터\(지정당시거주자는(\d+)제곱미터\)이하", body)
        h2 = re.search(r"2\)건폐율100분의(\d+)이하로건축하는경우:높이(\d+)층이하,용적률(\d+)퍼센트이하", body)
        if h1:
            housing.append({"coverage_pct": int(h1.group(1)), "max_floors": int(h1.group(2)), "far_pct": int(h1.group(3)),
                            "max_floor_area_m2": int(h1.group(4)), "max_floor_area_designated_resident_m2": int(h1.group(5))})
        if h2:
            housing.append({"coverage_pct": int(h2.group(1)), "max_floors": int(h2.group(2)), "far_pct": int(h2.group(3))})
        if not (h1 and h2):
            out["status"] = "housing-partial"
    else:
        out["status"] = "housing-partial"
    out["housing"] = housing
    g = flat(text)
    ms = re.search(r"건축물을건축하기위한대지면적이(\d+)제곱미터미만인경우에는건축물의건축을허가하지아니하여야한다", g)
    out["min_site_area_m2"] = int(ms.group(1)) if ms else None
    mi = re.search(r"기반시설로서건축연면적이(1천500|\d+천?\d*)제곱미터이상", sec)
    out["infrastructure_plan_threshold_m2"] = kn(mi.group(1)) if mi else None
    return out


def parse_resident_opinion(text):
    """영 제20조제1항제1호: 주민 의견청취 대상 연면적 기준(㎡)과 게시 기간(일)."""
    f = flat(text)
    a = re.search(r"연면적\(.*?\)이(1천500|\d+천?\d*)제곱미터이상인건축물의건축", f)
    d = re.search(r"게시판에(\d+)일이상게시", f)
    return {"floor_area_m2": kn(a.group(1)) if a else None, "notice_days": int(d.group(1)) if d else None}
