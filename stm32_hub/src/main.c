#include "board_pins.h"
#include "hub.h"
#include "parser.h"
#include "platform.h"
#include <stdio.h>
#include <string.h>
#include <ctype.h>
#include <inttypes.h>
static hub_t hub;
static comm_parser_t parsers[2];
static uint32_t status_at;
static void event_log(void *ctx,uint32_t now,uint8_t node,const char *event,const char *reason) {
    char line[224]; hub_t *h=ctx;
    snprintf(line,sizeof(line),"t=%"PRIu32" node=%u event=%s state=%s reason=%s gpio=%u",
             now,node,event,hub_state_name(h->state),reason,hub_output(h));
    platform_log(line);
}
static void receive(void *ctx,const comm_frame_t *f,uint32_t now) {
    char line[180];
    hub_receive(ctx,f,now);
    if (f->type==MSG_HEARTBEAT) return;
    switch (f->type) {
    case MSG_BEAM:
        snprintf(line,sizeof(line),"t=%"PRIu32" node=%u event=PAYLOAD simulated=1 type=BEAM_BREAK duration_0p1ms=%u min_adc=%u",
                 now,f->sender,comm_u16(f->payload),comm_u16(f->payload+2)); break;
    case MSG_SOUND:
        snprintf(line,sizeof(line),"t=%"PRIu32" node=%u event=PAYLOAD simulated=1 type=SOUND rms=%u",
                 now,f->sender,comm_u16(f->payload)); break;
    case MSG_DOOR:
        snprintf(line,sizeof(line),"t=%"PRIu32" node=%u event=PAYLOAD simulated=1 type=DOOR is_open=%u hall_adc=%u",
                 now,f->sender,f->payload[0],comm_u16(f->payload+1)); break;
    default:
        snprintf(line,sizeof(line),"t=%"PRIu32" node=%u event=PAYLOAD simulated=1 type=SHOCK pulse_count=%u",
                 now,f->sender,f->payload[0]); break;
    }
    platform_log(line);
}
static void status(uint32_t now) {
    unsigned i; char line[600];
    snprintf(line,sizeof(line),"t=%"PRIu32" node=3 event=STATUS state=%s reason=%s gpio=%u log_drops=%"PRIu32" pc_rx_drops=%"PRIu32,
             now,hub_state_name(hub.state),hub.reason,hub_output(&hub),platform_log_drops(),platform_pc_rx_drops());
    platform_log(line);
    for (i=0;i<2;i++) {
        const hub_node_t *n=&hub.nodes[i]; const comm_parser_t *p=&parsers[i];
        const dma_stream_t *d=platform_stream(i);
        snprintf(line,sizeof(line),"t=%"PRIu32" node=%u event=NODE_STATUS uart=%s seen=%u last_hb_ms=%"PRIu32" hb_age_ms=%"PRIu32" fault=%u seq=%u health=%u seq_gaps=%"PRIu32
                 " dma_bytes=%"PRIu32" frames=%"PRIu32" crc_errors=%"PRIu32" invalid=%"PRIu32" partial_timeouts=%"PRIu32" overruns=%"PRIu32" discarded=%"PRIu32
                 " uart_errors=%"PRIu32" dma_errors=%"PRIu32" hb=%"PRIu32" beam=%"PRIu32" sound=%"PRIu32" door=%"PRIu32" shock=%"PRIu32,
                 now,i+1,i?"USART3":"USART1",n->seen,n->last_hb,n->seen?now-n->last_hb:0,n->fault,n->seq,n->health,n->seq_gaps,
                 d->bytes,p->valid,p->checksum_errors,p->invalid,p->partial_timeouts,d->overruns,d->discarded,
                 platform_rx_errors(i),platform_dma_errors(i),n->events[0],n->events[1],n->events[2],n->events[3],n->events[4]);
        platform_log(line);
    }
}
static void console(uint32_t now) {
    static char command[32]; static unsigned used; static int overflow;
    static uint32_t previous_drops;
    uint32_t drops=platform_pc_rx_drops();
    int c; unsigned budget=32;
    if (drops!=previous_drops) { overflow=1; previous_drops=drops; }
    while (budget-- && (c=platform_pc_get())>=0) {
        if (c=='\r' || c=='\n') {
            if (overflow) event_log(&hub,now,NODE_HUB,"COMMAND_ERROR","invalid_or_incomplete_line");
            else if (used) {
                command[used]=0;
                if (!strcmp(command,"ARM")) hub_arm(&hub,now);
                else if (!strcmp(command,"DISARM")) hub_disarm(&hub,now);
                else if (!strcmp(command,"STATUS")) status(now);
                else if (!strcmp(command,"HELP")) event_log(&hub,now,NODE_HUB,"HELP","ARM,DISARM,STATUS,HELP");
                else event_log(&hub,now,NODE_HUB,"COMMAND_ERROR","unknown_command");
            }
            used=0; overflow=0;
        } else if (used<sizeof(command)-1) command[used++]=(char)toupper((unsigned char)c);
        else overflow=1;
    }
}
int main(void) {
    uint32_t now;
    platform_init(); hub_init(&hub,platform_ms(),event_log,&hub);
    comm_parser_init(&parsers[0],NODE_WINDOW,receive,&hub);
    comm_parser_init(&parsers[1],NODE_DOOR,receive,&hub);
    platform_log("t=0 node=3 event=BOOT reason=communication_smoke_test sensor_data=SIMULATED clock_hz=8000000");
    for (;;) {
        now=platform_ms();
        hub_tick(&hub,now);
        platform_receive(0,&parsers[0],now); platform_receive(1,&parsers[1],now);
        console(now); platform_status(hub_output(&hub)); platform_pc_flush();
        if ((uint32_t)(now-status_at)>=STATUS_PERIOD_MS) { status_at=now; status(now); }
    }
}
