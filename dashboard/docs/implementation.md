# UI Lite 변경 내역

기준은 `feature/dashboard-llm`의 `5de4508`이며 새 브랜치는 `feature/dashboard-ui-lite`입니다. 작업 시작 시 tracked/untracked 변경사항은 없었습니다. 변경은 PC Dashboard 디렉터리로 제한했습니다. 원본 6개 펌웨어, metrics.py, protocol_parser.py, serial_manager.py, 기존 SQLite 파일은 작업 전후 SHA-256으로 보존을 확인합니다. 구버전 Smoke Test는 수정하지 않았습니다.

## 변경 파일

| 경로 | 변경 목적 |
|---|---|
| app.py | 상단 보안 관제/DMA 전환, 3초 기본 갱신, 현재 화면만 실행, stateful lazy 패널, 명시적 다운로드 |
| pages/overview.py | 상태 대시보드·4개 노드 카드·역사 이벤트·수동 신고 지원 |
| pages/dma_performance.py | 핵심 4그래프·6조건 표·출처/포트/세션 선택·캐시·실험 메타데이터 조회 |
| pages/sensor_experiment.py | 열 때만 PLOT/TRACE/TRIAL 생성, 최근 PLOT extrema 표시, null/TRACE 전체 보존 |
| pages/recovery_control.py | 수동 승인만 유지, 과거 LLM 제안/연동 제거, typed table |
| runtime.py | LLM 객체·스레드·큐·요청·종료 경로 삭제; 시리얼/처리 스레드·규칙 보존 |
| state_manager.py | 화면별 얕은 스냅샷·revision/identity, 별도 보안 이벤트 버퍼, 장기 실험 자동 저장 상한 |
| anomaly_detector.py | node 문자열과 원본 numeric node_id 분리; 쿨다운 인덱스 상한 |
| command_controller.py | 기존 승인/전후 검사 유지, Demo/Replay Controller 차단, 제안 캐시 상한 |
| storage.py | 기존 스키마/내용 보존; 필터된 JSONL 명시적 조회, 실험 메타데이터·단건 조회 |
| presentation.py | 공통 Arrow 타입 정규화·bounded render cache·scope 필터·표시용 extrema |
| ui_components.py | responsive CSS·lazy expander·사용자 클릭 클립보드 복사 |
| emergency.py | 관측/사용자 입력 분리 요약·로컬 수동 신고 진술 기록; 외부 통신 없음 |
| requirements.txt / requirements-dev.txt | 실행용과 Pytest 개발용 분리; LLM 실행 의존성 없음 |
| samples/generate_demo.py / synthetic_demo.jsonl | 실제 firmware 이벤트 종류로 합성 보안 상태 시나리오 추가; 기존 6조건 값/TRACE 보존 |
| tests/test_app.py / test_ui_lite.py | 두 화면·lazy 동작·혼합 타입·연결 재사용·기록 보존·신고 안전성 검증 |
| scripts/benchmark_ui.py / soak_runtime.py / browser_check.py | 재현 가능한 선택적 성능·가속 스트레스·실제 Chromium QA |
| README.md / docs/ | 현재 사용법·실측 테스트 출력·측정 조건·브라우저 캡처 |

삭제: `llm_client.py`, `diagnosis_manager.py`, `pages/ai_diagnostics.py`, `tests/test_llm_anomalies.py`. 과거 diagnosis artifacts 및 이를 근거로 한 기존 command artifacts는 DB에서 삭제하지 않았고 UI에서 숨깁니다. Ollama 서비스/모델 설치·실행·삭제를 수행하지 않았습니다. 기준 버전 벤치마크에서는 과거 코드의 idle 진단 스레드만 생성되며 실제 LLM 호출은 없었습니다.

## 선택적 실행 경로

```text
USB worker × N → bounded queue → parser → state / unchanged metrics / SQLite
                                        → bounded rule anomaly observations

Streamlit singleton Runtime
  ├─ Security: latest device snapshot + bounded historical security timeline
  └─ DMA Lab: original valid metrics → selected source/port/session → 4 cached figures
      ├─ sensor panel opened → recent PLOT / complete TRACE / valid TRIAL
      ├─ experiment panel opened → metadata → explicit selected result
      └─ control panel opened → manual approval → write-time checks → ACK + followup

Emergency preparation → copy / optional user-declared LOCAL record (no dispatch)
Raw export preparation button → bounded, source-filtered SQLite read → download
```

그래프 통계 계산은 metrics.py의 기존 결과를 사용합니다. `presentation.comparison()`은 자료 범위만 나눈 뒤 원본을 `summarize()`에 넘기며, 누락/과도 구간 제외 기준은 변경하지 않았습니다. UI table은 식별/중첩 필드를 string, 명시한 계측 컬럼을 nullable numeric, boolean을 nullable boolean으로 변환합니다. Arrow 경고를 감추는 방식이 아닙니다.

UI 모드 전환 시 Runtime/state/SerialManager/worker가 재생성되지 않습니다. 입력 소스 변경은 기존과 같이 producer를 종료하고 메모리만 초기화합니다. 고유 state identity가 캐시·다운로드를 소스 변경 사이에서 분리합니다. 버전별 render cache는 최대 8항목이며 이전 revision이 무한히 쌓이지 않습니다.

## 남은 한계

- 실제 Windows COM·실제 보드·수시간 4포트·실제 DMA 우수성은 미검증입니다. 단기 Linux PTY·fake multi-port·합성 stress 결과를 실제 UART 성능으로 일반화하지 않습니다.
- PC 수신 시각은 현장 발생 시각과 다릅니다. 오래된 사건/정상 상태를 현재 상태로 추정하지 않습니다.
- firmware STATUS의 숨겨진 전제 조건(실험/PB0/pending/HB age 전체)은 여전히 확인 한계가 있습니다. CAL의 환경 확인과 MCU reject가 필요합니다.
- UI 메모리는 제한하지만 SQLite는 전체 원본을 계속 저장합니다. 디스크 백업/운영은 사용자 책임이며 자동 삭제는 하지 않습니다.
- Replay는 업로드 파일을 메모리에 파싱하므로 아주 큰 파일은 여러 파일로 나눠 재생하는 것이 좋습니다. 원본 전체 내보내기는 CLI 스트리밍을 사용합니다.
- 경보를 직접 신고하지 않습니다. 사용자 진술 저장은 실제 경찰 신고의 접수 확인이 아닙니다. 전화 앱 링크는 실제 모드에서 사용자 선택 후에만 노출합니다.
