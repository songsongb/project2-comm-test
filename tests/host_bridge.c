/* Thin ABI adapter only: Python exercises production C, not a duplicate model. */
#include "hub.h"
#include "parser.h"
#include "dma_stream.h"
#include <string.h>
static hub_t h;
static comm_parser_t p[2];
static dma_stream_t stream[2];
static volatile uint8_t ring[2][512];
static uint32_t producer[2],lost[2],recovered[2];
static void logger(void *ctx,uint32_t now,uint8_t id,const char *event,const char *reason) {
    (void)ctx; (void)now; (void)reason;
    if (id<1 || id>2) return;
    if (!strcmp(event,"LINK_LOST")) lost[id-1]++;
    if (!strcmp(event,"LINK_RECOVERED")) recovered[id-1]++;
}
void test_reset(uint32_t now) {
    hub_init(&h,now,logger,0);
    comm_parser_init(&p[0],1,hub_receive,&h); comm_parser_init(&p[1],2,hub_receive,&h);
    memset(stream,0,sizeof(stream)); memset(producer,0,sizeof(producer));
    memset(lost,0,sizeof(lost)); memset(recovered,0,sizeof(recovered));
}
void test_arm(uint32_t now) { hub_arm(&h,now); }
void test_disarm(uint32_t now) { hub_disarm(&h,now); }
void test_tick(uint32_t now) {
    hub_tick(&h,now); comm_parser_expire(&p[0],now); comm_parser_expire(&p[1],now);
}
void test_feed(unsigned port,const uint8_t *bytes,unsigned len,uint32_t now) {
    unsigned i; for (i=0;i<len;i++) comm_parser_feed(&p[port],bytes[i],now);
}
unsigned test_encode(uint8_t id,uint8_t type,const uint8_t *bytes,uint8_t len,uint8_t *out,unsigned capacity) {
    comm_frame_t f;
    memset(&f,0,sizeof(f)); f.sender=id; f.type=type; f.len=len;
    if (len>COMM_MAX_PAYLOAD) return 0;
    if (len) memcpy(f.payload,bytes,len);
    return (unsigned)comm_encode(out,capacity,&f);
}
void test_dma_write(unsigned port,const uint8_t *data,unsigned n) {
    unsigned i; for (i=0;i<n;i++) ring[port][producer[port]++%512]=data[i];
}
void test_dma_poll(unsigned port,uint32_t now) {
    dma_stream_drain(&stream[port],ring[port],512,producer[port],&p[port],now);
}
void test_dma_base(unsigned port,uint32_t base) { stream[port].tail=base; producer[port]=base; }
unsigned test_state(void) { return h.state; }
unsigned test_gpio(void) { return hub_output(&h); }
const char *test_reason(void) { return h.reason; }
uint32_t test_parser(unsigned port,unsigned field) {
    switch (field) {
    case 0: return p[port].valid;
    case 1: return p[port].checksum_errors;
    case 2: return p[port].invalid;
    default: return p[port].partial_timeouts;
    }
}
uint32_t test_stream(unsigned port,unsigned field) {
    switch (field) {
    case 0: return stream[port].bytes;
    case 1: return stream[port].overruns;
    default: return stream[port].discarded;
    }
}
uint32_t test_node(unsigned port,unsigned field) {
    switch (field) {
    case 0: return h.nodes[port].last_hb;
    case 1: return h.nodes[port].fault;
    case 2: return lost[port];
    case 3: return recovered[port];
    case 4: return h.nodes[port].seq_gaps;
    default: return h.nodes[port].events[field-5];
    }
}
