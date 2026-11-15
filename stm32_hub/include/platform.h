#ifndef PLATFORM_H
#define PLATFORM_H
#include "dma_stream.h"
void platform_init(void);
uint32_t platform_ms(void);
void platform_receive(unsigned,comm_parser_t *,uint32_t);
const dma_stream_t *platform_stream(unsigned);
uint32_t platform_rx_errors(unsigned);
uint32_t platform_dma_errors(unsigned);
uint32_t platform_pc_rx_drops(void);
uint32_t platform_log_drops(void);
int platform_pc_get(void);
void platform_pc_flush(void);
void platform_log(const char *);
void platform_status(uint8_t);
#endif
