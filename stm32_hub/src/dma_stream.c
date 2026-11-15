#include "dma_stream.h"
void dma_stream_drain(dma_stream_t *s,const volatile uint8_t *ring,uint32_t size,
                      uint32_t producer,comm_parser_t *parser,uint32_t now) {
    uint32_t count=producer-s->tail;
    s->bytes+=count;
    if (count>size) {
        s->overruns++; s->discarded+=count;
        s->tail=producer; comm_parser_reset(parser); return;
    }
    while (s->tail!=producer) {
        uint8_t b=ring[s->tail%size]; s->tail++;
        comm_parser_feed(parser,b,now);
    }
}
