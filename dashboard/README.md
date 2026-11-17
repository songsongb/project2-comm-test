# DMA Performance & AI Diagnostics Dashboard

PC에서 실행하는 한국어 Streamlit 계측 콘솔입니다. **최신 STM32 3대 + Uno 1대 펌웨어**를 해석하며 저장소 루트의 과거 Smoke Test README/프로토콜과 별개입니다. 기존 펌웨어·Smoke Test 파일을 변경하지 않았습니다.

현재 구현은 실제 실행 가능한 소스, 합성 Demo, JSONL 재생, 자동 테스트를 포함합니다. **실제 보드 측정 결과는 아직 없습니다.** Demo의 성능 수치를 DMA 우수성의 실험 결과로 인용하면 안 됩니다.

## Windows 설치와 실행

Python 3.10 이상(예: 3.11)을 설치하고 저장소 루트에서 PowerShell 또는 CMD로 실행합니다. IDE는 필요하지 않습니다. 아래는 가상환경 활성화 없이 실행하므로 PowerShell 실행 정책 변경이 필요 없습니다.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r dashboard\requirements.txt
.\.venv\Scripts\python.exe -m streamlit run dashboard\app.py --server.address 127.0.0.1 --browser.gatherUsageStats false
```

브라우저에서 `http://localhost:8501`을 엽니다. 종료는 터미널에서 Ctrl+C입니다. Python 3.11이 없다면 설치된 3.10 이상 버전으로 첫 명령을 바꿉니다. 검증한 주요 패키지 버전은 [검증 기록](docs/verification.md)에 있습니다.

Linux/WSL에서는:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r dashboard/requirements.txt
.venv/bin/python -m streamlit run dashboard/app.py --server.address 127.0.0.1 --browser.gatherUsageStats false
```

## 보드 없이 먼저 실행

1. 왼쪽 `입력 소스` → `Demo · 합성 데이터`를 선택합니다.
2. `Demo 시작`을 누릅니다. 기본 4배속이며 약 20초에 전체 시나리오가 재생됩니다.
3. DMA Performance에서 6개 MODE/LOAD 조합과 제외 구간을 확인합니다.
4. Sensor & Experiment에서 PLOT, 유효/무효 TRIAL, 누락 슬롯 4개가 있는 TRACE를 확인합니다.
5. AI Diagnostics에서 규칙 탐지 이력을 확인합니다. Ollama가 꺼져 있어도 실행됩니다.

상단에는 항상 DEMO/REPLAY 배너가 표시됩니다. 재생 종료 뒤 3초가 지나면 현재 상태는 만료되어 Unknown이 되고 그래프는 이력으로 남습니다. 재생은 하드웨어 명령을 전송하지 않습니다. 입력 소스 변경/재생 재시작은 실제 포트를 닫고 메모리 뷰를 초기화하며 SQLite 이력은 보존합니다.

`samples/synthetic_demo.jsonl`은 전부 **합성 데이터**입니다. 재생 입력은 `로그 파일 재생`에서 JSONL 파일을 업로드하고 시작합니다. 실제 로그는 `replay-live`, 합성 로그는 `replay-synthetic`으로 유지됩니다. Demo를 실제 측정으로 승격하지 않습니다.

## COM 포트 연결

1. 각 보드를 USB로 연결하고 Windows 장치 관리자에서 COM 포트를 확인합니다.
2. 기존 IDE Serial Monitor와 다른 Dashboard 프로세스를 닫습니다.
3. 입력 소스를 `실제 USB Serial`로 선택합니다.
4. 장치 역할 `STM32 #1 · Window`, `STM32 #2 · Door`, `STM32 #3 · Hub`, `Arduino #4`를 하나씩 선택하고 검색된 포트 또는 직접 입력한 포트로 `연결`합니다.
5. 네 포트 모두 **115200bps / 8N1**입니다. COM 번호는 하드코딩하지 않습니다. 한두 장치만 연결해도 해당 데이터만 표시합니다.

포트 열거는 자동이며 장치 역할은 사용자에게 확인받습니다. USB 장치 설명만으로 STM32 #1/#2/#3을 확실하게 구분할 수 없으므로 위험한 역할 자동 추정을 하지 않습니다. `해제` 후 포트를 다시 지정할 수 있으며 케이블 분리 시 해당 포트만 1초 간격으로 재연결을 시도합니다. 끊긴 연결을 넘어서 대기 명령을 재전송하지 않습니다.

