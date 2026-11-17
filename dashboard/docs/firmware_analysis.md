# 실제 펌웨어 분석 및 계측 한계

분석 기준: 브랜치 `feature/comm-smoke-test`, HEAD `021eed5`에서 사용자가 제공한 미추적 원본 6개 파일. 작업 브랜치는 `feature/dashboard-llm`입니다. 이 6개 파일을 모두 읽고, 과거 `stm32_hub/` 및 Arduino simulator와 별도 프로토콜로 처리했습니다. 원본 파일은 편집·스테이징하지 않았습니다. pull은 로컬 기준 코드가 모두 제공되어 수행하지 않았습니다.

## UART 구조 / 레지스터 근거

공통 `laser_guard.c`는 CPU 64MHz, APB1 32MHz, TIM3/4 64MHz, ADC 약 10.67MHz를 설정합니다. RCC/FLASH/USART/ADC/DMA/TIM/GPIO/NVIC/DWT 레지스터를 직접 사용합니다.

| 장치 | PC | 보드 간 통신 | 센서 취득 |
|---|---|---|---|
| Window / STM32 #1 | USART2 PA2/PA3, 115200 | USART1 PA9/PA10, 38400 ↔ Hub USART1 | ADC1 PA1 LDR + ADC2 PA4 mic 동시 변환, TIM3 10kHz, TIM4 슬롯 카운터 |
| Door / STM32 #2 | USART2 PA2/PA3, 115200 | USART1 PA9/PA10, 38400 ↔ Hub USART3 | ADC1 PA0 Hall, TIM3 1kHz, DMA 16샘플 Half, PA8 EXTI shock |
| Hub / STM32 #3 | USART2 PA2/PA3, 115200 | USART1 ↔ Window, USART3 PB10/PB11 ↔ Door, 각 38400 | 센서 이벤트 통합 / PC7·PB6로 Uno 상태 출력 |
| Uno #4 | USB Serial 115200 | UART 센서 프레임 없음. D2/D3 Hub 2비트 입력, D4 실험, D7 기준 펄스 | RGB/Buzzer/Relay, 기존 수동 펄스 실험 |

모든 STM32 USART RX는 DMA circular 512 bytes, TX는 DMA + 소프트웨어 1024-byte 링입니다. USART1 TX/RX는 DMA1 Ch4/5, USART2 Ch7/6, USART3 Ch2/3입니다. Window ADC는 DMA1 Ch1, Door ADC도 해당 보드 DMA1 Ch1입니다.

보드 간 binary frame: `AA,len,id,type,data[0..7],XOR(len..data)`; timeout 25ms. ID Window=1/Door=2/Hub=3. HEARTBEAT=0x10, BEAM=0x20, SOUND=0x21, DOOR=0x30, SHOCK=0x31, MODE=0x80, CAL=0x82, LOAD=0x83, ACK=0x90. 이 binary frame을 PC 문자열 파서에 입력하는 구조가 아닙니다.

HEARTBEAT는 약 200ms, Hub는 마지막 heartbeat 600ms부터 LINK_LOST로 판정합니다. flags bit0 READY / bit1 ACTIVE / bit2 SENSOR_FAULT입니다. Window heartbeat는 mode도 포함합니다. PC 직접 USB 마지막 수신 시간은 이 heartbeat 시각과 다릅니다.

## Window STAT의 실제 필드

`report_samples()`는 1000ms 이상마다 스냅샷을 잡습니다. MODE/LOAD 전환 및 카운터 초기화가 감지된 보고를 생략하고 previous를 갱신합니다. 따라서 `pairs/skipped/cycles/irqs`는 이미 보고 구간 차분이며 PC가 다시 차분하면 안 됩니다.

`STAT` 태그 + **17개 숫자 필드**, 총 18 CSV 항목입니다. 시작 시 같은 이름의 헤더도 출력합니다.

| 필드 | C 자료형 / 로그 값 | 의미 |
|---|---|---|
| time_ms | uint32 / unsigned long | Window 부팅 이후 ms, PC 수신 시각 아님 |
| mode | enum → unsigned | 0 Polling / 1 Interrupt / 2 DMA |
| load | bool → unsigned 0/1 | 50ms마다 8ms foreground 추가 부하, IRQ 허용 |
| slots | uint16 차분 → unsigned | TIM4 트리거 슬롯 차분; 16bit wrap |
| pairs | uint32 차분 | `process_pair`에서 처리한 광+마이크 쌍 수 |
| skipped | uint32 차분 | process_pair의 `step > 1`에서 `step - 1` 합계 |
| acq_cycles | uint32 차분 | DWT CYCCNT 기반 poll/ADC IRQ/DMA IRQ 취득·처리 코드 경로 |
| acq_permille | uint32 | `cycles*1000/(elapsed_ms*64000)` 정수값 |
| acq_irqs | uint32 차분 | ADC1_2 또는 DMA1_Ch1 handler 진입 수; Polling은 취득 IRQ 0 |
| ldr | uint16 / 0..4095 | `4095 - ADC1`로 반전한 밝기 값 |
| min / max | uint16 / 0..4095 | 보고 구간 처리 밝기 최솟값/최댓값; 처리 0개면 min=4095,max=0 가능 |
| lit_baseline | uint16 / 0..4095 | 10,000 pairs 보정의 밝은 기준값 |
| ldr_threshold | uint16 / 0..4095 | baseline * threshold_percent / 100 |
| mic_rms | uint16 | HPF(~200Hz, Q4) 후 250 pairs(25ms) RMS, ADC counts |
| ready | bool 표현 0/1 | ready && !acquisition_fault |
| event_drops | uint32 **누적** | 센서 이벤트 ring full 누락, STAT 보고마다 차분 아님 |

