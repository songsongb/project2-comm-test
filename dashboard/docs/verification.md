# 검증 기록

실행일: 2026-11-17 (Asia/Seoul). Linux/WSL, Python 3.10.12. 작업 브랜치 `feature/dashboard-llm`, 기존 HEAD `021eed5`. 기존 tracked 파일은 `git diff --exit-code`로 변경 없음 확인. 원본 펌웨어는 [분석 문서의 SHA-256](firmware_analysis.md)으로 보존 기준을 기록했습니다.

## 실제 실행 결과

```text
.venv/bin/python -m pytest -c dashboard/pytest.ini dashboard/tests -q
73 passed

make test
PASS C vectors + 1,000,000-byte parser fuzz + 100,000 state events (ASan/UBSan)
Ran 23 tests
OK

.venv/bin/python -m compileall -q dashboard
exit 0

.venv/bin/python -m pip check
No broken requirements found.
```

정확한 pytest 실행 시간과 개별 testcase는 [stdout](pytest-results.txt), [JUnit XML](pytest-results.xml)에 저장합니다. 기존 Makefile의 LeakSanitizer 비활성화 조건은 그대로 유지했고 기존 sanitizer/C/Smoke Test 코드는 변경하지 않았습니다.

Streamlit 서버를 loopback 127.0.0.1:8501로 실제 실행했고 `/_stcore/health`가 **HTTP/1.1 200 OK**, body `ok`를 반환했습니다. 서버 소켓/HTTP 접근은 샌드박스 제한으로 승인된 외부 실행에서 확인했습니다. 테스트용 서버는 검증 후 종료합니다. HTTP health만으로 브라우저 UI를 검증했다고 주장하지 않습니다. 별도로 AppTest가 미연결 상태, Demo 모드 변경/시작, 전체 합성 로그의 5개 탭/그래프/표 생성과 단일 Runtime 재사용을 확인합니다.

주요 설치 버전: Streamlit 1.65.0, Plotly 6.9.0, Pandas 2.3.3, PySerial 3.5, Pytest 9.2.0. Windows에서는 requirements 범위 내 해당 플랫폼의 패키지가 설치되며 실제 Windows 실행은 아래처럼 미검증입니다.

## 필수 16개 항목 대응

| 요구 | 실제 자동 검증 |
|---|---|
| 1 STAT 정상 파싱 | 정확한 tag+17 숫자, 필드·자료형 |
| 2 필드 수/자료형 거부 | 부족/초과/비정수/범위/음수/uint32 초과 파라미터 테스트 |
| 3 세 mode 식별 | 0/1/2 → Polling/Interrupt/DMA |
| 4 처리량·누락률 | 1200ms 구간 정확 계산, counter 재차분 안 함, 분모 0 Unknown, 가중 요약·LOAD 분리 |
| 5 PLOT | 장치별 파싱, 상태 갱신, 화면 그래프 생성 |
| 6 TRACE | explicit GAP null, PC 수신 누락 null, END 개수 검증, ABORT, 전체 2001슬롯 시나리오 |
| 7 Hub 이벤트 | ALARM/STATE/FLAGS/CMD 결과, STAT alias와 성능 STAT 분리 |
| 8 센서 flags | READY/ACTIVE/SENSOR_FAULT 및 unknown bits |
| 9 섞인 포트 | Window/Hub 식별 보존 및 동시 fake Window/Door 수신 |
| 10 재부팅 | timestamp 역행, uint32 wrap, BOOT, 지연 TRIAL 구별, ACK 뒤 reboot 확인 불가 |
| 11 Ollama 실패 | 접속 거부/Timeout stub 중 STAT 수집·처리 지속, unavailable 기록 |
| 12 미허용 LLM 명령 | ARM/DISARM/LASER/MODE 9/RESET/newline injection 거부, 가짜 evidence/수치/로그 거부 |
| 13 무승인 조작 | 승인 누락, CAL 기준 확인 누락, 20초 승인 만료 거부 |
| 14 결과 처리 | CMD_ACK/REJECT/TIMEOUT, wrong node/type/value 무시, CAL 양 ACK, 후속 STATUS+센서 필수 |
| 15 오래되거나 없는 상태 | stale/missing STATUS, 큐 대기 중 stale, 상태 변경·원복, 재연결, 외부 pending 차단 |
| 16 Replay 일관성 | 같은 원본의 동일 parsed fields, 원본 PC 시각 유지, source 분리, 6조건 전체 합성 재생 |

추가 검증: 실제 PySerial↔Linux PTY 로그 수신/명령 왕복, 포트별 자동 재연결·다른 포트 지속 수신, 다른 프로세스의 중복 포트 락 거부, 단일 승인 중복 사용 거부, 다른 제안의 중복 실행 거부, 부분 write 결과 unknown, ACK만으로 verified 금지, JSONL 전체 SQLite export 및 덮어쓰기 차단, 저장 실험의 경계/조건 변경 제외, 규칙 쿨다운, 정상 STAT의 자동 LLM 미호출, 중복 진단 방지.

PTY는 실제 UART 하드웨어가 아닙니다. Ollama 성공 응답은 HTTP client mock을 통한 schema·payload·timeout 경로 검증이며 실제 모델의 한국어 추론 품질 검증이 아닙니다.

## 미검증 / 남은 실행 절차

| 항목 | 상태 / 이유 |
|---|---|
| Windows 실제 설치·COM 열기·msvcrt 락 | **미검증** — 현재 실행 OS는 Linux/WSL. 이식 가능한 경로/Windows 락 분기를 구현했지만 실제 Windows가 필요 |
| 실제 4보드·부분 하드웨어 연결·케이블 분리 | **미검증** — 실제 장치 없이 fake serial와 Linux PTY로 검증 |
| DMA 실제 성능과 공정한 6조건 실험 | **미검증** — 제공 실측 로그 없음. 합성값을 실측으로 사용하지 않음 |
| 실제 센서/경보/TRACE/TRIAL | **미검증** — 실제 로그 형식은 코드로 확인했고 수신 경로는 합성 자료로 검증 |
| 실제 MODE/LOAD/CAL UART 실행 | **미검증** — PC 승인/전송/결과 경로는 mock 및 PTY, MCU 수락과 물리 변화는 실장치 필요 |
| 실제 Ollama 서버/모델 추론·GPU/CPU 지연 | **미검증** — 모델 설치/실서버 호출 없이 mock 성공/실패/timeout을 검증 |
| 브라우저 시각 QA/스크린샷 | **미검증** — 브라우저 자동화 도구 없음. Streamlit AppTest 실행·HTTP health는 검증 |
| 수시간 이상 4포트 연속 스트레스 | **미검증** — bounded buffer/독립 reader/SQLite WAL 구조 및 단기 테스트만 수행 |
| 펌웨어 rebuild/업로드 | **미수행** — 원본 보존 요구에 따라 PC 구현만 추가 |

실장치 검증은 [README의 6조건 절차](../README.md)를 따라 raw JSONL/SQLite와 각 실험 CSV를 저장한 뒤 진행합니다. 실제 경보가 발생했을 때 자동 경보 해제·레이저 작동을 하지 않는지, MCU reject가 실패로 남는지, 장치/상태가 끊기면 명령이 거부되는지를 함께 확인하세요.
