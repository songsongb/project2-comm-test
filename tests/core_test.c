#include "hub.h"
#include "parser.h"
#include "dma_stream.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static unsigned callbacks;
static void receive(void *ctx,const comm_frame_t *f,uint32_t now) {
    (void)ctx; (void)now;
    assert(comm_schema(f->sender,f->type,f->len)); callbacks++;
}
int main(void) {
    comm_parser_t p;
    comm_frame_t f={1,MSG_BEAM,4,{50,0,100,0}};
    uint8_t out[COMM_MAX_FRAME],expected[]={0xAA,4,1,0x20,50,0,100,0,0x73};
    uint32_t seed=0x12345678u,now=0;
    unsigned i,j;
    hub_t h;
    assert(comm_encode(out,sizeof(out),&f)==sizeof(expected));
    assert(!memcmp(out,expected,sizeof(expected)));
    assert(comm_encode(out,8,&f)==0);
    comm_parser_init(&p,1,receive,0);
    for (i=0;i<sizeof(expected);i++) comm_parser_feed(&p,expected[i],now);
    assert(callbacks==1);
    /* Arbitrary bytes, schema errors, AA in payload, lengths: ASan/UBSan checks. */
    for (i=0;i<1000000u;i++) {
        seed=seed*1664525u+1013904223u;
        comm_parser_feed(&p,(uint8_t)(seed>>24),now);
        assert(p.used<COMM_MAX_FRAME);
        if ((i%997)==0) {
            now+=COMM_PARTIAL_TIMEOUT_MS;
            comm_parser_expire(&p,now);
            for (j=0;j<sizeof(expected);j++) comm_parser_feed(&p,expected[j],now);
        }
    }
    assert(callbacks>=1003);
    hub_init(&h,0,0,0);
    comm_parser_init(&p,0,hub_receive,&h);
    now=0;
    for (i=0;i<100000u;i++) {
        static const uint8_t types[]={MSG_HEARTBEAT,MSG_BEAM,MSG_SOUND,MSG_DOOR,MSG_SHOCK};
        static const uint8_t lengths[]={2,4,2,3,1};
        unsigned choice;
        uint8_t was_latched=h.latched;
        seed=seed*1664525u+1013904223u; now+=seed%20u;
        if ((seed&511u)==0) { hub_disarm(&h,now); was_latched=0; }
        else if ((seed&511u)==1) hub_arm(&h,now);
        choice=(seed>>16)%5;
        memset(&f,0,sizeof(f));
        f.type=types[choice]; f.len=lengths[choice];
        f.sender=choice>=3?NODE_DOOR:NODE_WINDOW;
        for (j=0;j<f.len;j++) f.payload[j]=(uint8_t)(seed>>(j*8));
        if (f.type==MSG_DOOR) f.payload[0]&=1;
        j=(unsigned)comm_encode(out,sizeof(out),&f); assert(j);
        for (unsigned k=0;k<j;k++) comm_parser_feed(&p,out[k],now);
        hub_tick(&h,now);
        assert(h.state>=DISARMED && h.state<=FAULT);
        assert(hub_output(&h)<=3);
        assert(!was_latched || h.state==ALARM);
        assert(!h.latched || h.state==ALARM);
    }
    puts("PASS C vectors + 1,000,000-byte parser fuzz + 100,000 state events (ASan/UBSan)");
    return 0;
}
