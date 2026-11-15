#include "platform.h"
#include "board_pins.h"
#include <string.h>
#define TX_SIZE 4096u
#define PC_RX_SIZE 128u
typedef struct {
    DMA_Channel_TypeDef *channel;
    USART_TypeDef *uart;
    volatile uint8_t ring[RX_DMA_SIZE];
    volatile uint32_t wraps, dma_errors;
    uint32_t rx_errors, last_poll;
    dma_stream_t stream;
    uint32_t tc_flag, te_flag, clear_mask;
} rx_dma_t;
static rx_dma_t inputs[2];
static volatile uint32_t milliseconds;
static char tx[TX_SIZE];
static uint32_t tx_head,tx_tail,log_drops;
static volatile uint8_t pc_rx[PC_RX_SIZE];
static volatile uint32_t pc_head,pc_tail,pc_drops;
void SysTick_Handler(void) { milliseconds++; }
uint32_t platform_ms(void) { return milliseconds; }
static void pin_mode(GPIO_TypeDef *port,unsigned pin,uint32_t mode) {
    volatile uint32_t *cr=pin<8 ? &port->CRL : &port->CRH;
    unsigned shift=(pin%8)*4;
    *cr=(*cr & ~(15u<<shift)) | (mode<<shift);
}
void platform_status(uint8_t bits) {
    STATUS_BIT0_PORT->BSRR=1u<<(STATUS_BIT0_PIN+((bits&1)?0u:16u));
    STATUS_BIT1_PORT->BSRR=1u<<(STATUS_BIT1_PIN+((bits&2)?0u:16u));
}
static void uart_setup(USART_TypeDef *u,uint32_t baud,int tx_enable) {
    u->CR1=0; u->CR2=0; u->CR3=0;
    u->BRR=(HUB_CLOCK_HZ+baud/2u)/baud; /* oversampling 16: BRR = round(PCLK/baud) */
    u->CR1=USART_CR1_UE | USART_CR1_RE | (tx_enable?USART_CR1_TE:0u);
}
static void dma_setup(unsigned i,DMA_Channel_TypeDef *ch,USART_TypeDef *u,
                      uint32_t tc,uint32_t te,uint32_t clear) {
    rx_dma_t *r=&inputs[i];
    r->channel=ch; r->uart=u; r->tc_flag=tc; r->te_flag=te; r->clear_mask=clear;
    ch->CCR=0; DMA1->IFCR=clear;
    ch->CPAR=(uint32_t)(uintptr_t)&u->DR;
    ch->CMAR=(uint32_t)(uintptr_t)r->ring;
    ch->CNDTR=RX_DMA_SIZE;
    /* DIR=0 peripheral->memory; PSIZE=MSIZE=0 byte; PINC=MEM2MEM=0. */
    ch->CCR=DMA_CCR_MINC | DMA_CCR_CIRC | DMA_CCR_PL_1 |
            DMA_CCR_TCIE | DMA_CCR_TEIE | DMA_CCR_EN;
    u->CR3=USART_CR3_DMAR;
}
void platform_init(void) {
    RCC->AHBENR |= RCC_AHBENR_DMA1EN;
    RCC->APB2ENR |= RCC_APB2ENR_AFIOEN | RCC_APB2ENR_IOPAEN |
                    RCC_APB2ENR_IOPBEN | RCC_APB2ENR_IOPCEN | RCC_APB2ENR_USART1EN;
    RCC->APB1ENR |= RCC_APB1ENR_USART2EN | RCC_APB1ENR_USART3EN;
    AFIO->MAPR &= ~(AFIO_MAPR_USART1_REMAP | AFIO_MAPR_USART2_REMAP | AFIO_MAPR_USART3_REMAP);
    platform_status(0);
    pin_mode(STATUS_BIT0_PORT,STATUS_BIT0_PIN,2); /* 2 MHz push pull output */
    pin_mode(STATUS_BIT1_PORT,STATUS_BIT1_PIN,2);
    /* Input pull-up: idle high even when a transmitting node is disconnected. */
    WINDOW_RX_PORT->BSRR=1u<<WINDOW_RX_PIN;
    DOOR_RX_PORT->BSRR=1u<<DOOR_RX_PIN;
    PC_RX_PORT->BSRR=1u<<PC_RX_PIN;
    pin_mode(WINDOW_RX_PORT,WINDOW_RX_PIN,8);
    pin_mode(DOOR_RX_PORT,DOOR_RX_PIN,8);
    pin_mode(PC_RX_PORT,PC_RX_PIN,8);
    pin_mode(PC_TX_PORT,PC_TX_PIN,10); /* AF push pull, 2 MHz */
    uart_setup(USART1,NODE_BAUD,0); uart_setup(USART3,NODE_BAUD,0);
    uart_setup(USART2,PC_BAUD,1);
    dma_setup(0,DMA1_Channel5,USART1,DMA_ISR_TCIF5,DMA_ISR_TEIF5,DMA_IFCR_CGIF5);
    dma_setup(1,DMA1_Channel3,USART3,DMA_ISR_TCIF3,DMA_ISR_TEIF3,DMA_IFCR_CGIF3);
    NVIC_SetPriority(DMA1_Channel5_IRQn,1); NVIC_SetPriority(DMA1_Channel3_IRQn,1);
    NVIC_EnableIRQ(DMA1_Channel5_IRQn); NVIC_EnableIRQ(DMA1_Channel3_IRQn);
    NVIC_SetPriority(USART2_IRQn,2); NVIC_EnableIRQ(USART2_IRQn);
    USART2->CR1 |= USART_CR1_RXNEIE;
    (void)SysTick_Config(HUB_CLOCK_HZ/1000u); /* reload 7999 at 8 MHz */
}
/* Only count TC epochs in IRQ. Parsing, logging, restarts are main-loop work. */
static void dma_irq(unsigned i) {
    rx_dma_t *r=&inputs[i]; uint32_t flags=DMA1->ISR;
    if (flags&r->tc_flag) { r->wraps++; DMA1->IFCR=r->tc_flag; }
    if (flags&r->te_flag) { r->dma_errors++; DMA1->IFCR=r->te_flag; }
}
void DMA1_Channel5_IRQHandler(void) { dma_irq(0); }
void DMA1_Channel3_IRQHandler(void) { dma_irq(1); }
void USART2_IRQHandler(void) {
    uint32_t sr=USART2->SR;
    if (sr & (USART_SR_RXNE | USART_SR_ORE | USART_SR_FE | USART_SR_NE)) {
        uint8_t b=(uint8_t)USART2->DR;
        if (sr & (USART_SR_ORE | USART_SR_FE | USART_SR_NE)) { pc_drops++; return; }
        if (pc_head-pc_tail<PC_RX_SIZE) { pc_rx[pc_head%PC_RX_SIZE]=b; pc_head++; }
        else pc_drops++;
    }
}
static void restart_input(unsigned i,comm_parser_t *parser,uint32_t now,int uart_error) {
    rx_dma_t *r=&inputs[i];
    uint32_t mask=__get_PRIMASK(),remaining,count;
    __disable_irq();
    r->channel->CCR &= ~DMA_CCR_EN;
    if (uart_error) { (void)r->uart->DR; r->rx_errors++; }
    dma_irq(i);
    remaining=r->channel->CNDTR;
    if (remaining) {
        count=r->wraps*RX_DMA_SIZE+(RX_DMA_SIZE-remaining)-r->stream.tail;
        r->stream.bytes+=count; r->stream.discarded+=count;
    }
    DMA1->IFCR=r->clear_mask; r->wraps=0; r->stream.tail=0;
    r->channel->CNDTR=RX_DMA_SIZE; r->channel->CCR |= DMA_CCR_EN;
    __set_PRIMASK(mask);
    comm_parser_reset(parser); r->last_poll=now;
}
void platform_receive(unsigned i,comm_parser_t *parser,uint32_t now) {
    rx_dma_t *r=&inputs[i];
    uint32_t primask,remaining,producer,sr;
    /* SR/DR clearing is reserved for actual UART errors; never clear IDLE by
       reading DR during healthy DMA traffic (that can steal a received byte). */
    sr=r->uart->SR;
    if (sr & (USART_SR_ORE | USART_SR_FE | USART_SR_NE | USART_SR_PE)) {
        restart_input(i,parser,now,1); return;
    }
    if (!(r->channel->CCR & DMA_CCR_EN)) {
        /* Transfer error: fail visibly, reset channel and parser. */
        r->stream.overruns++; restart_input(i,parser,now,0); return;
    }
    primask=__get_PRIMASK(); __disable_irq();
    /* Account a pending rollover before sampling CNDTR; retry if the rollover
       happened between these two reads. TC IRQ cannot race this snapshot. */
    do { dma_irq(i); remaining=r->channel->CNDTR; }
    while (DMA1->ISR & r->tc_flag);
    producer=r->wraps*RX_DMA_SIZE + (RX_DMA_SIZE-remaining);
    __set_PRIMASK(primask);
    __DMB();
    if (!remaining) return; /* transient CNDTR=0: sample again after reload */
    /* Sticky TC cannot count multiple laps with interrupts masked externally.
       Treat a >ring-time main-loop stall as uncertain data and resynchronize. */
    if ((uint32_t)(now-r->last_poll) >= (RX_DMA_SIZE*10000u/NODE_BAUD)) {
        r->stream.overruns++; comm_parser_reset(parser);
        r->stream.bytes+=producer-r->stream.tail;
        r->stream.discarded+=producer-r->stream.tail;
        r->stream.tail=producer;
    } else dma_stream_drain(&r->stream,r->ring,RX_DMA_SIZE,producer,parser,now);
    r->last_poll=now;
    comm_parser_expire(parser,now);
}
const dma_stream_t *platform_stream(unsigned i) { return &inputs[i].stream; }
uint32_t platform_rx_errors(unsigned i) { return inputs[i].rx_errors; }
uint32_t platform_dma_errors(unsigned i) { return inputs[i].dma_errors; }
uint32_t platform_pc_rx_drops(void) { return pc_drops; }
uint32_t platform_log_drops(void) { return log_drops; }
int platform_pc_get(void) {
    uint8_t byte;
    if (pc_tail==pc_head) return -1;
    byte=pc_rx[pc_tail%PC_RX_SIZE];
    pc_tail++;
    return byte;
}
void platform_log(const char *line) {
    size_t n=strlen(line),i;
    if (n+1>TX_SIZE-(tx_head-tx_tail)) { log_drops++; return; }
    for (i=0;i<n;i++) tx[tx_head++%TX_SIZE]=line[i];
    tx[tx_head++%TX_SIZE]='\n';
}
void platform_pc_flush(void) {
    /* Sole TX owner: bounded polling; never wait for TXE and never restart DMA. */
    unsigned budget=32;
    while (budget-- && tx_tail!=tx_head && (USART2->SR & USART_SR_TXE))
        USART2->DR=(uint8_t)tx[tx_tail++%TX_SIZE];
}