Polling은 TIM4 슬롯 변화 때 SWSTART 후 EOC를 기다립니다. Interrupt는 TIM3 트리거 ADC EOC마다 처리합니다. DMA는 dual ADC 32bit packed word를 64-word circular buffer에 저장하고 Half=32/Full=32 단위로 snapshot 처리합니다. DMA 경로는 phase/lag, 복사 중 반쪽 재사용을 검사합니다.

## 기타 실제 출력

```text
PLOT,<time_ms>,<filtered_ldr>
PLOT_ON,5Hz
PLOT_OFF
TH,<percent>
TRACE_WAIT,<pre_ms>
TRACE_ARMED
TRACE_BEGIN,<sample_hz>,<first_offset>,<last_offset>,<mode>,<load>,<threshold>
TRACE_DATA,<offset>,<ldr>,<mic>
TRACE_GAP,<offset>,<count>
TRACE_END,<valid_slots>,<missing_slots>
TRACE_ABORT,<reason>
TRACE_ERROR,<reason>
TRIAL,<start_ms>,<mode>,<load>,<command_ms>,<hit>,<valid>
```

TRACE 기본 10kHz, offset -1000..1000, gap 한 행 최대64슬롯, 출력은 3ms 간격으로 재시도합니다. reason에는 timeout/early_trigger/configuration_changed/acquisition_fault 등이 있습니다. 데이터 출력은 캡처 시각보다 늦으므로 PC 수신 시각을 샘플 시각으로 사용하지 않습니다. PLOT은 10ms foreground 표시 샘플을 평균/LPF/최대변화 제한 후 200ms마다 출력합니다.

TRIAL은 PB0 rising 시 시작, falling 시 종료, 종료 후 250ms tail을 기다린 뒤 보고합니다. 겹친 pulse, 미준비/차단/취득 오류, 2초 초과 미종료는 유효성을 잃을 수 있습니다. `command_ms`는 PB0에서 측정한 pulse width이며 실제 레이저 광학 파형/센서 검출 지연은 아닙니다. `start_ms`는 지연된 과거 timestamp이므로 재부팅 검출에 쓰지 않습니다.

Door는 태그 없는 CSV:

```text
ms,raw,closed,delta,ready,open,shock_edges,fault
```

raw/closed/delta는 uint16, ready/open/fault는 bool, shock_edges/ms는 uint32입니다. Hall은 300샘플 보정, spread>100 보정 fault, open delta>=180 / close<=120, 50샘플 안정 조건입니다. DMA transfer error, 양 Half/Full 동시 pending, 100ms 블록 지연은 hall_dma_fault입니다. 출력 fault는 hall_cal_fault와 hall_dma_fault의 합성 플래그이므로 출력만으로 두 원인을 확정할 수 없습니다.

Hub는 `ms,event,node,value,state`입니다. state는 DISARMED/ARMED/SUSPECT/ALARM/FAULT. STATUS/STAT alias는 아래 5행을 같은 ms로 출력합니다. PC의 성능 STAT와 별개입니다.

```text
<ms>,WINDOW_FLAGS,1,<flags>,<state>
<ms>,DOOR_FLAGS,2,<flags>,<state>
<ms>,WINDOW_MODE,1,<mode_or_255>,<state>
<ms>,WINDOW_FRAME_ERRORS,1,<cumulative_parser_errors>,<state>
<ms>,DOOR_FRAME_ERRORS,2,<cumulative_parser_errors>,<state>
```

parser.errors는 길이/체크섬/부분 timeout 오류의 합계입니다. UART ORE/DMA overrun 카운터가 아닙니다. `CMD/CMD_ACK/CMD_REJECT/CMD_TIMEOUT` value는 `(type << 8) | value`입니다. ACK는 명령 수락만 나타내며 CAL 완료는 이후 heartbeat로 판단합니다.

Uno는 부팅 문구, TEST_STARTED/TEST_DONE/TEST_ABORTED/BUSY_OR_HUB_NOT_NORMAL/LASER_ON/LASER_OFF/COMMAND_TOO_LONG, `pulse,<number>,<off_ms>` 등을 출력합니다. 현재 Hub 상태의 2bit 값을 주기적으로 출력하지 않습니다. ARMED와 DISARMED의 정상 출력이 같으므로 Uno 출력으로 세부 상태를 추정할 수 없습니다.

## 명령 실제 전제 조건

