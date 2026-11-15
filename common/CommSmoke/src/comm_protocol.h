#ifndef COMM_PROTOCOL_H
#define COMM_PROTOCOL_H
#include <stddef.h>
#include <stdint.h>
/* Header-only encoder: shared unchanged by AVR, STM32 and host tests. */
enum { COMM_SOF=0xAA, COMM_MAX_PAYLOAD=8, COMM_MAX_FRAME=13,
       NODE_WINDOW=1, NODE_DOOR=2, NODE_HUB=3,
       MSG_HEARTBEAT=0x10, MSG_BEAM=0x20, MSG_SOUND=0x21,
       MSG_DOOR=0x30, MSG_SHOCK=0x31 };
typedef struct { uint8_t sender, type, len, payload[COMM_MAX_PAYLOAD]; } comm_frame_t;
static inline uint16_t comm_u16(const uint8_t *p) {
    return (uint16_t)((uint16_t)p[0] | ((uint16_t)p[1]<<8));
}
static inline void comm_put_u16(uint8_t *p, uint16_t v) {
    p[0]=(uint8_t)v; p[1]=(uint8_t)(v>>8);
}
static inline int comm_schema(uint8_t id, uint8_t type, uint8_t len) {
    if (id < NODE_WINDOW || id > NODE_HUB) return 0;
    switch (type) {
    case MSG_HEARTBEAT: return len==2;
    case MSG_BEAM: return id==NODE_WINDOW && len==4;
    case MSG_SOUND: return id==NODE_WINDOW && len==2;
    case MSG_DOOR: return id==NODE_DOOR && len==3;
    case MSG_SHOCK: return id==NODE_DOOR && len==1;
    default: return 0;
    }
}
static inline size_t comm_encode(uint8_t *out, size_t capacity,
                                const comm_frame_t *f) {
    size_t i, n=(size_t)f->len+5;
    uint8_t x=0;
    if (!comm_schema(f->sender,f->type,f->len) || capacity<n ||
        (f->type==MSG_DOOR && f->payload[0]>1)) return 0;
    out[0]=COMM_SOF; out[1]=f->len; out[2]=f->sender; out[3]=f->type;
    for (i=0;i<f->len;i++) out[4+i]=f->payload[i];
    for (i=1;i<n-1;i++) x^=out[i];
    out[n-1]=x; return n;
}
#endif