PC 포트는 공통 펌웨어 USART2 VCP이고 **보드 간 UART는 38400bps**입니다. 이 프로그램에 과거 Smoke Test의 `t=...` 로그를 입력하면 최신 보드 데이터로 변환하지 않습니다. COM 연결 자체는 MCU USB 부팅/DTR 동작에 영향을 줄 수 있으며 실제 보드 동작은 기존 펌웨어를 따릅니다.

Overview는 PC USB 연결, 마지막 수신 시각, 최신 센서 준비 상태, Hub가 보고한 플래그를 구분합니다. Hub 경유 Window/Door 링크와 PC에 직접 연결된 Window/Door USB 포트는 서로 다른 경로입니다. 과거 상태를 현재 정상 상태로 간주하지 않습니다. Uno는 주기 상태 로그가 없으므로 포트가 열려 있어도 조용하면 수신 만료로 표시될 수 있습니다.

## DMA 성능 실험

1. 최소 Window USB를 연결합니다. MODE/LOAD 변경에는 Hub USB도 연결합니다.
2. 실제 보드에서 경보 해제·센서 기준 환경·준비 상태를 확인합니다. Dashboard는 ARM/DISARM을 제공하지 않습니다.
3. Recovery & Control에서 MODE/LOAD를 각각 승인하여 설정합니다. 명령의 후속 검증 완료를 확인합니다.
4. 해당 조건에서 STAT가 안정된 뒤 `현재 조건으로 측정 시작`을 누릅니다. 기본 시작 안정화는 2초이며 이 구간에 걸친 보고도 제외합니다.
5. 동일한 센서 환경, TRACE/PLOT 설정, USB 연결, 실험 길이(예: 조건당 30초 이상)를 유지합니다. 끝나면 `실험 종료·저장`을 누릅니다.
6. `(Polling, OFF)`, `(Interrupt, OFF)`, `(DMA, OFF)`, `(Polling, ON)`, `(Interrupt, ON)`, `(DMA, ON)`을 반복합니다. 가능하면 순서를 바꿔 여러 번 반복합니다.
7. 저장 실험에서 시작/종료 시각, 유효 구간 수, 제외 사유, pairs 합계를 확인하고 CSV를 다운로드합니다. 무효 구간을 포함한 원자료 CSV도 별도로 제공됩니다.

| 지표 | 계산 / 해석 |
|---|---|
| 처리량 | `pairs * 1000 / 이전 STAT와의 MCU ms 차이`; 1 pair는 LDR+마이크 동시 샘플이며 목표 10,000 pairs/s |
| 관측 누락률 | `skipped / (pairs + skipped) * 100`; TIM4 슬롯 차이가 포착한 누락이며 모든 ADC 유실의 절대 손실률 아님 |
| 취득 IRQ/s | `acq_irqs * 1000 / 보고 간격`; 전체 MCU IRQ 아님 |
| 취득·처리 사이클 | `acq_cycles`: 보고 구간 DWT 사이클 차분 |
| 계측 구간 시간 비율 | `acq_permille / 10` (%); **MCU 전체 CPU 사용률 아님** |

비교 통계는 구간 길이에 따라 가중하며 LOAD, MODE, source를 분리합니다. 부팅 후 첫 STAT, 관측된 MODE/LOAD 전환, 보수적 안정화 구간, 미준비, 500~1500ms 밖의 STAT 간격을 제외합니다. 펌웨어는 전환 보고를 생략하고 TX 로그도 유실될 수 있어, 멀리 떨어진 STAT의 pairs를 긴 시간으로 나누면 부당한 저처리량을 만들 수 있습니다. 따라서 구간 길이를 확정할 수 없는 보고는 비교에서 제외합니다.

현재 펌웨어가 구간 시작 시각/sequence를 내보내지 않으므로 정상적으로 1.5초보다 긴 보고도 보수적으로 제외합니다. 직접 읽은 `slots`는 uint16 차분이며 처리량의 분모로 사용하지 않습니다. 관측되지 않은 빠른 설정 변경/펌웨어 누락을 완벽하게 복원할 수 없습니다.

일반 ADC Interrupt는 샘플마다, DMA는 32 pairs Half/Full Complete마다 처리합니다. **설계상 기대치**는 각각 약 10,000 IRQ/s와 312.5 IRQ/s이며 실측값이 아닙니다. CPU 사이클/관측 누락/부하 조건까지 함께 비교해야 합니다.

## 센서 / TRACE / TRIAL

