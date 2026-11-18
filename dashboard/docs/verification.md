# UI Lite 검증 기록

실행일 2026-11-18 (Asia/Seoul). Linux/WSL Ubuntu, Python 3.10.12. 기준 `5de4508` / `feature/dashboard-llm`, 작업 브랜치 `feature/dashboard-ui-lite`입니다. 실제 보드는 연결하지 않았고 사용자 DB 대신 임시 디렉터리의 DB를 사용했습니다.

## 자동 테스트

```text
.venv/bin/python -m pytest -c dashboard/pytest.ini dashboard/tests -q
70 passed

make test
PASS C vectors + 1,000,000-byte parser fuzz + 100,000 state events (ASan/UBSan)
Ran 23 tests
OK

.venv/bin/python -m pip check
No broken requirements found.
```

정확한 pytest 시간과 testcase는 [stdout](pytest-results.txt), [JUnit XML](pytest-results.xml)에 있습니다. 기존 Smoke Test/C sanitizer 출력은 [legacy-test-results.txt](legacy-test-results.txt)입니다. LLM 전용 테스트는 삭제하고 규칙 탐지 테스트를 새 모듈로 이동했습니다. 단순히 기존 73개에 새 테스트를 더한 숫자가 아닙니다.

| 요구사항 | 검증 근거 |
|---|---|
| 1~2 PyArrow 혼합 node | 정수/문자/누락/중첩 필드에 명시적 dtype 적용 후 `pyarrow.Table.from_pandas()` 직접 성공; UI에서도 양 타입 함께 렌더 |
| 3~4 두 화면 | AppTest와 Chromium에서 Security / DMA Lab 정상 생성, 기본 탭 0개, 보안 그래프 0개·Lab 그래프 4개 |
| 5~6 Runtime·COM 유지 | 같은 Runtime/State/SerialManager/port worker 객체 및 포트 factory 생성 횟수 1회 확인 |
| 7 불필요 그래프 방지 | 선택하지 않은 모드와 닫힌 센서 패널의 Plotly 0회; 같은 revision 캐시 재사용·상한 |
| 8 Demo | 전체 합성 파일 처리, 6조건 및 보안 ALARM/LINK_LOST/FAULT, 실제 브라우저 재생 |
| 9 Replay | JSONL 원본 필드/PC 시각 보존, replay-synthetic provenance와 비동기 큐 처리 |
| 10 시리얼 경로 | 기존 실제 PySerial↔Linux PTY 왕복, fake 다중 포트·부분 줄·끊김/재연결·다른 포트 지속, OS 중복 락 |
| 11 DMA 계산 보존 | metrics.py 바이트 불변, 기존 처리량·가중 평균·전환 제외·LOAD 분리 테스트 유지 |
| 12 6조건 표 | 6행 항상 표시, 0%와 No data 구별, source/port/session 범위 분리 |
| 13 TRACE | gap/null·PC 수신 누락·END 개수·ABORT 기존 테스트, 브라우저 상세 패널 |
| 14 TRIAL | valid=1만 분모, invalid 분리, 모드/LOAD/폭별 표 렌더 |
| 15 SQLite 보존 | 기존 diagnosis artifact와 live/demo 원본을 넣은 DB 재열기 후 내용 보존·출처 필터 |
| 16 원본 다운로드 | 일반 갱신의 DB raw 조회 없음, 준비 버튼 이후 실제 Chromium download, CLI 전량 export·덮어쓰기 거부 |
| 17 LLM 제거 | 세 모듈의 파일/수입 부재, 새 Runtime에 diagnosis/auto_diagnose 없음·추론 스레드 없음 |
| 18 수동 제어 | 무승인/중복/만료/오래된 상태 거부, ACK/REJECT/TIMEOUT, CAL 양 ACK/양 센서, ACK 후 재부팅 결과 unknown |
| 19 Demo/Replay 차단 | UI disabled 및 Controller의 source_mode 검사. 가짜 Hub 연결을 넣어도 STATUS/MODE 거부 |
| 20 자동 신고 없음 | emergency 모듈에 외부 통신 경로 없음, 명시 확인 없는 수동 기록 거부, Demo practice_record·접수 미확인, 브라우저 전화 링크 클릭/신고 없음 |

## 실제 Chromium 검증

선택적 개발용 Playwright/Chromium으로 loopback 테스트 서버를 열었습니다. 앱 실행 의존성에는 Playwright를 추가하지 않았습니다. 시스템 공유 라이브러리와 한글 폰트가 없는 환경이어서 필요한 파일을 `/tmp`에 준비했고 시스템 패키지나 Ollama는 변경하지 않았습니다.

검증 스크립트: [browser_check.py](../scripts/browser_check.py). 결과: [browser-results.json](ui-verification/browser-results.json).

