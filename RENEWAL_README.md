# Building Law Checker — OpenCrab Core v2 Renewal

The renewal screen is now `app.py` (formerly `app_v2.py`) so the existing Streamlit deployment (main file `app.py`) serves it
without changing deployment settings. The previous screen is preserved as `legacy_app.py` (still contains the old
north-daylight / road-slope / parking calculations that the renewal does not use).

## Run

```bash
pip install -r requirements.txt
# 환경변수 (키는 코드·Git에 넣지 말 것)
#   VWORLD_API_KEY   VWorld 인증키
#   VWORLD_DOMAIN    키에 등록한 서비스 URL (기본 localhost:8501) — 키가 URL에 묶여 있어 domain 파라미터가 필요
streamlit run app.py
```

Streamlit 배포에서는 Secrets에 `VWORLD_API_KEY`, `VWORLD_DOMAIN`(배포 주소로 등록한 키)을 넣는다.

### 해외 서버(Streamlit Cloud)에서 VWorld 조회가 막힐 때: 서울 중계

Streamlit Cloud 서버에서는 VWorld 호출이 `ConnectionError`/비JSON 응답으로 실패한다(해외 IP 차단 추정, 미확정).
그래서 Vercel 서울 리전(`icn1`) 함수 `api/vworld.js` 가 VWorld 를 대신 호출한다.

- 중계(Vercel 환경변수): `VWORLD_API_KEY`, `VWORLD_DOMAIN`(키에 등록한 중계 도메인), `RELAY_TOKEN`(임의의 긴 문자열)
- 앱(Streamlit Secrets): `VWORLD_RELAY_URL`(`https://<중계 도메인>/api/vworld`), `VWORLD_RELAY_TOKEN`(= `RELAY_TOKEN`)
  — 설정되면 중계가 우선이고 앱에는 VWorld 키가 필요 없다.
- 중계는 토큰 없이는 응답하지 않으며, 허용 호출은 주소 좌표·용도지역·지구단위계획구역 세 가지뿐이다.
- 진단: `GET /api/vworld?action=diag` (토큰 필요) → 중계 실행 리전과 VWorld 응답 상태를 돌려준다.
- 로컬 점검: `node tests/relay_check.js`
- 조회가 안 될 때는 화면에서 '용도지역 직접 선택'으로 대전 조례 상한을 볼 수 있다.

## Architecture

- `app.py`: UI (구 app_v2.py). 외부 자료 조회, 법규 우선순위, 대전 조례 기준, 규모/주차 산술 시나리오를 분리해서 보여준다.
- `law_core_v2.py`: 오프라인 정책 어댑터. REQUIRED / CONDITIONAL / LOW_PRIORITY / UNKNOWN. 법규 → 조건 → 설계 영향 → 대응.
  - 부설주차장: 주차장법 시행령 별표 1 (공포 36623, 시행 2026-08-28), 비고의 끝수 처리(0.5 이상 1대) 적용
  - 용적률 산정 제외 면적: 건축법 시행령 제119조제1항제4호 (공포 36817, 시행 2026-11-12)
- `ordinance_daejeon.py`: 대전광역시·유성구 조례 연결. 건폐율·용적률(대전광역시 도시계획 조례 제45·50조),
  부설주차장(대전광역시 주차장 조례 별표 6). 유성구 조례에는 수치가 없고 광역시 조례를 따른다.
- `ordinance_regions.py` + `data/ordinance_zone_limits.json`: 광역시·특별시 8곳(서울·부산·대구·인천·광주·대전·울산·세종)
  도시계획 조례의 용도지역별 건폐율·용적률 상한. 법제처 원문에서 `tools/build_ordinance_data.py` 로 생성(수정 금지, 재생성),
  `ordinance_parse.py` 가 조문(한글 '1천300퍼센트'·'100분의 N' 표기 포함) 또는 별표 hwp 표를 읽는다. 원문에서 읽지 못한 값은
  비워 두고 '미확인'으로 표시한다(서울·부산은 제1항 목록에 비도시지역 용도지역이 없어 해당 항목 미확인).
  테스트가 JSON 을 원문 사본(`data/law_snapshots/ordinances/`)에서 다시 파싱한 값과 대조한다.
- `vworld_client.py`: VWorld 용도지역(LT_C_UQ111)·지구단위계획구역(LT_C_UQ141) 조회. 오류를 삼키지 않고
  OK / NOT_FOUND / ERROR 로 구분한다. NOT_FOUND 는 법적 '비적용' 확정이 아니다.
- `law_sync.py`: 법령·조례 개정 감지(네트워크 필요, CI 제외). 값을 자동으로 바꾸지 않고 재검토 필요만 알린다.
- `data/law_snapshots/`: 근거 원문 사본(출처·시행일 표기). 테스트가 코드 값과 사본을 대조한다.
- `building_law_checker.py`: legacy. VWorld 주소→좌표 함수(`get_coordinates`)만 app.py 가 재사용한다.

## QA / Safety

```bash
python -m unittest discover -s tests -v
python -m py_compile app.py law_core_v2.py ordinance_daejeon.py law_sync.py vworld_client.py
python law_sync.py     # 법령·조례 개정 여부 확인 (프록시 접근 필요)
```

Live OpenCrab API calls are **not** implemented. The pack ID is a provenance reference, not a credential.
This tool gives no legal OK/NG determination.

### Policy

- 법령 수치는 법제처 원문에서 확인한 것만 넣는다. 원문이 정하지 않은 부분(소수 첫째자리 처리, 0.5~1대 구간)은
  후보를 모두 보여주고 확정하지 않는다.
- 조회 실패·데이터 없음은 UNKNOWN(미확인)이며 '해당 없음'이 아니다.
- 사본 갱신 절차: `law_sync.py` 가 CHANGED 를 보고하면 → 원문 확인 → `data/law_snapshots/` 새 파일 → 코드 값 → 테스트 통과.

### Known limitations

- 조례 연결 범위: 건폐율·용적률은 광역시·특별시 8곳, 부설주차장·일조는 대전만. 그 밖의 지자체·조례는 직접 확인. 다른 지자체 주소는 시행령 기준만 쓰며 조례를 직접 확인해야 한다.
- 정북일조: 건축법 제61조제1항(현행 시행 2026-11-12, 제21880호) 법 하한(10m 이하 1.5m, 10m 초과 17m 이하 5m, 17m 초과 높이의 1/2)과
  대전광역시 건축 조례 제43조 문언(영 제86조제1항 인용, 해당 항은 2026-11-12 삭제됨)을 비교해 안전측 값만 제시한다.
  조례가 법 개정에 맞춰 개정되었는지는 미확인이며, 정북 인접 대지 용도지역 등 영 제86조제2항 예외는 계산에 반영하지 않는다.
- 대전광역시 주차장 조례 별표 6 은 hwp 첨부에서 텍스트를 추출한 것이므로 원본 대조 필요. 데이터센터 항목은 별표 6에 없어 자동 산정하지 않는다.
- 건폐율·용적률은 조례의 '상한'이며 지구단위계획·정비구역·특례는 반영하지 않는다.
- 용도변경·증축, 장애인전용·경형자동차 주차구획, 표 제5호(공동주택·오피스텔) 주차 산정은 미구현.
- Do not commit API keys or .env. 이전 커밋에 노출된 VWorld 키는 폐기 대상이다.
