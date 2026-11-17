#ifndef LASER_GUARD_H
#define LASER_GUARD_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "stm32f1xx.h"

#define LG_CPU_HZ 64000000u

enum {
    LG_GPIO_ANALOG = 0x0,
    LG_GPIO_FLOAT = 0x4,
    LG_GPIO_PULL = 0x8,
    LG_GPIO_OUTPUT = 0x2,
    LG_GPIO_AF_OUTPUT = 0xA
};

enum { LG_NODE_A = 1, LG_NODE_B = 2, LG_HUB = 3 };
enum { LG_READY = 1, LG_ACTIVE = 2, LG_SENSOR_FAULT = 4 };
enum {
    LG_HEARTBEAT = 0x10,
    LG_BEAM = 0x20,
    LG_SOUND = 0x21,
    LG_DOOR = 0x30,
    LG_SHOCK = 0x31,
    LG_MODE = 0x80,
    LG_CAL = 0x82,
    LG_LOAD = 0x83,
    LG_ACK = 0x90
};

typedef struct {
    uint8_t id;
    uint8_t type;
    uint8_t len;
    uint8_t data[8];
} LgFrame;

typedef struct {
    uint8_t bytes[13];
    uint8_t used;
    uint32_t last_byte_ms;
    uint32_t errors;
} LgParser;

void lg_init(void);
uint32_t lg_millis(void);
void lg_gpio(GPIO_TypeDef *port, unsigned pin, unsigned config);

static inline void lg_write(GPIO_TypeDef *port, unsigned pin, bool level)
{
    port->BSRR = 1u << (pin + (level ? 0u : 16u));
}

static inline bool lg_read(GPIO_TypeDef *port, unsigned pin)
{
    return (port->IDR & (1u << pin)) != 0u;
}

/* UART APIs are called from foreground code. TX data are copied before return. */
void lg_uart_init(unsigned port, unsigned baud);
void lg_uart_service(void);
bool lg_uart_read(unsigned port, uint8_t *byte);
bool lg_send(unsigned port, uint8_t id, uint8_t type, const uint8_t *data, uint8_t len);
bool lg_recv(unsigned port, LgParser *parser, LgFrame *frame);
bool lg_log(const char *fmt, ...) __attribute__((format(printf, 1, 2)));

#endif
