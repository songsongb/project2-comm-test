# 공통 UART 프로토콜 v1

8N1, flow control 없음. 기본 38400bps, 대안 19200bps. 양쪽 설정을 함께 변경한다.
프레임 길이는 `5 + payload_len`이며 payload 길이 범위는 0..8이다.
현재 정의된 메시지는 아래 고정 길이만 허용한다. 다중 바이트 값은 unsigned Little Endian이다.

```text
AA | payload_len | sender_id | message_type | payload[0..len-1] | xor
xor = payload_len XOR sender_id XOR message_type XOR 각 payload 바이트
```

| type | 이름 | payload | 허용 송신자 |
|---|---|---|---|
| 10 | HEARTBEAT | seq:u8, health:u8 | 01, 02, 03 |
| 20 | BEAM_BREAK | duration_0p1ms:u16, min_adc:u16 | 01 |
| 21 | SOUND | rms:u16 | 01 |
| 30 | DOOR | is_open:u8 (0 또는 1), hall_adc:u16 | 02 |
| 31 | SHOCK | pulse_count:u8 | 02 |

표의 type/ID와 아래 예시는 16진수다. ID 01=창문, 02=문, 03=허브.
허브 ID는 예약했으며 현재 노드 링크에서 허브 프레임을 수신하지 않는다.
USART1에서는 ID 01, USART3에서는 ID 02만 허용한다.
`seq`는 HEARTBEAT마다 증가하고 255 다음 0이다. `badcrc`도 seq를 증가시키므로
다음 정상 HEARTBEAT에서 seq_gaps가 늘 수 있다. 센서 이벤트의 별도 seq 필드는 없다.
시뮬레이터 `health=0`은 정상이다. health는 기록만 하고 별도 경보 조건으로 해석하지 않는다.
재부팅·중복·누락 때문에 seq가 연속하지 않으면 seq_gaps가 1 증가한다(빠진 패킷 개수가 아님).

정확한 예시:

```text
창문 heartbeat seq=0 health=0: AA 02 01 10 00 00 13
창문 beam 5 (5ms → 50), 합성 min_adc=100:
                              AA 04 01 20 32 00 64 00 73
창문 sound 300:                AA 02 01 21 2C 01 0F
문 open, 합성 hall_adc=900:    AA 03 02 30 01 84 03 B7
문 shock 3:                   AA 01 02 31 03 31
잘못된 heartbeat XOR:         AA 02 01 10 00 00 12
```

`beam 1/2/5`는 duration을 각각 10/20/50으로 전송한다. 실제 차단 시간이나 ADC를
측정하지 않는다. min_adc=100, hall_adc=open 900/close 100은 합성 상수다.
PC 로그에 `SIM_EVENT`, `simulated=1`, 단위를 포함한 payload 필드가 출력된다.

`common/CommSmoke/src/comm_protocol.h`의 `comm_frame_t`, `comm_encode`,
`comm_put_u16`, `comm_u16`를 AVR·STM32·호스트가 그대로 공유한다.
Arduino용 라이브러리 경로는 `--libraries <프로젝트>/common`이다.

스트림 파서는 `common/parser.{c,h}`이다. `comm_parser_init(parser, expected_id,
callback, context)` 후 바이트마다 `comm_parser_feed(parser, byte, now_ms)`를 호출한다.
새 입력이 없을 때도 `comm_parser_expire(parser, now_ms)`를 호출한다.
콜백은 검증된 프레임만 받는다. 상태 판정 API는 `hub_receive(context, frame, now_ms)`다.
허브→최종 센서 노드 교체 시에도 이 인터페이스를 유지한다.

부분 프레임을 보관하고, 한 번에 여러 프레임이 도착해도 순서대로 처리한다.
길이·송신자·종류·메시지별 길이·DOOR bool이 잘못되면 `invalid`를 증가시킨다.
XOR 불일치는 `crc_errors`를 증가시킨다(로그 필드 이름이며 실제 CRC 다항식은 아님).
실패한 후보는 한 바이트씩 이동하여 다음 AA를 찾으므로 손상된 프레임 내부에
후속 프레임의 시작이 있어도 다시 검사한다. AA가 정상 payload에 있어도 파싱 가능하다.
SOF 밖의 잡음은 무시하며 잡음 바이트 하나마다 invalid를 증가시키지는 않는다.
50ms 동안 다음 바이트가 없는 부분 프레임은 invalid와 partial_timeouts를 각각 증가시키고 폐기한다.

XOR은 일부 다중 비트 손상·우연한 정상 모양·재전송을 검출하지 못한다. 현재 규격에는
escape, 인증, ACK, 재전송이 없다. 임의의 손상 이후 무손실 복구를 보장하는 프로토콜이
아니며, 본 단계에서 검증하는 것은 길이/XOR 검사와 다음 정상 프레임 재수신이다.
