#ifndef BOARD_PINS_H
#define BOARD_PINS_H
#include "stm32f1xx.h"
/* Change status pins here; choose GPIOA/B/C, 0..15. Clocks A/B/C enabled. */
#define STATUS_BIT0_PORT GPIOA
#define STATUS_BIT0_PIN 6u
#define STATUS_BIT1_PORT GPIOB
#define STATUS_BIT1_PIN 6u
#define WINDOW_RX_PORT GPIOA
#define WINDOW_RX_PIN 10u
#define DOOR_RX_PORT GPIOB
#define DOOR_RX_PIN 11u
#define PC_TX_PORT GPIOA
#define PC_TX_PIN 2u
#define PC_RX_PORT GPIOA
#define PC_RX_PIN 3u
/* UART RX pins are fixed by the default (non-remapped) USART mapping. */
#ifndef NODE_BAUD
#define NODE_BAUD 38400u
#endif
#define PC_BAUD 115200u
#define HUB_CLOCK_HZ 8000000u
#define RX_DMA_SIZE 512u
#define STATUS_PERIOD_MS 2000u
#endif
