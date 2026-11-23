# Building Law Checker — OpenCrab Core v2 Renewal

Original `app.py` and `building_law_checker.py` are deliberately preserved (legacy; still contains the old
north-daylight / road-slope / parking calculations that the renewal does not use). The new entry point is `app_v2.py`.

## Run

```bash
pip install -r requirements.txt
# 환경변수 (키는 코드·Git에 넣지 말 것)
#   VWORLD_API_KEY   VWorld 인증키
#   VWORLD_DOMAIN    키에 등록한 서비스 URL (기본 localhost:8501) — 키가 URL에 묶여 있어 domain 파라미터가 필요
streamlit run app_v2.py
```

Streamlit 배포에서는 Secrets에 `VWORLD_API_KEY`, `VWORLD_DOMAIN`(배포 주소로 등록한 키)을 넣는다.

## Architecture

- `app_v2.py`: UI. 외부 자료 조회, 법규 우선순위, 대전 조례 기준, 규모/주차 산술 시나리오를 분리해서 보여준다.
- `law_core_v2.py`: 오프라인 정책 어댑터. REQUIRED / CONDITIONAL / LOW_PRIORITY / UNKNOWN. 법규 → 조건 → 설계 영향 → 대응.
  - 부설주차장: 주차장법 시행령 별표 1 (공포 36623, 시행 2026-08-28), 비고의 끝수 처리(0.5 이상 1대) 적용
  - 용적률 산정 제외 면적: 건축법 시행령 제119조제1항제4호 (공포 36817, 시행 2026-11-12)
- `ordinance_daejeon.py`: 대전광역시·유성구 조례 연결. 건폐율·용적률(대전광역시 도시계획 조례 제45·50조),
  부설주차장(대전광역시 주차장 조례 별표 6). 유성구 조례에는 수치가 없고 광역시 조례를 따른다.
- `vworld_client.py`: VWorld 용도지역(LT_C_UQ111)·지구단위계획구역(LT_C_UQ141) 조회. 오류를 삼키지 않고
  OK / NOT_FOUND / ERROR 로 구분한다. NOT_FOUND 는 법적 '비적용' 확정이 아니다.
- `law_sync.py`: 법령·조례 개정 감지(네트워크 필요, CI 제외). 값을 자동으로 바꾸지 않고 재검토 필요만 알린다.
- `data/law_snapshots/`: 근거 원문 사본(출처·시행일 표기). 테스트가 코드 값과 사본을 대조한다.
- `building_law_checker.py`: legacy. VWorld 주소→좌표 함수(`get_coordinates`)만 app_v2 가 재사용한다.

## QA / Safety

```bash
python -m unittest discover -s tests -v
python -m py_compile app_v2.py law_core_v2.py ordinance_daejeon.py law_sync.py vworld_client.py
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

- 조례는 대전광역시·유성구만 연결. 다른 지자체 주소는 시행령 기준만 쓰며 조례를 직접 확인해야 한다.
- 정북일조 이격거리는 확정하지 않는다: 건축법 제61조 개정(조문시행일 2027-02-12)과 시행령 제86조제1항 삭제,
  대전광역시 건축 조례 제43조의 인용이 과도기에 있어 오늘 시행 중인 수치를 단정할 수 없다. 현행본 확보 후 반영.
- 대전광역시 주차장 조례 별표 6 은 hwp 첨부에서 텍스트를 추출한 것이므로 원본 대조 필요. 데이터센터 항목은 별표 6에 없어 자동 산정하지 않는다.
- 건폐율·용적률은 조례의 '상한'이며 지구단위계획·정비구역·특례는 반영하지 않는다.
- 용도변경·증축, 장애인전용·경형자동차 주차구획, 표 제5호(공동주택·오피스텔) 주차 산정은 미구현.
- Do not commit API keys or .env. 이전 커밋에 노출된 VWorld 키는 폐기 대상이다.
