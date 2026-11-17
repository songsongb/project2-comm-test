#include "laser_guard.h"

#include <stdarg.h>
#include <stdio.h>
#include <string.h>

enum { RX_SIZE = 512, TX_SIZE = 1024, SYNC = 0xAA, FRAME_TIMEOUT_MS = 25 };

typedef struct {
    USART_TypeDef *usart;
    DMA_Channel_TypeDef *tx_dma;
    DMA_Channel_TypeDef *rx_dma;
    unsigned tx_channel;
    bool enabled;
    volatile uint8_t rx[RX_SIZE];
    uint16_t rx_tail;
    uint8_t tx[TX_SIZE];
    uint16_t tx_head;
    uint16_t tx_tail;
    uint16_t tx_in_flight;
} Uart;

static Uart uarts[3];
static volatile uint32_t ticks;

void lg_init(void)
{
    RCC->CR |= RCC_CR_HSION;
    while (!(RCC->CR & RCC_CR_HSIRDY)) {}
    RCC->CFGR &= ~RCC_CFGR_SW;
    while ((RCC->CFGR & RCC_CFGR_SWS) != RCC_CFGR_SWS_HSI) {}
    RCC->CR &= ~RCC_CR_PLLON;
    while (RCC->CR & RCC_CR_PLLRDY) {}

    FLASH->ACR = FLASH_ACR_PRFTBE | FLASH_ACR_LATENCY_2;
    /* HSI/2 x 16. APB1 32 MHz (timers 64 MHz), APB2 64 MHz, ADC ~10.67 MHz. */
    RCC->CFGR = RCC_CFGR_PPRE1_DIV2 | RCC_CFGR_ADCPRE_DIV6 | RCC_CFGR_PLLMULL16;
    RCC->CR |= RCC_CR_PLLON;
    while (!(RCC->CR & RCC_CR_PLLRDY)) {}
    RCC->CFGR |= RCC_CFGR_SW_PLL;
    while ((RCC->CFGR & RCC_CFGR_SWS) != RCC_CFGR_SWS_PLL) {}
    SystemCoreClock = LG_CPU_HZ;

    RCC->APB2ENR |= RCC_APB2ENR_AFIOEN | RCC_APB2ENR_IOPAEN
                 | RCC_APB2ENR_IOPBEN | RCC_APB2ENR_IOPCEN;
    RCC->AHBENR |= RCC_AHBENR_DMA1EN;
    (void)RCC->APB2ENR;
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CYCCNT = 0;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
    SysTick_Config(LG_CPU_HZ / 1000u);
}

void SysTick_Handler(void)
{
    ++ticks;
}

uint32_t lg_millis(void)
{
    return ticks;
}

void lg_gpio(GPIO_TypeDef *port, unsigned pin, unsigned config)
{
    volatile uint32_t *reg = pin < 8u ? &port->CRL : &port->CRH;
    unsigned shift = 4u * (pin & 7u);
    *reg = (*reg & ~(0xFu << shift)) | (config << shift);
}

void lg_uart_init(unsigned port, unsigned baud)
{
    static const struct {
        USART_TypeDef *usart;
        GPIO_TypeDef *gpio;
        unsigned tx_pin, rx_pin, tx_channel, rx_channel;
    } pins[] = {
        {USART1, GPIOA, 9, 10, 4, 5},
        {USART2, GPIOA, 2,  3, 7, 6},
        {USART3, GPIOB, 10, 11, 2, 3},
    };
    static DMA_Channel_TypeDef *const dma[] = {
        DMA1_Channel1, DMA1_Channel2, DMA1_Channel3, DMA1_Channel4,
        DMA1_Channel5, DMA1_Channel6, DMA1_Channel7
    };
    unsigned index = port - 1u;
    Uart *uart = &uarts[index];
    uart->usart = pins[index].usart;
    uart->tx_channel = pins[index].tx_channel;
    uart->tx_dma = dma[uart->tx_channel - 1u];
    uart->rx_dma = dma[pins[index].rx_channel - 1u];

    const uint32_t bus_hz = (port == 1u) ? LG_CPU_HZ : LG_CPU_HZ / 2u;
    if (port == 1u) {
        RCC->APB2ENR |= RCC_APB2ENR_USART1EN;
    } else {
        RCC->APB1ENR |= port == 2u ? RCC_APB1ENR_USART2EN : RCC_APB1ENR_USART3EN;
    }
    lg_gpio(pins[index].gpio, pins[index].tx_pin, LG_GPIO_AF_OUTPUT);
    lg_write(pins[index].gpio, pins[index].rx_pin, true);
    lg_gpio(pins[index].gpio, pins[index].rx_pin, LG_GPIO_PULL);

    uart->usart->BRR = (bus_hz + baud / 2u) / baud;
    uart->rx_dma->CPAR = (uint32_t)(uintptr_t)&uart->usart->DR;
    uart->rx_dma->CMAR = (uint32_t)(uintptr_t)uart->rx;
    uart->rx_dma->CNDTR = RX_SIZE;
    uart->rx_dma->CCR = DMA_CCR_MINC | DMA_CCR_CIRC | DMA_CCR_EN;
    uart->tx_dma->CPAR = (uint32_t)(uintptr_t)&uart->usart->DR;

    uart->usart->CR3 = USART_CR3_DMAT | USART_CR3_DMAR;
    uart->usart->CR1 = USART_CR1_UE | USART_CR1_TE | USART_CR1_RE;
    uart->enabled = true;
}

