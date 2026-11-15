# Project 2 — 임시 다중 보드 통신 검증

학생 C의 중앙 허브 개발용 스모크 테스트다. **Uno 3대 + NUCLEO-F103RB 1대**로
UART DMA 수신·파싱·상태 판정·노드 통신 끊김·2비트 경보 출력을 검증하도록 구성했다.
현재 센서 이벤트와 ADC 값은 모두 **시뮬레이션 데이터**다.
실제 센서 수집, ADC DMA, 성능 비교, LLM, KV Cache는 구현하지 않았다.

**HARDWARE NOT TESTED — T1~T10 모두 실제 보드 미수행.**
호스트에서 실제 공통 C 코드를 빌드한 테스트 23개 및 ASan/UBSan 퍼즈 검사를 통과했다.
ARM GCC/arduino-cli 부재로 보드 펌웨어 빌드와 업로드도 검증하지 못했다.
환경·실행 결과는 [검증 기록](docs/verification.md), 실제 수행 절차는 [시험 계획](docs/test_plan.md)에 있다.

## 저장소 확인과 작업 범위

작업 시작 시 `/home/songsong/Emb-2`에는 내용이 없는 읽기 전용 `.git/.agents/.codex/.aws`
디렉터리만 있었다. `git status`는 `not a git repository`였고 소스·v3/v4·보드 설정·
Makefile·ioc·AGENTS.md를 확인할 수 없었다. 따라서 기존 코드와의 호환성을 확인했다고
주장하지 않는다. 기존 디렉터리는 변경하지 않았다.

새 파일은 모두 `project2_comm_test/` 아래에 있다. 이 디렉터리 자체를 독립 Git 저장소로
초기화하고 `feature/comm-smoke-test` 브랜치를 만들었다. 상위 저장소의 브랜치를 바꾼 것은 아니다.

```bash
cd /home/songsong/Emb-2/project2_comm_test
git status --short --branch
git log -1 --oneline
git show --stat HEAD
```

나중에 원래 저장소에 통합할 때는 여기의 `.git`, `build/`, `.venv/`, `__pycache__/`를
제외하고 `project2_comm_test/`로 복사한 뒤 원래 저장소에서 같은 feature 브랜치로 커밋한다.

## 구조와 보드 역할

| 경로 | 내용 |
|---|---|
| `stm32_hub/src/main.c` | 수신/상태 갱신 루프, PC 명령·로그·2초 상태 출력 |
| `stm32_hub/src/platform.c` | CMSIS 레지스터 기반 GPIO·UART·RX DMA·IRQ·비차단 PC 큐 |
| `stm32_hub/src/system.c` | HSI 8MHz SystemInit, SystemCoreClock |
| `stm32_hub/src/hub.c`, `include/hub.h` | 하드웨어와 독립된 상태 판정 |
| `stm32_hub/src/dma_stream.c`, `include/dma_stream.h` | 누적 producer 위치 → 링 바이트 → 파서 |
| `stm32_hub/include/board_pins.h` | PA6/PB6 상태 핀, baud·버퍼·로그 간격 설정 |
| `stm32_hub/include/platform.h` | 보드 계층 인터페이스 |
| `stm32_hub/Makefile`, `STM32F103RB.ld` | GCC 빌드, Flash 128KiB/RAM 20KiB, 최소 스택 4KiB |
| `arduino_window_sim/arduino_window_sim.ino` | ID 01, 가상 창문 노드 |
| `arduino_door_sim/arduino_door_sim.ino` | ID 02, 가상 문 노드 |
| `arduino_alarm_sim/arduino_alarm_sim.ino` | D2/D3 입력, USB 상태·D13 LED 출력 |
| `common/CommSmoke/src/comm_protocol.h` | 공통 자료형·schema·LE 변환·프레임 인코더 |
| `common/CommSmoke/src/node_sim.h`, `library.properties` | 두 Uno의 공통 명령·HEARTBEAT 송신 코드 |
| `common/parser.c`, `parser.h` | 부분/연속/손상 프레임 스트림 파서 |
| `tools/monitor.py`, `requirements.txt` | pyserial PC 모니터, 저장·재생 |
| `tests/host_bridge.c`, `core_test.c` | 실제 C 테스트 ABI, sanitizer 퍼즈 테스트 |
| `tests/test_comm.py`, `test_monitor.py` | 프레임·상태·DMA 링 모형·가상 터미널 검사 |
| `docs/` | 배선, 프로토콜, 시험 계획, 검증 기록 |
| `Makefile`, `.gitignore`, `README.md` | 호스트/보드 빌드 진입점과 안내 |

