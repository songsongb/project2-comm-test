# 검증 기록 / 2026-11-15

## 작업 환경과 저장소

- 작업 디렉터리: `/home/songsong/Emb-2`.
- 시작 시 상위 `.git`은 내용이 없는 read-only 디렉터리였다.
  `git status --short --branch`와 `git log -3 --oneline`은 `not a git repository`로 실패했다.
- `rg --files`와 디렉터리 조사에서 기존 소스, Makefile, ioc, linker script, AGENTS.md를 찾지 못했다.
  기존 ADC DMA/LLM v3/v4를 검사할 수 없었으며 해당 파일을 수정하지 않았다.
- 독립 저장소 생성: `git -C project2_comm_test init -b feature/comm-smoke-test`.
  상위 저장소의 이력에 연결된 브랜치가 아니다.
- GCC: Ubuntu 11.4.0. Python: 3.10.12. pyserial: 3.5. make 사용 가능.
- `command -v arm-none-eabi-gcc`, `command -v arduino-cli`, `command -v avr-g++` 결과 없음.
  일반 `/opt/st/stm32cubeide_*`, `/opt/gcc-arm*`, `~/STM32Cube/Repository/*`,
  `~/.arduino15/packages/arduino/hardware/avr/*` 경로도 없었다.
- `/dev/ttyACM*`, `/dev/ttyUSB*` 장치 없음. 하드웨어 통신이나 업로드를 수행하지 않았다.

## 실제 실행한 명령과 결과

작업 폴더 `/home/songsong/Emb-2`에서 실행:

```bash
make -C project2_comm_test test
python3 -m py_compile project2_comm_test/tools/monitor.py project2_comm_test/tests/test_comm.py project2_comm_test/tests/test_monitor.py
make -C project2_comm_test stm32
make -C project2_comm_test arduino
```

| 명령/검사 | 실제 결과 |
|---|---|
| `make ... test`의 C 실행 파일 빌드 | GCC C11, Wall/Wextra/Werror/pedantic, ASan/UBSan 빌드 성공 |
| C 실행 파일 | PASS: 정확한 인코딩 벡터, 1,000,000-byte 파서 fuzz, 100,000개 상태 이벤트 불변조건 |
| C 공유 라이브러리 빌드 | 실제 encoder/parser/hub/dma_stream C 코드 빌드 성공 |
| Python unittest | **23 tests, OK, skipped=0** |
| py_compile | 성공 |
| `make ... stm32` | 실패: `Missing ARM GCC: install gcc-arm-none-eabi and libnewlib-arm-none-eabi` (Make exit 2) |
| `make ... arduino` | 실패: 첫 window compile에서 `arduino-cli: not found` (Make exit 2, 하위 command 127) |

첫 C 실행은 LeakSanitizer가 ptrace 환경에서 동작하지 않아 실패했다.
Makefile에 `ASAN_OPTIONS=detect_leaks=0`을 적용한 이후 메모리 접근·UB 검사는 통과했다.
누수 검사를 통과했다고 주장하지 않는다. 이후 생산 코드 변경 후 최종 전체 테스트도 23개 통과했다.

Python 테스트는 중복 Python 상태 모형을 구현하지 않는다. ctypes ABI를 통해 펌웨어에 사용하는
공통 C를 직접 실행한다. DMA 테스트에서는 생산 `dma_stream_drain`에 가상 링과 누적 producer를
전달한다. 실제 `platform.c`의 CNDTR snapshot/TC IRQ는 실행하지 않는다.
모니터 테스트는 실제 pyserial과 Linux PTY를 연결하여 STATUS 송신과 분할 로그 수신·저장을 확인했다.
이는 STM32 VCP를 연결한 결과가 아니다.

호스트 검증 항목:

- T1 두 독립 스트림의 200ms HEARTBEAT와 마지막 수신 시각.
- T2 BEAM 경보 latch 및 DISARM 해제, DISARMED 이벤트 무경보.
- T3 DOOR SUSPECT → 10초 ALARM, CLOSE 해제, 반복 OPEN/ARM 타이머 연장 방지.
- T4 SHOCK 단독 5초 복귀, 반복 SHOCK 타이머 연장 방지, 문 타이머와 동시 존재.
- T5 두 순서의 조합, timestamp=0, 500/501ms 경계, 재무장 시 과거 이력 제거.
- T6/T7 각 노드 정확히 600ms timeout, 링크 소실/복구 기록, 기동 1000ms 유예.
- T8 bad XOR 거부 후 다음 정상 프레임 수신, bad frame이 HEARTBEAT를 갱신하지 않음.
- T9 포트별 2000개 연속 HB, 임의 chunk, 512-byte 링 wrap/한 바퀴/초과/복구/u32 wrap.
- T10 내부 상태 → GPIO 코드 매핑 **계산만** 검증.
- 잘못된 schema/ID/수신 포트/DOOR bool, 부분 프레임 전 분할 지점, payload AA, 부분 timeout,
  손상 길이 뒤 동기 복구, sequence/time wrap, FAULT/ALARM 우선순위.
- PC 모니터 명령 검증, 저장 로그 재생, PTY 기반 pyserial 송수신.

## 미검증 범위

**T1~T10 전부 HARDWARE NOT TESTED.**
STM32/AVR 목표 아키텍처 빌드, CubeIDE import, Flash/RAM 최종 map, 업로드, 실제 HSI/baud,
SoftwareSerial 주기·지터, DMA CNDTR/IRQ 경합, UART 오류 복구와 최대 연속 부하,
ST-LINK VCP, 분압 전압, 상태선/LED는 아직 검증하지 않았다.
도구 설치·보드 빌드·업로드 명령은 README에 안내했다. 보드 성공 결과나 성능 수치는 제시하지 않는다.

레지스터/커넥터 확인 근거:
[ST RM0008 §13.3.7 DMA1 mapping 및 GPIO/USART 절](https://www.st.com/resource/en/reference_manual/rm0008-stm32f101xx-stm32f102xx-stm32f103xx-stm32f105xx-and-stm32f107xx-advanced-arm-based-32-bit-mcus-stmicroelectronics.pdf),
[ST UM1724 Rev 17 §7.8, Tables 12/27](https://www.st.com/resource/en/user_manual/um1724-stm32-nucleo64-boards-mb1136-stmicroelectronics.pdf),
[ST CMSIS STM32F103xB 헤더](https://github.com/STMicroelectronics/cmsis-device-f1/blob/master/Include/stm32f103xb.h).
문서상 매핑 검증은 하드웨어 동작 검증과 구별한다.

## 생성 파일 전체 목록

아래는 독립 저장소 기준 상대 경로다. 기존 파일 수정·삭제 없이 모두 새로 생성했다.
`.git` 메타데이터와 ignored 빌드 산출물은 제외한다.

```text
.gitignore
Makefile
README.md
arduino_alarm_sim/arduino_alarm_sim.ino
arduino_door_sim/arduino_door_sim.ino
arduino_window_sim/arduino_window_sim.ino
common/CommSmoke/library.properties
common/CommSmoke/src/comm_protocol.h
common/CommSmoke/src/node_sim.h
common/parser.c
common/parser.h
docs/protocol.md
docs/test_plan.md
docs/verification.md
docs/wiring.md
stm32_hub/Makefile
stm32_hub/STM32F103RB.ld
stm32_hub/include/board_pins.h
stm32_hub/include/dma_stream.h
stm32_hub/include/hub.h
stm32_hub/include/platform.h
stm32_hub/src/dma_stream.c
stm32_hub/src/hub.c
stm32_hub/src/main.c
stm32_hub/src/platform.c
stm32_hub/src/system.c
tests/core_test.c
tests/host_bridge.c
tests/test_comm.py
tests/test_monitor.py
tools/monitor.py
tools/requirements.txt
```
