#include "parser.h"
#include <string.h>
static void shift(comm_parser_t *p, unsigned n) {
    p->used=(uint8_t)(p->used-n);
    memmove(p->data,p->data+n,p->used);
}
void comm_parser_init(comm_parser_t *p, uint8_t id, comm_receive_fn fn, void *ctx) {
    memset(p,0,sizeof(*p)); p->expected_id=id; p->receive=fn; p->context=ctx;
}
void comm_parser_reset(comm_parser_t *p) { p->used=0; }
void comm_parser_expire(comm_parser_t *p, uint32_t now) {
    if (p->used && (uint32_t)(now-p->last_byte_ms)>=COMM_PARTIAL_TIMEOUT_MS) {
        p->invalid++; p->partial_timeouts++; p->used=0;
    }
}
void comm_parser_feed(comm_parser_t *p, uint8_t byte, uint32_t now) {
    comm_frame_t f;
    unsigned n,i; uint8_t x;
    comm_parser_expire(p,now); p->last_byte_ms=now;
    p->data[p->used++]=byte;
    for (;;) {
        if (!p->used) return;
        if (p->data[0]!=COMM_SOF) { shift(p,1); continue; }
        if (p->used<2) return;
        if (p->data[1]>COMM_MAX_PAYLOAD) { p->invalid++; shift(p,1); continue; }
        if (p->used<4) return;
        if ((p->expected_id && p->data[2]!=p->expected_id) ||
            !comm_schema(p->data[2],p->data[3],p->data[1])) {
            p->invalid++; shift(p,1); continue;
        }
        n=5u+p->data[1];
        if (p->used<n) return;
        x=0; for (i=1;i<n-1;i++) x^=p->data[i];
        if (x!=p->data[n-1]) { p->checksum_errors++; shift(p,1); continue; }
        if (p->data[3]==MSG_DOOR && p->data[4]>1) {
            p->invalid++; shift(p,1); continue;
        }
        memset(&f,0,sizeof(f));
        f.len=p->data[1]; f.sender=p->data[2]; f.type=p->data[3];
        memcpy(f.payload,p->data+4,f.len);
        shift(p,n); p->valid++;
        if (p->receive) p->receive(p->context,&f,now);
    }
}