static void service_tx(Uart *uart)
{
    unsigned shift = 4u * (uart->tx_channel - 1u);
    if (uart->tx_in_flight) {
        uint32_t status = DMA1->ISR >> shift;
        if (!(status & (DMA_ISR_TCIF1 | DMA_ISR_TEIF1))) {
            return;
        }
        uart->tx_dma->CCR = 0;
        DMA1->IFCR = DMA_IFCR_CGIF1 << shift;
        uart->tx_tail = (uart->tx_tail + uart->tx_in_flight) % TX_SIZE;
        uart->tx_in_flight = 0;
    }
    if (uart->tx_head == uart->tx_tail) {
        return;
    }

    uart->tx_in_flight = uart->tx_head > uart->tx_tail
                         ? uart->tx_head - uart->tx_tail
                         : TX_SIZE - uart->tx_tail;
    uart->tx_dma->CMAR = (uint32_t)(uintptr_t)&uart->tx[uart->tx_tail];
    uart->tx_dma->CNDTR = uart->tx_in_flight;
    __DMB();
    uart->tx_dma->CCR = DMA_CCR_MINC | DMA_CCR_DIR | DMA_CCR_EN;
}

void lg_uart_service(void)
{
    for (unsigned i = 0; i < 3; ++i) {
        if (uarts[i].enabled) {
            service_tx(&uarts[i]);
        }
    }
}

static bool queue_tx(unsigned port, const uint8_t *data, unsigned count)
{
    Uart *uart = &uarts[port - 1u];
    if (!uart->enabled) {
        return false;
    }
    service_tx(uart);
    if (count > (uart->tx_tail + TX_SIZE - uart->tx_head - 1u) % TX_SIZE) {
        return false;
    }
    for (unsigned i = 0; i < count; ++i) {
        uart->tx[uart->tx_head] = data[i];
        uart->tx_head = (uart->tx_head + 1u) % TX_SIZE;
    }
    service_tx(uart);
    return true;
}

bool lg_uart_read(unsigned port, uint8_t *byte)
{
    Uart *uart = &uarts[port - 1u];
    if (!uart->enabled) {
        return false;
    }
    service_tx(uart);
    uint16_t head = (RX_SIZE - uart->rx_dma->CNDTR) % RX_SIZE;
    if (head == uart->rx_tail) {
        return false;
    }
    __DMB();
    *byte = uart->rx[uart->rx_tail];
    uart->rx_tail = (uart->rx_tail + 1u) % RX_SIZE;
    return true;
}

static uint8_t checksum(const uint8_t *data, unsigned length)
{
    uint8_t value = 0;
    for (unsigned i = 0; i < length; ++i) {
        value ^= data[i];
    }
    return value;
}

bool lg_send(unsigned port, uint8_t id, uint8_t type, const uint8_t *data, uint8_t len)
{
    if (len > sizeof(((LgFrame *)0)->data)) {
        return false;
    }
    uint8_t bytes[13] = {SYNC, len, id, type};
    if (len) {
        memcpy(bytes + 4, data, len);
    }
    bytes[4 + len] = checksum(bytes + 1, 3 + len);
    return queue_tx(port, bytes, 5 + len);
}

bool lg_recv(unsigned port, LgParser *parser, LgFrame *frame)
{
    uint32_t now = lg_millis();
    if (parser->used && now - parser->last_byte_ms >= FRAME_TIMEOUT_MS) {
        parser->used = 0;
        ++parser->errors;
    }
    uint8_t byte;
    while (lg_uart_read(port, &byte)) {
        if (!parser->used && byte != SYNC) {
            continue;
        }
        parser->last_byte_ms = now;
        parser->bytes[parser->used++] = byte;
        if (parser->used == 2 && byte > sizeof(frame->data)) {
            ++parser->errors;
            parser->used = (byte == SYNC);
            continue;
        }
        if (parser->used < 5 || parser->used < 5 + parser->bytes[1]) {
            continue;
        }
        unsigned len = parser->bytes[1];
        parser->used = 0;
        if (byte != checksum(parser->bytes + 1, 3 + len)) {
            ++parser->errors;
            parser->used = (byte == SYNC);
            continue;
        }
        frame->len = len;
        frame->id = parser->bytes[2];
        frame->type = parser->bytes[3];
        memcpy(frame->data, parser->bytes + 4, len);
        return true;
    }
    return false;
}

bool lg_log(const char *fmt, ...)
{
    char line[256];
    va_list args;
    va_start(args, fmt);
    int length = vsnprintf(line, sizeof(line), fmt, args);
    va_end(args);
    return length > 0 && (unsigned)length < sizeof(line)
        && queue_tx(2, (const uint8_t *)line, (unsigned)length);
}
