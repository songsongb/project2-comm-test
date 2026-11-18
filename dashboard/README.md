# Laser Guard · Security Monitoring & DMA Performance Lab

STM32 3대 + Arduino Uno 1대의 PC용 한국어 계측·보안 관제 콘솔입니다. **LLM/Ollama 기능과 추론 스레드·큐·설정·자연어 질의를 완전히 제거했습니다.** 별도 모델이나 Ollama 설치가 필요하지 않습니다. 기존 SQLite의 과거 진단 기록은 삭제하지 않고 UI에서 숨깁니다. 규칙 기반 센서·통신·DMA 이상 탐지는 계속 동작합니다.

원본 펌웨어 6개, `metrics.py` 계산식, 실제 통신 파서와 시리얼 수신 구현은 보존했습니다. 실제 DMA 실험 수치는 제공되지 않았으며 Demo 값은 전부 합성입니다.

## Ubuntu / WSL 실행

저장소 루트에서 Python 3.10 이상으로 실행합니다.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r dashboard/requirements.txt
.venv/bin/python -m streamlit run dashboard/app.py --server.address 127.0.0.1 --browser.gatherUsageStats false
```

브라우저에서 `http://localhost:8501`을 엽니다. 종료는 Ctrl+C입니다. STM32CubeIDE/Arduino IDE는 필요하지 않습니다. WSL에서 실제 USB 장치 전달·시리얼 권한은 별도로 설정되어 있어야 합니다. COM 연결이 목적이면 Windows Python으로 직접 실행할 수도 있습니다. 한글이 사각형으로 보이는 최소 Ubuntu 환경은 시스템 한글 폰트(예: `fonts-noto-cjk`)를 설치하고 브라우저를 다시 시작하세요.

## Windows 실행