[정확한 배선표·분압기](docs/wiring.md)를 먼저 읽는다.
Uno #1 D11 → **분압** → PA10/USART1 RX, Uno #2 D11 → **분압** → PB11/USART3 RX.
STM32 PA6/bit0 → Uno #3 D2, PB6/bit1 → D3. PC는 ST-LINK USB/USART2 PA2·PA3.
모든 GND를 공통 연결하며, 독립 USB 전원의 **5V 선끼리는 연결하지 않는다**.
Uno #1/#2 D10은 RX 예약·미연결이다. Uno #3 D2/D3에 각각 10kΩ pull-down을 사용한다.

## 도구 확인과 호스트 테스트

Ubuntu에서 필요 도구를 먼저 확인한다. 아래 설치 명령은 안내이며 이번 작업에서 실행하지 않았다.

```bash
command -v gcc make python3 arm-none-eabi-gcc arduino-cli
python3 -c "import serial; print(serial.__version__)"
make test
```

호스트에는 GCC와 Python 3만으로 C/Python 핵심 테스트를 실행할 수 있다.
pyserial이 없으면 모니터 PTY 테스트 1개는 skip된다. 전체 실행을 위해 필요한 경우:

```bash
sudo apt update
sudo apt install build-essential python3-venv
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r tools/requirements.txt
make test
```

C 테스트는 `-Wall -Wextra -Werror -pedantic`과 AddressSanitizer/UndefinedBehaviorSanitizer를
사용한다. 현재 환경은 ptrace 때문에 LeakSanitizer 실행이 불가능하여 Makefile에서
`ASAN_OPTIONS=detect_leaks=0`을 지정했다. 동적 할당을 사용하지 않는 공통 C의
메모리 접근·정수/포인터 UB 검사는 켜져 있다. Python은 공유 라이브러리의 **동일 C 구현**을 호출한다.

## STM32 빌드·업로드

현재 `arm-none-eabi-gcc`와 STM32CubeF1 패키지는 이 작업 폴더에서 제공되지 않는다.
GCC, newlib, CMSIS core/device 헤더 및 ST 공식 startup 어셈블리가 필요하다.
HAL UART API나 HAL 소스는 사용하지 않는다.

필요할 경우 Ubuntu ARM GCC 설치:

```bash
sudo apt install gcc-arm-none-eabi libnewlib-arm-none-eabi
```

