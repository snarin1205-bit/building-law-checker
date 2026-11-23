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
- `review_sheet.py`: **법규검토서**(화면 맨 위). 주소·용도·면적으로 항목별 '근거 조문 / 기준 수치 / 이 대지 적용값 / 설계 영향 / 상태'를 만든다.
  항목: 대지 개요, 건폐율·용적률(최대 건축면적·연면적), 정북일조, 부설주차장·장애인 전용주차, 조경(`data/landscape_ordinances.json`), 공개공지(법정 대상 판정 +
  조례 조문 원문 발췌), 직통계단 보행거리·2개소 설치 대상, 방화구획. 미연결 항목(가로구역별 높이, 대지 안의 공지, 장애인 편의시설, 에너지, 심의)은 표에서 숨기지 않고 '미연결'로 표시한다.
  주요 수치는 `key/value`로 JSON 에 함께 내보내 최대건축가능영역 계산(siteplan)이 이어받을 수 있다. 상태: 확정 / 조건부 / 미확인 / 미연결.
  안전장치: 용도가 표에 열거돼 있는데 계산 가능한 분류가 없으면 '그 밖의 건축물'로 대체하지 않고 미확인으로 둔다.
- `ordinance_regions.py` + `data/ordinance_zone_limits.json`: 광역시·특별시 8곳(서울·부산·대구·인천·광주·대전·울산·세종)
  도시계획 조례의 용도지역별 건폐율·용적률 상한. 법제처 원문에서 `tools/build_ordinance_data.py` 로 생성(수정 금지, 재생성),
  `ordinance_parse.py` 가 조문(한글 '1천300퍼센트'·'100분의 N' 표기 포함) 또는 별표 hwp 표를 읽는다. 원문에서 읽지 못한 값은
  비워 두고 '미확인'으로 표시한다(서울·부산은 제1항 목록에 비도시지역 용도지역이 없어 해당 항목 미확인).
  테스트가 JSON 을 원문 사본(`data/law_snapshots/ordinances/`)에서 다시 파싱한 값과 대조한다.
- `parking_regions.py` + `data/parking_ordinances.json`: 광역시·특별시 8곳 주차장 조례의 부설주차장 설치기준(별표). 법제처 원문 별표(대부분 hwp 첨부)를
  `tools/build_parking_data.py` 로 사본 저장 후 `ordinance_parking_parse.py` 가 구조화한다. 단순·명확한 분류(면적·단위·단독주택 구간식)만 계산하고,
  공동주택·오피스텔 등 별도 규정을 인용하거나 규칙 수가 원문과 맞지 않는 분류는 manual(원문 표 그대로 표시, 계산 안 함). 인천처럼 열 구분(도시지역/관리지역)이
  있으면 열을 선택해야 한다. 테스트가 JSON 을 별표 사본에서 다시 파싱한 값과 대조하고 대전은 검증된 표와 교차 대조한다.
- `sunlight_regions.py` + `data/sunlight_ordinances.json`: 광역시·특별시 8곳 건축 조례의 '일조 등의 확보를 위한 건축물의 높이 제한' 조문에서 읽은 정북 이격 구간.
  법 제61조제1항 현행 하한과 조례 문언 값을 비교해 안전측을 제시한다. 조례가 영 제86조제1항(2026-11-12 삭제)을 인용하는 채로 남아 있으면 stale_basis 로 표시
  (서울·대구는 이미 법 제61조 3단계로 개정, 나머지 6곳은 2단계 기준 유지).
- `data/local_zone_limits.json`, `data/local_parking.json`: 도 소재 시·군의 도시계획·주차장 조례(`tools/build_local_ordinances.py` 로 수집). 같은 파서·검증 규칙을 쓰며
  읽지 못했거나 검증에 실패한 지자체는 포함하지 않고 `data/local_ordinance_report.json` 에 사유를 남긴다. 주소는 '경기도 성남시 …'처럼 도+시·군으로 인식한다.
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

- 법규검토서의 조경·공개공지 조례 값은 광역시·특별시 8곳만 연결(시·군은 '미연결'). 공개공지 비율은 도시마다 구조가 달라 계산하지 않고 조문 원문을 보여준다.
- 법규검토서 연면적을 입력하지 않으면 용적률 상한 기준 최대 연면적을 가정한다(상태 '조건부'). 시설면적(주차 산정)은 공용 포함 바닥면적에서 주차용 면적을 뺀 값으로 직접 맞춰야 한다.
- 조례 연결 범위: 광역시·특별시 8곳(건폐율·용적률·부설주차장·일조 이격)과 도 소재 시·군 중 수집·검증에 성공한 곳(건폐율·용적률·부설주차장). 시·군의 일조(건축 조례)는 미연결(법 하한만 표시).
  연결되지 않은 지자체는 '미연결' 안내만 하고 값을 추정하지 않는다. 구 단위·읍면 단위의 별도 조례, 도(道) 조례는 반영하지 않는다.
- 주차 조례의 설치제한지역·특수지역 별표(서울 별표 3 등), 조건부 분류(광주 아시아문화중심도시 등)는 계산에 반영하지 않고 안내만 한다. 다른 지자체 주소는 시행령 기준만 쓰며 조례를 직접 확인해야 한다.
- 정북일조: 건축법 제61조제1항(현행 시행 2026-11-12, 제21880호) 법 하한(10m 이하 1.5m, 10m 초과 17m 이하 5m, 17m 초과 높이의 1/2)과
  대전광역시 건축 조례 제43조 문언(영 제86조제1항 인용, 해당 항은 2026-11-12 삭제됨)을 비교해 안전측 값만 제시한다.
  조례가 법 개정에 맞춰 개정되었는지는 미확인이며, 정북 인접 대지 용도지역 등 영 제86조제2항 예외는 계산에 반영하지 않는다.
- 대전광역시 주차장 조례 별표 6 은 hwp 첨부에서 텍스트를 추출한 것이므로 원본 대조 필요. 데이터센터 항목은 별표 6에 없어 자동 산정하지 않는다.
- 건폐율·용적률은 조례의 '상한'이며 지구단위계획·정비구역·특례는 반영하지 않는다.
- 용도변경·증축, 장애인전용·경형자동차 주차구획, 표 제5호(공동주택·오피스텔) 주차 산정은 미구현.
- Do not commit API keys or .env. 이전 커밋에 노출된 VWorld 키는 폐기 대상이다.