PowerShell/CMD에서 가상환경 활성화나 실행 정책 변경 없이 실행할 수 있습니다.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r dashboard\requirements.txt
.\.venv\Scripts\python.exe -m streamlit run dashboard\app.py --server.address 127.0.0.1 --browser.gatherUsageStats false
```

설치된 Python 3.10 이상 버전에 맞게 첫 명령의 버전을 바꾸세요. Windows 실제 COM/잠금 분기는 이번 Linux 검증 환경에서 미검증입니다.

## 두 화면 모드

상단 `보안 관제` / `DMA 성능 분석` 메뉴로 전환합니다. **화면 전환은 Runtime·COM 포트·로그·실험을 초기화하지 않습니다.** 왼쪽 `입력 소스`의 실제/Demo/Replay 변경과는 별개입니다. 입력 소스를 변경하거나 재생을 다시 시작하면 실제 포트는 닫고 현재 메모리 뷰만 초기화하며 SQLite는 보존합니다.

기본 화면 갱신은 **3초**, 설정에서 2/3/5초를 선택할 수 있습니다. 시리얼 수집·규칙 탐지·저장 및 연결된 Hub의 읽기 전용 STATUS 1초 조회는 UI 갱신과 독립적입니다. 마지막 수신 3초 경과 시 현재 상태를 만료 처리하며, 화면은 선택한 갱신 주기에 이를 반영합니다.

### Security Monitoring · 보안 관제

- 큰 상태 표시: DISARMED(감시 해제), ARMED(감시 중), SUSPECT, ALARM, FAULT, Unknown.
- DISARMED는 침입 감시가 해제되었다는 의미입니다. 센서가 정상이라는 것과 감시 활성화는 별개입니다.
- Window/Door/Hub/Uno 카드에 USB 연결·수신 최신성·준비 상태·현재 확인 가능한 센서 정보를 표시합니다. PC USB와 Hub↔센서 통신 경로를 구분합니다.
- Window LDR/임계값, Hub가 보고한 flags, Door open/closed, 최근 BEAM/SOUND/SHOCK 등의 관측을 보여줍니다. 이벤트는 발생 이력이며 현재 활동 상태로 추정하지 않습니다.
- Uno 릴레이/RGB/부저는 주기 피드백이 없어 `Not measured`입니다. 실험 상태도 마지막 보고와 현재 Unknown을 구분합니다.
- 타임라인은 실제 Hub 이벤트 이름·당시 상태·노드·PC 수신 시각·Hub MCU 시각·출처를 표시합니다. ALARM 이벤트는 강조하지만 과거 이벤트를 현재 경보로 승격하지 않습니다.
- 센서/통신/DMA 규칙 이상은 최근 관측 목록에 남습니다. 상세 연결/원본 로그는 접힌 패널에서 확인합니다.

### 경찰 신고 지원 · 112

접힌 `경찰 신고 지원 · 112` 패널을 열면 번호 복사, 사용자가 직접 입력한 주소/위치, 최근 경보 기반 요약 복사를 사용할 수 있습니다. 경찰 긴급 번호는 **112**입니다. 공식 안내: [행정안전부 긴급신고 통합서비스](https://mois.go.kr/frt/sub/a06/b10/emergencycall/screen.do).

- **실제 신고 전송·접수 확인·외부 경찰 시스템 연동은 없습니다.** Dashboard의 어떤 버튼도 자동 신고하지 않습니다.
- 실제 입력 모드에서만 사용자가 전화 앱 지원을 확인한 뒤 `tel:112` 링크를 표시합니다. 지원 기기에서 전화 앱을 여는 용도이며 접수 결과가 아닙니다. 전화 앱이 없는 PC에서는 번호 복사만 사용하세요.
- Demo/Replay에서는 연습 자료 표시와 복사만 제공하고 전화 링크를 숨깁니다.
- 요약은 센서 관측 로그와 사용자 입력 위치를 명시적으로 나눕니다. 주소 자동 추정·생성은 하지 않습니다. PC 수신 시각은 정확한 현장 사건 시각과 다를 수 있습니다.
- 선택적으로 `사용자가 직접 신고했습니다`를 확인하고 로컬 수동 기록을 저장할 수 있습니다. `receipt_verified=false`이며 사용자의 진술만 기록합니다. Demo/Replay는 `practice_record`로 저장합니다. 입력 주소는 이 수동 저장을 누를 때만 해당 기록에 포함됩니다.
- 클립보드 권한이 없는 브라우저는 표시된 번호/요약을 직접 선택해 복사할 수 있습니다.

### DMA Performance Lab · DMA 성능 분석

상단에 현재 Mode/LOAD, 최근 처리량, 관측 누락률, 취득 IRQ/s, 취득·처리 계측 시간 비율, 비교 유효성을 표시합니다. 오래된 값은 마지막 측정 이력임을 알립니다.

기본 2×2 그래프:

1. **Throughput:** Polling/Interrupt/DMA × LOAD OFF/ON, 목표 10,000 pairs/s 기준선.
2. **Observed Sample Loss:** 0% 실측 관측값과 `No data` 미측정을 구분.
3. **Interrupt Frequency:** 실제 로그 IRQ/s. 설계상 이상적 Interrupt 약 10,000/s, DMA 약 312.5/s는 설명용 기대치이며 실측이 아닙니다.
4. **CPU Acquisition Burden:** acq_permille/10의 계측 구간 %, acq_cycles를 유효 초로 나눈 cycles/s. 원본 사이클 합계는 아래 표에 보존합니다. **전체 CPU 사용률이 아닙니다.**

6조건 비교 표에는 유효 구간 수·처리량·관측 누락률·IRQ/s·계측 시간 비율·사이클 합계·제외 건수/사유·시각·포트·출처가 표시됩니다. **출처/포트/부팅 세션을 선택한 뒤** 동일 범위에서만 기존 `summarize()`를 사용합니다. 세션이나 보드가 다른 자료를 무리하게 합치지 않습니다.

기존 계산식은 유지했습니다.

| 지표 | 의미 |
|---|---|
| pairs/s | 보고 구간 pairs × 1000 / 인접 STAT의 MCU ms 차이; 한 pair는 LDR+마이크 동시 샘플 |
| 관측 누락률 | skipped / (pairs + skipped) × 100; TIM4 슬롯 기반으로 관측한 누락이며 모든 ADC 유실의 절대 손실률 아님 |
| IRQ/s | acq_irqs × 1000 / 보고 간격; 전체 MCU IRQ가 아님 |
| 계측 부담 | acq_cycles, acq_permille; 지정 취득·처리 경로만 계측 |

처음/설정 전환/안정화/보고 간격 이상/미준비 구간은 기존 계산대로 제외합니다. 정상 범위를 벗어난 보고 사이의 정확한 firmware 구간 길이는 확인할 수 없어 보수적으로 제외합니다.

#### 실험 절차

1. Window USB로 STAT를 수신하고 Hub USB로 설정합니다. MODE/LOAD 변경은 아래 승인 절차를 사용합니다.
2. 보드에서 감시 해제와 센서 준비·정상 환경을 확인합니다.
3. 원하는 MODE/LOAD가 실제 후속 로그에서 확인된 뒤 `실험 구간 관리` 패널에서 시작합니다. 기본 안정화 2초와 경계 구간은 제외합니다.
4. 같은 센서 환경, PLOT/TRACE 설정, 측정 시간(예: 30초 이상)을 유지합니다.
5. 종료·저장 후 6조건(Polling/Interrupt/DMA 각각 LOAD OFF/ON)을 반복합니다. 가능하면 순서를 바꿔 여러 번 반복합니다.
6. 저장 결과 요약에서 source/port/session/mode/load/시각/제외 건수를 확인하고 필요한 실험만 불러와 CSV를 받습니다.

한 실험은 RAM 제한을 위해 7,200개 STAT 보고 구간에서 자동 저장·종료합니다. 원본 수집은 계속됩니다. 전체 메모리 STAT 버퍼도 최근 7,200구간입니다. 더 긴 비교는 실험을 나눠 저장하고 원본 DB를 보존하세요.

#### 센서·TRACE·TRIAL 패널

패널을 **열었을 때만** 파형 데이터를 읽고 갱신합니다. PLOT은 최근 600개(기본 약 2분)를 표시하고 min/max 방식으로 표시 점만 줄입니다. 최대·최소와 모든 누락 지점을 보존합니다. 통계에는 축약 데이터를 쓰지 않습니다.

TRACE는 2,001슬롯 전체를 보존하고 explicit GAP/PC 수신 누락을 null과 붉은 영역으로 표시하며 보간하지 않습니다. TRIAL은 valid=1만 성공률의 분모에 포함하고 무효 시험은 따로 셉니다. command_ms는 PB0 기준 펄스 폭이며 감지 지연이 아닙니다.

PLOT/PLOTOFF/TRACE는 Window VCP로만 보내는 수동 계측 명령입니다. 레이저·릴레이 동작은 하지 않습니다.

#### 장치 설정 및 실험 제어

허용 명령은 STATUS, HELP, MODE 0/1/2, LOAD 0/1, CAL입니다. 승인 단계와 기존 Command Controller의 전송 직전 검사·ACK 매칭·후속 로그 검증은 유지합니다.

- 최신 2.5초 이내의 완성된 실제 Hub STATUS, DISARMED, 두 센서 READY·비활성, 다른 pending/실험 없음 조건을 확인합니다.
- 실제 UNO/PB0 펄스가 유휴임을 사용자가 확인해야 합니다. CAL은 광 경로·문 기준 위치·환경을 별도로 명시적 확인합니다.
- 승인 준비 후 20초 이내 실제 전송을 승인합니다. 연결/상태/세션이 바뀌거나 만료되면 거부합니다.
- CMD_ACK/REJECT/TIMEOUT을 node/type/value로 매칭합니다. CAL은 두 노드 ACK와 이후 Window/Door 준비 상태가 필요합니다.
- 12초 내 후속 계측이 부족하면 unknown으로 기록합니다. ACK만으로 장애 해결을 주장하지 않으며 자동 반복하지 않습니다.
- Demo/Replay는 UI뿐 아니라 Controller에서도 차단합니다.
- ARM/DISARM, LASER/릴레이, Uno TEST/STOP/DEMO, 임의 GPIO/레지스터, 리셋, Window TH 변경은 제공하지 않습니다.

현재 firmware STATUS는 experiment/PB0/pending/heartbeat age 전체를 보고하지 않습니다. 숨겨진 전제 조건은 사용자 확인과 MCU의 최종 reject에 의존하며 FAULT 중 CAL은 보수적으로 차단합니다. MODE 2는 DMA 모드 요청이지 범용 복구가 아닙니다.

## 실제 장치 연결

왼쪽에서 `실제 USB Serial`을 선택하고 장치 역할을 수동 매핑합니다. 자동 검색된 포트나 직접 입력한 COM/장치 경로를 연결합니다. 포트 번호는 고정하지 않습니다. 모든 PC 포트는 **115200bps, 8N1**이고 보드 간 UART는 38400bps입니다.

```bash
.venv/bin/python -m serial.tools.list_ports
```

각 장치는 다른 포트가 필요하고 IDE Serial Monitor는 닫아야 합니다. 같은 포트는 단일 reader/writer와 OS 락으로 소유합니다. 한 포트가 끊겨도 다른 포트는 계속 수집하며 해당 포트만 1초 간격 재연결합니다. 재연결을 넘어서 대기 승인 명령을 재전송하지 않습니다. 일부 보드만 연결하면 받은 정보만 표시합니다. Uno의 조용한 USB 포트는 열려 있어도 최신 수신은 Unknown일 수 있습니다.

## Demo / Replay

`Demo · 합성 데이터` → `Demo 시작`으로 보드 없이 두 화면을 확인합니다. 약 100초 분량이며 4배속 기본, 0.5/1/2/4/10배속을 선택할 수 있습니다. 보안 상태 변화를 천천히 보려면 1배속을 사용하세요.

Demo에는 6조건 DMA 비교, PLOT, 누락 4슬롯 TRACE, 유효/무효 TRIAL과 실제 Hub에서 가능한 READY/ARM/DOOR_OPEN/SHOCK/SOUND/BEAM/ALARM/DISARM/LINK_LOST/SENSOR_FAULT 이벤트가 있습니다. 해당 이벤트는 **물리·수동 동작을 흉내 낸 로그**이며 Dashboard가 명령을 실행하는 것이 아닙니다.

Replay는 source와 PC 시각/device/raw가 포함된 JSONL 파일을 선택해 시작합니다. `live`는 `replay-live`, 합성은 `replay-synthetic`으로 보존합니다. 부팅 세션과 MCU uint32 wrap/지연 TRIAL 구분은 유지합니다. 재생 종료 뒤 현재 수신이 만료되어도 이력·그래프는 남습니다. 과거 자료를 현재 실측으로 표시하지 않습니다.

## 저장·다운로드·운영 범위

기본 DB는 `dashboard/data/dashboard.sqlite3`입니다. 실행 전 `DASHBOARD_DATA_DIR`로 디렉터리를 바꿀 수 있습니다. 브라우저 UI 테스트는 별도 임시 DB를 사용했습니다.

- 모든 원본 로그: device/port/source/session/PC 수신 UTC/MCU ms/raw/파싱 결과를 SQLite에 보존.
- 규칙 이상/수동 명령·승인/실험/완료 TRACE/수동 신고 진술 기록: artifacts에 보존.
- 기존 diagnosis artifacts는 삭제·변환하지 않고 UI에서 읽지 않습니다.
- 평소 갱신에서는 DB의 전체 원본을 조회하지 않습니다. 최근 로그 30행은 메모리에서 표시합니다.
- `원본 JSONL 다운로드 준비`를 누르면 현재 입력 소스의 최근 2,000행만 DB에서 읽습니다. 실험/TRACE/TRIAL/6조건 CSV도 명시적으로 준비합니다.
- 전체 DB 원본은 메모리를 일정하게 유지하는 CLI로 내보낼 수 있습니다. 출력 파일이 있으면 덮어쓰지 않습니다.

```bash
.venv/bin/python -m dashboard.export_logs --output full_session.jsonl
```

SQLite는 자동 삭제/회전하지 않습니다. 장기 운영 시 디스크와 백업을 관리하세요. UI 메모리 버퍼는 원본 2000행, 성능 7200구간, PLOT 3000개(화면 600개), TRIAL 1000개, 일반 이벤트 500개/보안 이벤트 120개, TRACE 15개입니다. 렌더 캐시·명령 제안·규칙 탐지 키도 상한을 적용합니다.

한 프로세스의 여러 브라우저는 수집기/입력 소스/승인 상태를 공유합니다. 로컬 loopback 운영이 기본이며 별도 다중 사용자 인증은 범위 밖입니다.

## 자동 테스트 / 브라우저 검증

```bash
.venv/bin/python -m pip install -r dashboard/requirements-dev.txt
.venv/bin/python -m pytest -c dashboard/pytest.ini dashboard/tests -q
make test
```

Windows는 `.venv\Scripts\python.exe`와 역슬래시 경로를 사용합니다. Linux PTY 테스트는 Windows에서 skip됩니다.

실제 Chromium QA는 선택적인 개발 도구이며 앱 의존성이 아닙니다.

```bash
.venv/bin/python -m pip install playwright
.venv/bin/python -m playwright install chromium
# Linux 브라우저 공유 라이브러리는 환경에 맞게 준비
.venv/bin/python dashboard/scripts/browser_check.py --url http://127.0.0.1:8501
```

테스트 결과·성능 측정의 조건과 한계·미검증 범위는 [검증 기록](docs/verification.md), 변경 파일은 [구현 내역](docs/implementation.md), 실제 firmware 계측 한계는 [펌웨어 분석](docs/firmware_analysis.md)을 참고하세요.
