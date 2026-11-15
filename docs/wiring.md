# 임시 3 Uno + 1 NUCLEO-F103RB 배선

**HARDWARE NOT TESTED.** 전원을 끈 상태에서 배선한다. 보드 실크의 CN 번호와
1번 핀 표시를 기준으로 확인한다. Uno D 번호와 Nucleo Arduino 헤더 D 번호는
서로 다른 보드의 번호이다.

| 송신/출력 | 연결 | 수신/입력 | Nucleo 커넥터 대안 |
|---|---|---|---|
| Uno #1 D11 (SoftwareSerial TX, 5V) | 아래 분압기 #1 | PA10, USART1 RX | CN10-33 또는 CN9-3 (D2) |
| Uno #2 D11 (SoftwareSerial TX, 5V) | 아래 분압기 #2 | PB11, USART3 RX | CN10-18 |
| STM32 PA6, bit0, 3.3V | 신호선 | Uno #3 D2 INPUT | CN10-13 또는 CN5-5 (D12) |
| STM32 PB6, bit1, 3.3V | 신호선 | Uno #3 D3 INPUT | CN10-17 또는 CN5-3 (D10) |
| STM32 PA2 TX / PA3 RX | 보드 내 ST-LINK 연결 | PC ST-LINK USB VCP | 외부 UART 배선 불필요 |
| 각 Uno GND | 공통 GND | STM32 GND | 예: CN10-9 또는 CN7-19 |

Uno #1/#2 D10은 SoftwareSerial RX로 예약하고 첫 시험에서는 미연결한다.
STM32 USART1 TX PA9 / USART3 TX PB10은 이 시험에서 설정·연결하지 않는다.
Uno #3 UART는 USB 콘솔 전용이다. PA6/PB6에 SPI/I2C 등 다른 주변장치를 연결하지 않는다.

각 Uno 송신선에 **별도의** 분압기를 사용한다:

```text
Uno D11 ---- 1 kΩ ----+---- STM32 RX (PA10 또는 PB11)
                     |
                    2 kΩ
                     |
                    GND
```

5V HIGH → 약 3.33V. 1% 저항을 권장하며 실측 전압과 파형을 확인한다.
**Uno의 5V TX를 STM32 RX에 직접 연결하지 않는다.** 분압기와 공통 GND가 모두 필요하다.
각 보드가 서로 다른 USB 전원으로 작동하면 **5V 전원선끼리 직접 묶지 않는다.**
이 구성에서는 GND와 필요한 신호선만 연결하고, 네 보드를 모두 켠 뒤 시험한다.
꺼진 보드로 신호를 계속 인가하는 운용은 피한다.

Uno #3 D2와 D3에는 각각 외부 **10 kΩ pull-down → GND**를 넣는다.
Uno에는 내부 INPUT_PULLDOWN이 없다. STM32 3.3V 출력은 5V ATmega328P의 일반
디지털 입력 HIGH 기준(0.6 VCC = 3.0V)을 충족하지만 여유가 작으므로 짧은 배선으로
실측한다. 5V pull-up은 사용하지 않는다.

표기 순서는 **bit1 bit0**이다. PA6는 하위 비트이다.

| PB6 → D3, bit1 | PA6 → D2, bit0 | Uno #3 출력 | D13 LED |
|---|---|---|---|
| 0 | 0 | NORMAL (DISARMED 또는 ARMED) | 꺼짐 |
| 0 | 1 | SUSPECT | 1Hz 점멸 |
| 1 | 0 | ALARM | 계속 켜짐 |
| 1 | 1 | FAULT | 4Hz 점멸 |

PA6/PB6는 서로 다른 GPIO 포트이므로 갱신 순간 중간 코드가 잠깐 나타날 수 있다.
Uno #3은 입력이 10ms 유지된 뒤 상태를 바꾼다. 두 상태선만으로 허브 정지나 단선을
구별할 수는 없으며, pull-down 때문에 허브 전원 OFF도 NORMAL로 보일 수 있다.
현재 시험의 FAULT는 허브가 감지한 센서 노드 HEARTBEAT 장애를 뜻한다.

ST-LINK VCP 기본 연결은 SB13/SB14 ON, SB62/SB63 OFF이다. 보드 개조 이력이 있으면
해당 실크와 회로도를 먼저 확인한다. PA2/PA3 외부 헤더에 별도의 Uno를 연결하지 않는다.

근거: [ST UM1724 Rev 17](https://www.st.com/resource/en/user_manual/um1724-stm32-nucleo64-boards-mb1136-stmicroelectronics.pdf),
§7.8 USART, Table 12 NUCLEO-F103RB Arduino 헤더, Table 27 Morpho 헤더.
DMA/USART 기본 핀 기능은 [ST RM0008](https://www.st.com/resource/en/reference_manual/rm0008-stm32f101xx-stm32f102xx-stm32f103xx-stm32f105xx-and-stm32f107xx-advanced-arm-based-32-bit-mcus-stmicroelectronics.pdf)의
AFIO 및 USART/DMA 설명을 기준으로 했다. 커넥터 매핑의 문서 확인과 실제 배선 시험은 별개이다.