Hub는 ARM/DISARM/STATUS(STAT)/HELP(?)/CAL/MODE 0..2/LOAD 0..1을 해석합니다. Dashboard는 ARM/DISARM을 제공하지 않습니다.

- MODE/LOAD/CAL: Hub가 armed 또는 experiment이면 CMD_BUSY_OR_ARMED. Window pending이 있거나 CAL 시 Door pending이 있어도 거부합니다.
- Window MODE: trial이 열리지 않고 PB0가 low, adc_available, len=1, value<=2.
- Window LOAD: 같은 idle 조건, len=1, value<=1.
- Window CAL: 같은 idle 조건, adc_available && !acquisition_fault, len=0.
- Door CAL: hall_dma_fault가 아니면 수락하고 보정 시작.
- Hub는 최대 두 번 내부 frame 송신을 시도하고 CMD_TIMEOUT을 출력합니다. PC는 이에 추가 재시도를 하지 않습니다.

Window VCP의 TRACE/PLOT/PLOTOFF/TH는 Hub 명령과 별개입니다. Dashboard는 TH를 보내지 않습니다. Uno LASER/TEST/STOP/DEMO는 Dashboard에서 모두 차단합니다.

## 수정 없이 구현한 범위 / 추가 계측 제안

수정 없이 다중 PC 수집, 최신성·세션, 성능 차분 계산, 관측 누락/IRQ/계측 부담, 6조건 실험, PLOT/TRACE/TRIAL, Hub 상태/프레임 오류, 규칙 진단·로컬 LLM·제한 명령 검증까지 가능합니다.

아래는 발견한 **관측 한계 및 최소 추가 계측 제안**이며 원본은 수정하지 않았습니다.

| 현재 한계 | 결과 / 제안 |
|---|---|
| STAT 보고 시작/elapsed/sequence 없음 | 전환 생략/TX 로그 유실 시 dt 확정 불가. `report_seq,interval_ms,sampling_generation` 추가 제안 |
| lg_log/queue_tx 일부 호출은 실패를 버림 | STAT/TRIAL/이벤트 송신 누락을 PC가 완벽히 구분 못 함. 보드별 log_drops/tx_queue_full 누적값 제안 |
| UART RX는 CNDTR 위치 기반만 읽음 | 링 한 바퀴 이상 지연 유실을 절대 검출할 수 없음. wrap epoch/overrun/ORE/FE/NE/TE 계측을 별도 검증 후 추가 제안 |
| Window 일부 DMA 오류/early return은 cycles 합계 전에 종료 | 오류 구간 계측 부담은 경로 전체를 포함하지 않을 수 있음. 일관된 exit 계측 + 오류 원인 카운터 제안 |
| ready/fault는 복합 플래그 | 보정 중/배선/ADC 불가/취득 fault를 확정 구별 못 함. 명시적 fault reason과 calibration_left 제안 |
| STATUS에 pending/experiment/heartbeat age 없음 | PC 안전 조건 완전 판정 불가. armed/experiment/pending/node_seen/hb_age/실제 PB0를 읽기 전용으로 추가 제안 |
| command request ID 없음 | node/type/value/time으로만 매칭. 늦은 동일 ACK와 외부 동시 수동 명령을 완전히 구별 못 함. transaction ID 제안 |
| TRIAL은 hit만 보고 | 감지 latency/광학 pulse 실제 폭 미계측. PB0 onset과 beam onset sample index를 함께 기록하도록 제안 |
| acq_cycles는 지정 코드 경로만 포함 | 전체 CPU 점유율/전력/버스 이용률로 일반화 금지. idle 계측 또는 DWT task/IRQ별 계측 필요 |
| INIT/TIM4 reset이 로그 없이 빠르게 지나갈 수 있음 | 관측되지 않은 모드 왕복/동일 ms 리셋 완전 감지 불가. boot ID/config generation 추가 제안 |

현재 센서 fault에서 CAL이 거부되는 경우가 있고 Door DMA fault에는 원본 코드상 회복 명령이 없습니다. MODE 2만으로 모든 DMA 오류나 문 노드 문제를 복구할 수 있다고 표시하지 않습니다.

## 보존 파일 SHA-256

검증 기준 해시(줄끝 포함 원본 바이트):

```text
4442912c727604ba75d4a5faeb952bad51b599f7fbfc62edafda8ced8bd94f8c  STM1번 코드.txt
15e4d9c1014aaea524eaaf67bdfa71ec79017a88dff7021b7285de684929cbff  STM2번 코드.txt
c8683582693c803aa23331f915e54e58e66f1a821f7719767e841b0be1296818  STM3번코드.txt
02278c8ef518675bfd6ab1a49f9fe957afcf4fb06a444bfd6f7a8a4026e4b70a  플잭2우노 4번 코드.txt
4a77ef4adcb8c3615d9f706b393df40c9847e0a2b991ba1a742242a177b3e3dc  laser_guard.c
5961730f06011f778a5901dc14f7996570798b9a6224d3ae3ad4c00aa0911132  laser_guard.h
```
