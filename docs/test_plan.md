# 통신 스모크 테스트

**T1~T10: HARDWARE NOT TESTED.** 아래는 수행 절차와 통과 기준이며 실제 성공 기록이 아니다.
호스트에서 같은 C 로직을 실행한 결과는 `verification.md`에 별도로 기록한다.

공통 준비: 배선 확인 → 모든 보드 업로드/전원 ON → Uno 콘솔 9600bps, newline →
STM32 PC 모니터 115200bps. 두 노드에서 `resume`, 문 노드에서 `door close`,
PC에서 `DISARM` 후 `STATUS`를 실행한다. fault=0, log_drops=0을 확인한다.
각 테스트 전에 이 절차로 초기 상태를 복원한다. 카운터는 부팅 후 누적값이므로 전후 차이를 비교한다.

| 시험 | 독립 실행 절차 | 통과 기준 | 실제 결과 |
|---|---|---|---|
| T1 | DISARM 상태에서 양 노드 resume, 10초간 STATUS 관찰 | USART1/3 각각 HB 약 50개 증가, last_hb_ms 갱신, age 통상 200ms 이하, 오류/오버런 없음 | HARDWARE NOT TESTED |
| T2 | ARM → 창문 `beam 5` → STATUS → DISARM | ALARM, reason=beam_break_simulated, gpio=2; 시간이 지나도 유지; DISARM 시 해제 | HARDWARE NOT TESTED |
| T3 | ARM → 문 `door open` | 즉시 SUSPECT/gpio=1; 닫지 않고 10초면 ALARM. 별도 재시험에서 10초 이전 `door close` 시 ARMED | HARDWARE NOT TESTED |
| T4 | ARM → 문 `shock 3`, sound/door 이벤트 없음 | SUSPECT 후 첫 shock 약 5초에 ARMED/gpio=0 | HARDWARE NOT TESTED |
| T5 | ARM → 문 `shock 3`와 창문 `sound 300`을 500ms 이내에 입력 | ALARM, reason=shock_sound_500ms. 반대 순서도 확인 | HARDWARE NOT TESTED |
| T6 | ARM → 창문 `pause`, 문은 송신 유지 → 창문 `resume` | 창문 last_hb_ms부터 600ms 이상에서 LINK_LOST/node=1, FAULT/gpio=3; resume 후 LINK_RECOVERED 및 ARMED | HARDWARE NOT TESTED |
| T7 | ARM → 문 `pause`, 창문은 송신 유지 → 문 `resume` | T6와 동일하되 node=2 | HARDWARE NOT TESTED |
| T8 | 양 노드 각각 `badcrc` 한 번, 그 뒤 정상 HB 관찰 | 해당 crc_errors가 1 증가, bad frame은 frames에 미포함, 다음 정상 frames/HB는 계속 증가 | HARDWARE NOT TESTED |
| T9 | 두 노드 각각 `burst 100` (10ms 간격 HB), 동시에 기본 HB도 유지 | 기본 HB 외 추가 100개씩 증가, seq_gaps/CRC/invalid/overruns/discarded 증가 없음 | HARDWARE NOT TESTED |
| T10 | T1/T4/T2/T6 순으로 NORMAL/SUSPECT/ALARM/FAULT 생성, 각 단계 DISARM 등으로 초기화 | STM32 gpio 값 0/1/2/3과 Uno #3의 00/01/10/11, LED 꺼짐/1Hz/켜짐/4Hz 일치 | HARDWARE NOT TESTED |

T5는 사람이 두 터미널에 입력하면 500ms를 넘기기 쉽다. 필요 시 아래 PC 예제로
두 Uno USB 포트를 열고 자동 리셋 후 2초 이상 기다린 다음 실행한다. STM32는 별도로 ARM한다.
포트는 실제 `/dev/serial/by-id/...`로 바꾼다. 자동 리셋 중 FAULT가 발생해도 두 노드의
HEARTBEAT가 재개되어 fault=0인지 확인한 뒤 ARM한다.

```python
import serial, time
window = serial.Serial('/dev/ttyACM1', 9600, timeout=0.1)
door = serial.Serial('/dev/ttyACM2', 9600, timeout=0.1)
time.sleep(2)
door.write(b'door close\n')
time.sleep(0.3)  # 이 시점 뒤 STM32 ARM이 완료되어야 함
# STM32 모니터에서 ARM을 완료한 뒤 다음 두 줄 실행:
door.write(b'shock 3\n'); door.flush()
time.sleep(0.1)
window.write(b'sound 300\n'); window.flush()
window.close(); door.close()
```

타임아웃 시각은 `pause`를 입력한 시각이 아니라 **마지막 유효 HEARTBEAT** 기준이다.
예: last_hb_ms=1200이면 LINK_LOST t≈1800. 주기 STATUS는 2초마다 나오지만
LINK_LOST/RECOVERED 및 상태 전이는 즉시 로그 큐에 넣는다. UART 출력 지연은 있을 수 있다.
ALARM 중에는 PA6/PB6가 ALARM을 유지하므로 T6/T7 전에 반드시 DISARM 후 ARM한다.
FAULT 회복은 정상 HEARTBEAT가 와야 가능하며 센서 이벤트만으로 회복하지 않는다.

38400에서 T1/T8/T9가 불안정하면 양 Uno와 STM32를 모두 19200으로 다시 빌드하여
동일 시험을 반복하고 baud/보드 revision/배선 길이/오류 전후 수치를 함께 기록한다.
HSI 오차, SoftwareSerial 지터, 레벨/접지/USB 콘솔 영향은 실제 보드에서 확인해야 한다.

호스트 개별 실행(먼저 프로젝트 루트에서 `make build/libcommtest.so`):

```bash
PYTHONPATH=tests python3 -m unittest test_comm.CommunicationTests.test_T2_beam_alarm_latched_until_disarm -v
PYTHONPATH=tests python3 -m unittest test_comm.CommunicationTests.test_T6_T7_timeout_exact_boundary_and_recovery -v
PYTHONPATH=tests python3 -m unittest test_comm.CommunicationTests.test_T9_dma_bursts_wraps_two_ports_random_chunks -v
```

전체: `make test`. T1~T10에 대응하는 C 로직 외에 모든 분할 지점, 잘못된 schema/ID/port,
손상 길이 뒤 복구, 500/501ms 경계, 5/10초 경계, 반복 ARM/DOOR의 타이머 연장 방지,
기동 유예, FAULT/ALARM 우선순위, u32 시간/위치 wrap, DMA 모형의 정확히 한 바퀴 및
오버런 이후 복구, seq wrap, 모니터 PTY 송수신을 검증한다.
실제 DMA 레지스터/IRQ 타이밍·핀 전압·USART baud·보드 LED는 호스트 테스트 범위 밖이다.