- Window의 `PLOT 표시 시작`/`중지`는 고정 명령 `PLOT`/`PLOTOFF`만 전송합니다. 5Hz 저속 필터 표시이며 고속 원파형이 아닙니다.
- `TRACE 캡처 요청`은 Window에 `TRACE`를 보내 캡처를 대기시킵니다. 레이저 작동은 수행하지 않습니다. 실제 펄스 실험은 기존 장치의 수동 절차를 사용합니다.
- TRACE는 감지 전후 ±100ms, 10kHz, 2001슬롯입니다. 명시적 `TRACE_GAP`과 PC 수신 누락은 모두 빈 값과 붉은 구간으로 표시하며 보간하지 않습니다. END 개수/전체 커버리지가 다르면 incomplete입니다.
- `TRIAL.command_ms`는 PB0 기준 펄스 폭입니다. 센서 검출 지연으로 해석하지 않습니다. 유효(valid=1) 시험만 감지 성공률 분모에 포함하고 무효 건수는 따로 표시합니다. MODE/LOAD/펄스 폭별 통계도 제공됩니다.

## Ollama 설정과 진단

[Ollama Windows 설치 파일](https://ollama.com/download/windows)을 설치하고 별도 터미널에서 모델을 준비합니다.

```powershell
ollama pull qwen2.5:7b
ollama list
# Ollama 앱이 서버를 실행하지 않은 경우에만:
ollama serve
```

기본 주소는 `http://localhost:11434`, 모델은 `qwen2.5:7b`, 제한 시간은 30초입니다. 이는 기본 설정 예시이며 PC 자원에 맞는 설치된 모델 이름을 AI Diagnostics → Ollama 설정에서 바꿀 수 있습니다. 연결 검사는 아래처럼 할 수 있습니다.

```powershell
Invoke-RestMethod http://localhost:11434/api/tags
```

모델 미설치·접속 실패·Timeout·잘못된 JSON은 `unavailable` 이력으로 남깁니다. 기본 화면과 시리얼 수집은 계속 동작합니다. 초기에는 자동 진단이 꺼져 있습니다. `새 이상 탐지 시 Ollama 진단 요청`을 켜거나 선택한 이상/자연어 질문을 수동 요청합니다. 정상 STAT마다 추론하지 않습니다.

규칙 탐지 대상은 SENSOR_FAULT/CAL_WAIT/ARM_NOT_READY/LINK_LOST/CMD_TIMEOUT, 프레임 오류 증가, 목표 대비 90% 미만의 유효 처리량, observed skipped, DMA pairs=0, ARM_BUSY/ARM_PATH_NOT_CLEAR, TRACE 실패, 무효 TRIAL/유효 감지 실패, ALARM 이벤트입니다. 같은 장치/세션/이상은 기본 30초 쿨다운을 적용합니다.

요청에는 관련 근거와 최근 로그, 출처별 DMA 요약을 제한해서 담습니다. 질문 시에도 수집 근거가 없으면 요청을 거부합니다. JSON Schema 응답을 받고 사실의 field/value/evidence ID를 입력과 정확히 대조합니다. 근거에 없는 수치·로그 식별자·허용 목록 밖 조치·금지 조작을 거부합니다. 자유 문장으로 된 원인 설명 전체를 수학적으로 증명할 수는 없으므로 항상 **미확정 가설**로 표시합니다. 진단 지연/모델 추론 total_duration과 전체 소요 시간을 이력에 저장합니다.

LLM은 도구 호출이나 시리얼 접근 권한이 없습니다. 조치 목록은 단순 enum 제안이며 명령은 별도의 안전한 승인 흐름으로만 전송합니다. UART ORE/DMA 오버런/전력/검출 지연 같은 미계측 항목을 실제 측정 정보로 만들지 않습니다.

## 제한적 복구 사용

1. 실제 모드에서 Hub를 연결합니다. 연결 중 1초마다 읽기 전용 STATUS를 자동 조회합니다. HELP도 수동 조회할 수 있습니다.
2. 두 센서 READY·비활성, Hub DISARMED, 2.5초 이내 완성된 STATUS 묶음이 필요합니다. 실험 진행/다른 명령 대기가 관측되면 차단합니다.
3. 명령과 영향을 확인하고 실제 UNO/PB0 실험이 진행 중이지 않음을 체크합니다. CAL은 광 경로·문 기준 위치·환경 확인을 별도로 체크합니다.
4. `승인 요청 준비` 후 20초 안에 `위 명령의 실제 전송을 승인합니다`를 누릅니다.
5. 승인과 실제 UART write 사이에 상태를 재검사합니다. 상태 변화, 재연결, 재부팅, 만료가 있으면 차단합니다. 상태가 바뀌었다가 원래로 돌아와도 이전 승인은 무효입니다.
6. CMD_ACK/REJECT/TIMEOUT을 node/type/value로 매칭합니다. CAL은 두 노드 ACK가 모두 필요합니다.
7. ACK 후 STATUS 및 실제 Window STAT(MODE/LOAD/READY), CAL은 Door 진단까지 재확인합니다. 12초 내 확인이 부족하면 `unknown`으로 끝내며 추가 명령을 반복하지 않습니다.

`verified`는 **요청한 설정/준비 상태를 후속 로그로 확인했다는 뜻**입니다. 기존 장애의 근본 원인이 해결되었다고 판정하지 않습니다. 전후 데이터와 결과를 이력에서 확인하세요. `MODE 2`는 DMA 모드 선택이며 범용 고장 복구가 아닙니다.

허브 STATUS에는 실험 level, 실제 PB0 level, pending, adc_available/acquisition_fault, heartbeat age가 없습니다. 보이지 않는 전제 조건은 사용자 확인 후 MCU가 최종 거부할 수 있습니다. PC는 보수적으로 **FAULT 중 CAL도 차단**합니다. 고장 상태에서 재보정이 필요한 경우 현장 점검과 기존 수동 절차를 사용해야 합니다.

**제공하지 않는 명령:** ARM, DISARM, Uno LASER ON/OFF, TEST, STOP, DEMO, 임의 GPIO/레지스터, 재부팅/펌웨어 재설정. Window TH 변경도 이 Dashboard에서는 제공하지 않습니다. PLOT/TRACE는 LLM 복구와 분리된 수동 계측 기능입니다.

## 저장과 구조

원본 로그는 `dashboard/data/dashboard.sqlite3`의 records에 PC 수신 시각(UTC), device, port, source, session, raw와 파싱 결과를 저장합니다. 진단/이상/승인·명령/실험/완료 TRACE는 artifacts에 저장합니다. UI가 사용하는 최근 버퍼는 제한되지만 DB는 전체 이력을 유지합니다. DB는 자동 삭제/회전하지 않으므로 장기 실험 후 별도 백업합니다. 다운로드 버튼의 원본 JSONL은 최근 10,000행입니다. 전체 DB 내보내기는 아래 도구를 사용합니다.

```powershell
.\.venv\Scripts\python.exe -m dashboard.export_logs --output full_session.jsonl
```

저장 경로를 바꾸려면 실행 전 환경 변수 `DASHBOARD_DATA_DIR`를 설정합니다.

```powershell
$env:DASHBOARD_DATA_DIR = "C:\DMA-Lab\sessions\run01"
```

| 모듈 | 역할 |
|---|---|
| app.py / pages/ | 5개 화면, 캐시된 단일 Runtime, 1초 fragment 갱신 |
| serial_manager.py | 포트별 독립 reader/writer, OS 포트 락, 재연결, 명령 큐 |
| protocol_parser.py / models.py | 실제 소스별 파서, 원본 시간·출처 보존 |
| state_manager.py / metrics.py | 재부팅 세션, 최신성, TRACE, 구간 계측·실험 |
| storage.py / export_logs.py | SQLite WAL, 승인/진단/측정 이력, 전체 로그 내보내기 |
| anomaly_detector.py | 규칙 탐지, 장치별 쿨다운 |
| llm_client.py / diagnosis_manager.py | 로컬 Ollama, JSON 검증, 비동기 중복 방지 |
| command_controller.py | allowlist, 단일 승인, 전송 직전 재검사, 후속 검증 |
| runtime.py / replay.py | 수집 큐, 소스 분리, 원본 JSONL 재생 |

Streamlit 재실행은 `st.cache_resource`의 단일 Runtime을 재사용합니다. 포트별 단일 스레드가 read/write를 소유하고 UI는 스냅샷만 읽습니다. OS 락은 다른 Dashboard 프로세스의 동일 포트 열기도 차단합니다. 외부 Serial Monitor의 점유는 OS/PySerial 오류로 표시됩니다. PC 큐 초과는 별도 PC 오류로 표시하며 MCU DMA 오류 카운터로 바꾸지 않습니다.

## 테스트

```powershell
.\.venv\Scripts\python.exe -m pytest -c dashboard\pytest.ini dashboard\tests -q
```

Linux:

```bash
.venv/bin/python -m pytest -c dashboard/pytest.ini dashboard/tests -q
make test
```

실행 결과와 하드웨어 미검증 범위: [검증 기록](docs/verification.md). 실제 프로토콜 분석 및 추가 계측 제안: [펌웨어 분석](docs/firmware_analysis.md). 변경 파일과 요구사항 대응: [변경 내역](docs/implementation.md).

API 구현 참고: [Streamlit fragment](https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment), [Streamlit AppTest](https://docs.streamlit.io/develop/api-reference/app-testing/st.testing.v1.apptest), [Ollama generate / structured format](https://docs.ollama.com/api/generate).