- 미연결 상태 Unknown, 두 화면 전환, 4개 비교 그래프와 6조건 표, 센서 상세 LDR/TRACE/TRIAL 표시를 확인했습니다.
- 실제 expander 열기, 준비 버튼으로만 raw DB 읽기, `raw_live.jsonl` 다운로드를 확인했습니다.
- Demo 재생은 송신 스케줄뿐 아니라 수집 큐가 0행이 된 뒤 확인합니다. 경보 요약에서 ALARM_BEAM을 확인합니다.
- 112 복사 버튼의 실제 브라우저 클립보드 값을 확인합니다. tel 링크는 클릭하지 않고 신고 수동 기록도 제출하지 않습니다. Demo에서는 전화 링크가 없습니다.
- 1440 / 768 / 390px에서 document scrollWidth가 viewport를 초과하지 않았습니다. 그래프는 좁은 화면에서 세로 배치되고 큰 표는 자체 스크롤을 사용합니다.
- 브라우저 pageerror는 0개입니다. 한글 폰트를 준비한 후 캡처에서 글자 깨짐·문서 가로 넘침·시각적 겹침을 확인했습니다.
- 자동 갱신은 일부 fragment에만 적용되고 정적 메뉴·입력·접힌 패널은 갱신 대상에서 빠집니다. 짧은 실행에서 심각한 깜빡임은 관찰되지 않았으나 별도의 영상·정량 프레임 분석은 수행하지 않았습니다.

캡처: [미연결 관제](ui-verification/security-disconnected.png), [보안 Demo](ui-verification/security-demo.png), [신고 준비](ui-verification/emergency-demo.png), [DMA Demo](ui-verification/dma-demo.png), [센서 상세](ui-verification/sensor-details.png), [모바일](ui-verification/dma-mobile.png). 캡처는 합성/미연결 상태이며 실제 하드웨어 화면이 아닙니다.

## 기존 구조와 비교 측정

동일한 현재 합성 JSONL과 추가 합성 STAT를 넣어 **7200구간 버퍼 / SQLite 10,229행** 상태를 만들었습니다. 같은 Python/패키지 환경에서 분리 프로세스로 AppTest 전체 재실행을 각 모드 3회 측정했습니다. 닫힌 패널은 기본 상태입니다. 벤치마크는 네트워크나 모델을 호출하지 않습니다. 기존 코드에는 idle 진단 스레드가 존재하며 새 코드에는 없습니다.

| 측정 | 기존 5탭 | 새 보안 관제 | 새 DMA Lab |
|---|---:|---:|---:|
| 렌더 중앙값 (ms) | 1266.26 | 533.78 | 594.78 |
| 범위 (ms) | 1222.27~1403.00 | 238.70~622.62 | 579.90~824.90 |
| 기본 생성 그래프 수 | 7 | 0 | 4 |
| 일반 갱신 원본 DB 조회 | 회당 10,000행 | 0행 | 0행 |
| 프로세스 최고 RSS (MiB) | 268.37 | 새 두 모드 통합 216.93 | 같은 프로세스 |

원자료: [before](benchmark-before.json), [after](benchmark-after.json). 재현 도구: [benchmark_ui.py](../scripts/benchmark_ui.py). 측정은 UI 생성/직렬화를 포함한 AppTest 경과 시간이며 실제 브라우저 paint FPS·MCU 처리 속도·전체 WSL RAM을 의미하지 않습니다. 3회뿐인 짧은 합성 비교이므로 모든 PC에서 같은 개선 폭을 보장하지 않습니다. RSS는 OS의 프로세스 최고값이며 현재 사용량과 다릅니다. 기존 버전에서는 혼합 node의 Arrow 자동 복구 경고도 재현됐습니다.

## 메모리 가속 시험

[soak_runtime.py](../scripts/soak_runtime.py)로 합성 STAT **40,000행**을 약 **129.19초**에 연속 처리했습니다. 실시간 11시간 운영을 대체하는 시험이 아니며 수신 UART를 사용하지 않았습니다.

| 처리량 시점 | Python 현재 힙 (MiB) | STAT 버퍼 | 원본 메모리 버퍼 |
|---|---:|---:|---:|
| 20,000행 | 14.34196 | 7200 | 2000 |
| 40,000행 | 14.33787 | 7200 | 2000 |

SQLite에는 40,000행 모두 저장됐습니다. 해당 프로세스 최고 RSS는 52.49MiB였으며 이는 Streamlit/Plotly/브라우저를 포함하지 않은 Runtime 시험입니다. 원자료: [soak-results.json](soak-results.json). 버퍼가 포화된 뒤 두 관측점 사이에서 Python 힙이 계속 증가하는 현상은 확인되지 않았습니다. 수시간 실제 장치 시험까지 무누수라고 단정하지 않습니다.

## 보존 및 미검증

- SHA-256 보존 대상: 사용자 펌웨어 6개, metrics.py, protocol_parser.py, serial_manager.py, 기존 dashboard/data/dashboard.sqlite3. 이번 앱 테스트/브라우저/벤치마크는 임시 DB만 사용했습니다. DB 자동 삭제나 diagnosis migration은 없습니다.
- **미검증:** Windows 실제 COM/배포, 4보드 물리 연결과 케이블 문제, 실제 센서·경보·MODE/LOAD/CAL 결과, 실제 DMA 공정한 6조건 우수성 실험, 수시간 4포트 연속 운영, 실제 전화 앱·경찰 신고 접수. 마지막 항목은 구현 범위 밖입니다.
- 모든 성능 예시는 합성 자료입니다. UART ORE/DMA overrun·실제 부저/RGB/릴레이 피드백·검출 지연·전체 CPU 사용률은 Not measured입니다.
- Streamlit 여러 브라우저는 같은 Runtime과 제어 상태를 공유합니다. UI 모드 전환과 입력 소스 변경의 의미를 구분해 사용하세요.
