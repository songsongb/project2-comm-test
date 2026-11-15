#ifndef DMA_STREAM_H
#define DMA_STREAM_H
#include "parser.h"
typedef struct { uint32_t tail, bytes, overruns, discarded; } dma_stream_t;
/* producer is an absolute byte position, including DMA TC wrap epochs. */
void dma_stream_drain(dma_stream_t *, const volatile uint8_t *, uint32_t,
                      uint32_t, comm_parser_t *, uint32_t);
#endif