STM32CubeIDE의 MCU package manager로 STM32CubeF1 패키지를 설치하거나,
[ST STM32CubeF1](https://github.com/STMicroelectronics/STM32CubeF1)을 submodule 포함 확보한다.
예시 명령(네트워크 연결 필요):

```bash
git clone --recursive https://github.com/STMicroelectronics/STM32CubeF1.git /tmp/project2-STM32CubeF1
make -C stm32_hub CUBE_F1=/tmp/project2-STM32CubeF1 NODE_BAUD=38400
# 패키지가 이미 설치되어 있다면 실제 패키지 루트로 지정:
make -C stm32_hub CUBE_F1="$HOME/STM32Cube/Repository/STM32Cube_FW_F1_V1.8.6"
```

`CUBE_F1/Drivers/CMSIS/Include/core_cm3.h`,
`Drivers/CMSIS/Device/ST/STM32F1xx/Include/stm32f1xx.h`,
`Source/Templates/gcc/startup_stm32f103xb.s`가 존재해야 한다(마지막 경로는 device 디렉터리 기준).
버전 문자열은 예시이며 설치된 경로를 지정한다. 보드별 빌드 결과는
`stm32_hub/build/38400/hub.{elf,bin,map}`에 생성된다.

업로드 도구도 설치되어 있다고 가정하지 않는다. STM32CubeIDE의 ST-LINK 디버그 실행 또는
별도 [STM32CubeProgrammer](https://www.st.com/en/development-tools/stm32cubeprog.html)를 설치하여:

```bash
STM32_Programmer_CLI -c port=SWD -w stm32_hub/build/38400/hub.elf -v -rst
```

NUCLEO의 ST-LINK USB를 연결하고 BOOT0은 기본 LOW를 유지한다. 프로그래머 실행 파일이
PATH에 없다면 설치 위치의 절대 경로를 쓴다. 이 명령의 실행·검증은 아직 하지 않았다.

STM32CubeIDE에서는 두 가지 방식으로 구성할 수 있다(IDE 가져오기 미검증):

1. Existing Code as Makefile Project로 `stm32_hub/`를 가져오고, IDE 번들의 ARM GCC bin을
   PATH에 추가하여 build command를 `make CUBE_F1=<실제 패키지 경로>`로 설정한다.
2. STM32F103RBTx/NUCLEO-F103RB의 빈 C 프로젝트를 만든 뒤 이 소스를 linked source로 추가한다.
   `src/*.c`와 `../common/parser.c`, include 경로 `include`, `../common`,
   `../common/CommSmoke/src`, CMSIS core/device include를 사용하고 `STM32F103xB`를 정의한다.
   GCC startup은 공식 `startup_stm32f103xb.s` 하나만 사용하고 여기의 linker script를 선택한다.
   자동 생성 main.c, system_stm32f1xx.c, stm32f1xx_it.c는 빌드에서 제외하여
   main/SystemInit/SysTick/USART2/DMA IRQ 중복을 없앤다. HAL_Init/SystemClock_Config 호출을
   추가하지 않는다. nano/nosys specs를 사용하며 HSI 8MHz 설정을 유지한다.

## Uno 빌드·업로드

현재 `arduino-cli`와 AVR core가 없다. 먼저
[공식 설치 안내](https://arduino.github.io/arduino-cli/latest/installation/)에 따라 CLI를 설치하고
PATH를 설정한다. Arduino IDE의 Uno 지원이 있다고 CLI에도 설치되어 있다고 가정하지 않는다.

```bash
arduino-cli core update-index
arduino-cli core install arduino:avr
arduino-cli board list
make arduino

# 실제 각 포트로 변경하고 보드별로 업로드한다.
arduino-cli upload -p /dev/ttyACM1 --fqbn arduino:avr:uno arduino_window_sim
arduino-cli upload -p /dev/ttyACM2 --fqbn arduino:avr:uno arduino_door_sim
arduino-cli upload -p /dev/ttyACM3 --fqbn arduino:avr:uno arduino_alarm_sim
arduino-cli monitor -p /dev/ttyACM1 --config baudrate=9600
```

세 콘솔 모두 **9600bps, newline**이다. PC↔STM32만 115200bps다. Uno #1/#2는
`SoftwareSerial(10,11)`로 38400bps TX를 사용하며 RX listen은 끈다.
USB 콘솔 손실을 줄이기 위해 9600bps로 설정했다. SoftwareSerial TX가 인터럽트를 잠시
차단하므로 과도한 콘솔 입력은 피하고 실제 200ms HEARTBEAT 간격·지터를 확인한다.
각 노드의 HEARTBEAT seq와 문 열림 상태는 RAM에서 유지하며 재부팅 시 초기화된다.

| 보드 | 소문자 명령 |
|---|---|
| Uno #1 | `beam 1`, `beam 2`, `beam 5`, `sound 300`, `pause`, `resume`, `badcrc`, `help` |
| Uno #2 | `door open`, `door close`, `shock 3`, `pause`, `resume`, `badcrc`, `help` |
| Uno #1/#2 공통 | `burst 1..100`: T9용 10ms 간격 추가 HEARTBEAT |
| Uno #3 | 입력 명령 없음, 상태 변화만 출력 |

`pause`는 HEARTBEAT와 burst를 멈추고 수동 가상 이벤트 명령은 허용한다.
`resume`은 즉시 정상 HEARTBEAT를 보내며 이후 200ms 주기를 재개한다.
`badcrc`는 잘못된 XOR HEARTBEAT 한 개만 보낸다.
BEAM 입력 범위는 1..6553ms, sound 0..65535, shock 1..255다.

19200 검증 옵션(양쪽 재빌드·재업로드 필수):

```bash
make -C stm32_hub CUBE_F1=/실제/STM32CubeF1 NODE_BAUD=19200
arduino-cli compile --fqbn arduino:avr:uno --libraries "$PWD/common" \
  --build-property 'compiler.cpp.extra_flags=-DNODE_BAUD=19200UL' arduino_window_sim
arduino-cli compile --fqbn arduino:avr:uno --libraries "$PWD/common" \
  --build-property 'compiler.cpp.extra_flags=-DNODE_BAUD=19200UL' arduino_door_sim
# 위와 동일한 upload 명령으로 두 Uno를 업로드하고, STM32는 build/19200/hub.elf 사용
```

## UART와 DMA 구성

| 주변장치 | 핀 | 속도 | 수신 방식 |
|---|---|---|---|
| USART1 | PA10 RX | 38400, 대안 19200 | DMA1 Channel 5, 독립 512-byte circular |
| USART3 | PB11 RX | 38400, 대안 19200 | DMA1 Channel 3, 독립 512-byte circular |
| USART2 | PA2 TX / PA3 RX | 115200 | RXNE IRQ → 128-byte PC 명령 큐, TXE 비차단 폴링 |

[RM0008 §13.3.7 및 USART 절](https://www.st.com/resource/en/reference_manual/rm0008-stm32f101xx-stm32f102xx-stm32f103xx-stm32f105xx-and-stm32f107xx-advanced-arm-based-32-bit-mcus-stmicroelectronics.pdf)을
기준으로 DMA 매핑·레지스터를 확인했다. RCC DMA1/A GPIO/B GPIO/C GPIO/AFIO/USART 클럭을
켜고 USART remap을 해제한다. RX는 pull-up input, PC TX는 AF push-pull,
상태선은 2MHz GPIO push-pull이다. 핀 설정은 `board_pins.h` 한곳에서 변경한다.
상태 핀은 GPIOA/B/C로 변경 가능하며 UART 핀 변경에는 AFIO remap 설정도 맞춰야 한다.

HSI=SYSCLK=HCLK=PCLK1=PCLK2=8MHz, PLL 미사용. SysTick reload=7999로 1ms다.
USART BRR=`round(PCLK/baud)`:

| baud | BRR | 실제 nominal baud (HSI 자체 오차 제외) |
|---|---|---|
| 38400 | 208 = 0x00D0 | 38461.5 (+0.16%) |
| 19200 | 417 = 0x01A1 | 19184.7 (-0.08%) |
| 115200 | 69 = 0x0045 | 115942.0 (+0.64%) |

DMA CPAR는 해당 USART DR, CMAR는 각 링, CNDTR=512,
DIR=0/PINC=0/MINC=1/PSIZE=MSIZE=8bit/CIRC=1/MEM2MEM=0, high priority다.
DMA TC IRQ는 wrap epoch를 증가시키고 TE IRQ는 오류를 센다.
메인 루프에서 IRQ와 경합하지 않도록 짧은 critical section으로 epoch/CNDTR을 읽어
`producer = epoch*512 + (512-CNDTR)`를 계산한다. transient CNDTR=0은 다음 루프에 다시 읽는다.
`dma_stream_drain`이 이전 tail부터 새 위치까지 바이트를 전달한다. 정확히 한 바퀴 수신도
0바이트로 오인하지 않는다. 32bit producer/시간 wrap은 unsigned 차이로 처리한다.

512바이트를 초과하여 밀리면 overrun을 세고 해당 backlog 전체를 discarded로 폐기한 뒤
파서를 재동기화한다. 또한 폴링이 링 한 바퀴 시간(38400에서 약 133ms, 19200에서 약 267ms)
이상 지연되면 불확실한 backlog를 보수적으로 폐기한다. 로그 출력은 이 시간을 막지 않도록
대기 없이 큐에 넣고 전송한다. 외부에서 장시간 IRQ를 막으면 sticky TC로 여러 바퀴를
정확히 셀 수 없으므로 그 상황에서 dma_bytes는 하한이며 무손실 수신을 보장하지 않는다.
UART ORE/FE/NE/PE 또는 DMA TE는 카운터를 증가시키고 채널·부분 프레임을 재시작한다.

USART1/3 IDLE IRQ는 사용하지 않는다. 지속적인 CNDTR 폴링+TC IRQ로 길이가 짧거나
연속인 프레임을 처리하며, 정상 수신 중 IDLE clear를 위한 DR 읽기로 DMA 바이트를
가져가는 경합을 피한다. DMA와 프로토콜, 상태 로직은 독립 모듈이다.

USART2 로그는 4096-byte 큐와 단일 메인 루프 TX 소유자를 사용한다. TX DMA는 구현하지
않았다. TXE를 기다리지 않고 루프마다 가능한 바이트만 보낸다. 큐가 가득 차면 한 줄 전체를
폐기하고 log_drops를 센다. 실제 스트림 최대 부하·IRQ 타이밍·오류 복구는 보드 미검증이다.

## 상태 규칙과 기본 가정

초기 DISARMED, 노드 미접속 유예 1000ms다. 이미 유효 HEARTBEAT를 한 번 받았다면
유예 중이라도 마지막 HEARTBEAT부터 **600ms 이상**이면 장애다. 센서 프레임은
HEARTBEAT 시각을 갱신하지 않는다. 양 노드 모두 정상 HEARTBEAT를 받으면 장애가 해제된다.

우선순위는 **ALARM latch > FAULT > SUSPECT > ARMED/DISARMED**다.
FAULT는 DISARMED에서도 표시한다. ALARM 중에도 노드별 FAULT와 링크 이벤트를 기록하며,
DISARM으로 latch를 해제해도 링크가 끊겼으면 출력은 FAULT다.

- DISARMED: 센서 이벤트를 기록한다. DOOR의 마지막 상태는 기억하지만 침입 타이머/조합은 시작하지 않는다.
- ARM: 이미 문이 열렸으면 ARM 시점부터 SUSPECT/10초 유예. ARM 반복으로 타이머를 연장하지 않는다.
- BEAM_BREAK: ARMED 의도 플래그가 켜져 있으면 즉시 ALARM. FAULT/SUSPECT 중에도 적용한다.
- DOOR OPEN: SUSPECT, 처음 OPEN부터 10초가 지나도 close 또는 DISARM이 없으면 ALARM.
  반복 OPEN은 시간을 연장하지 않고 CLOSE는 문 타이머만 해제한다.
- SHOCK: SUSPECT, 처음 SHOCK부터 5초 뒤 해제한다. 반복 SHOCK은 5초를 연장하지 않는다.
  문 타이머가 남아 있으면 SUSPECT를 유지한다.
- SHOCK와 SOUND: 순서에 관계없이 최근 두 이벤트 수신 간격 **500ms 이하**이면 ALARM.
  크기 임계값은 이 단계에서 적용하지 않는다. DISARM/새 ARM에서 조합 이력을 지운다.
- ALARM: 문이 닫히거나 통신이 회복되어도 유지하며 DISARM만 해제한다.

시간은 허브가 파싱한 ms 기준이며 센서 발생 시각이나 실제 ADC 측정 시각이 아니다.
두 노드의 USB/보드 부팅 순서는 임의다. 문 노드는 부팅 시 닫힘을 기본값으로 삼으며
실제 위치를 측정하지 않는다. 최종 센서 노드는 부팅 시 실제 DOOR 상태 이벤트를 전송해야 한다.

## PC 실행과 로그

```bash
python3 -m serial.tools.list_ports
python3 tools/monitor.py --port /dev/serial/by-id/실제-ST-LINK-ID --log session.log
# 콘솔에서 ARM, DISARM, STATUS, HELP 입력 (대소문자 허용, 줄끝 필요)
python3 tools/monitor.py --replay session.log
```

동일 포트를 다른 Serial Monitor와 동시에 열지 않는다. 권한이 없으면 현재 사용자에게
Ubuntu dialout 그룹 권한을 부여하고 다시 로그인하는 등 로컬 정책에 맞게 설정한다.
정기 STATUS 간격은 `board_pins.h`의 `STATUS_PERIOD_MS=2000`이다. HEARTBEAT마다
로그를 찍지 않고 STATUS에 누적값을 표시한다. 이벤트/상태/링크 변화는 즉시 큐에 넣는다.

- `t`: 허브 부팅 후 ms, `node`: 1/2/3, `state`, `reason`, `gpio`: 0..3.
- `seen`, `last_hb_ms`, `hb_age_ms`, `fault`, `seq`, `health`, `seq_gaps`.
  seen=0일 때 last_hb_ms/age의 0은 미수신 표시이다.
- `dma_bytes`: DMA에서 관측한 누적 수신량(거부된 프레임/잡음/관측된 폐기량 포함), `frames`: 유효 프레임 수.
- `crc_errors`: XOR 불일치, `invalid`: 잘못된 schema/길이/ID/부분 타임아웃.
- `partial_timeouts`, `overruns`, `discarded`, `uart_errors`, `dma_errors`.
- 메시지별 수신 횟수 `hb/beam/sound/door/shock`, `log_drops`, `pc_rx_drops`.
- `LINK_LOST`, `LINK_RECOVERED`, `SIM_EVENT`, `PAYLOAD`, `STATE` 이벤트.

`beam 5` 후 기대 로그의 예(실측 결과 아님):

```text
t=1200 node=1 event=STATE state=ALARM reason=beam_break_simulated gpio=2
t=1200 node=1 event=PAYLOAD simulated=1 type=BEAM_BREAK duration_0p1ms=50 min_adc=100
```

프레임 바이트 예시는 [프로토콜](docs/protocol.md)에 있고, C 인코더로 동일 값을 검증한다.

## 최종 3 STM32 + 1 Uno로 교체할 때

`common/CommSmoke/src/comm_protocol.h`, `common/parser.*`, 허브의 `hub_receive` 인터페이스,
ID/종류/LE 규격과 Arduino #3 경보 스케치는 유지한다.
`arduino_window_sim/`, `arduino_door_sim/` 및 공통 `node_sim.h`를 실제 STM32 센서 노드의
새 펌웨어로 대체한다. 새 송신부는 `comm_frame_t`를 만들고 `comm_encode` 결과를 UART TX로
전달한다. TX DMA를 추가할 때 해당 버퍼는 전송 완료까지 재사용하지 않는다.

센서 수집/ADC scan DMA/EXTI는 새 노드 모듈에서 값을 생산하고, 프레임 전송부와 분리한다.
실제 3.3V STM32 TX로 바뀌면 Uno용 분압기를 제거하고 배선 문서를 갱신한다.
허브 RX 핀이 유지되면 platform.c는 교체할 필요가 없다. 센서 데이터가 실제 값이 되면
`stm32_hub/src/main.c`와 `src/hub.c`의 SIMULATED 로그 표기만 적절히 변경한다.
PC 프로토콜과 보안 상태 규칙은 그대로 사용할 수 있다.
Polling/IRQ/DMA 비교·신뢰성 평가·LLM 진단은 이후 별도 모듈/실험으로 추가하며 현재 구현에 포함하지 않는다.
