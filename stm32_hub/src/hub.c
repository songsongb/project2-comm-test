#include "hub.h"
#include <string.h>
static void log_event(hub_t *h,uint32_t now,uint8_t id,const char *ev,const char *why) {
    if (h->log) h->log(h->log_context,now,id,ev,why);
}
const char *hub_state_name(enum hub_state s) {
    static const char *const names[]={"DISARMED","ARMED","SUSPECT","ALARM","FAULT"};
    return names[s];
}
uint8_t hub_output(const hub_t *h) {
    return h->state==FAULT?3 : h->state==ALARM?2 : h->state==SUSPECT?1 : 0;
}
static void evaluate(hub_t *h,uint32_t now,const char *cause,uint8_t id) {
    enum hub_state next;
    const char *why=cause;
    if (h->latched) { next=ALARM; why=h->state==ALARM?h->reason:cause; }
    else if (h->nodes[0].fault || h->nodes[1].fault) {
        next=FAULT; why=h->nodes[0].fault?"window_heartbeat_timeout":"door_heartbeat_timeout";
    } else if (!h->armed) {
        next=DISARMED; if (h->state==DISARMED) why=h->reason;
    }
    else if (h->door_pending || h->shock_pending) {
        next=SUSPECT; why=h->door_pending?"door_open_grace":"shock_wait";
    } else { next=ARMED; if (h->state==ARMED) why=h->reason; }
    if (h->state!=next || strcmp(h->reason,why)!=0) {
        h->state=next; h->reason=why;
        log_event(h,now,id,"STATE",why);
    }
}
void hub_init(hub_t *h,uint32_t now,hub_log_fn log,void *ctx) {
    memset(h,0,sizeof(*h)); h->started=now; h->state=DISARMED;
    h->reason="boot_disarmed"; h->log=log; h->log_context=ctx;
}
void hub_arm(hub_t *h,uint32_t now) {
    /* ARM is idempotent: it must not extend an open-door deadline. */
    if (!h->armed) {
        h->armed=1; h->door_pending=h->door_open; h->door_since=now;
        h->have_shock=h->have_sound=0;
    }
    log_event(h,now,NODE_HUB,"COMMAND","ARM"); evaluate(h,now,"armed",NODE_HUB);
}
void hub_disarm(hub_t *h,uint32_t now) {
    h->armed=0; h->latched=0; h->door_pending=h->shock_pending=0;
    h->have_shock=h->have_sound=0;
    log_event(h,now,NODE_HUB,"COMMAND","DISARM"); evaluate(h,now,"disarmed",NODE_HUB);
}
void hub_tick(hub_t *h,uint32_t now) {
    unsigned i;
    const char *cause=h->armed?"armed":"disarmed";
    for (i=0;i<2;i++) {
        hub_node_t *n=&h->nodes[i];
        uint8_t bad=n->seen ? (uint32_t)(now-n->last_hb)>=HUB_TIMEOUT_MS :
                             (uint32_t)(now-h->started)>=HUB_GRACE_MS;
        if (bad!=n->fault) {
            n->fault=bad;
            log_event(h,now,(uint8_t)(i+1),bad?"LINK_LOST":"LINK_RECOVERED","heartbeat");
        }
    }
    if (h->armed && h->door_pending && (uint32_t)(now-h->door_since)>=10000u) {
        h->latched=1; evaluate(h,now,"door_open_10s",NODE_DOOR);
    }
    if (h->shock_pending && (uint32_t)(now-h->shock_since)>=5000u) {
        h->shock_pending=0; cause="shock_expired_5s";
    }
    evaluate(h,now,cause,NODE_HUB);
}
void hub_receive(void *ctx,const comm_frame_t *f,uint32_t now) {
    hub_t *h=(hub_t *)ctx;
    hub_node_t *n;
    unsigned event;
    const char *cause="sensor_event";
    uint8_t recovered;
    if (f->sender<1 || f->sender>2 || !comm_schema(f->sender,f->type,f->len) ||
        (f->type==MSG_DOOR && f->payload[0]>1)) return;
    n=&h->nodes[f->sender-1];
    switch (f->type) {
    case MSG_HEARTBEAT:
        if (n->seen && f->payload[0]!=(uint8_t)(n->seq+1)) n->seq_gaps++;
        n->seen=1; n->seq=f->payload[0]; n->health=f->payload[1]; n->last_hb=now;
        n->events[0]++;
        recovered=n->fault;
        if (recovered) { n->fault=0; log_event(h,now,f->sender,"LINK_RECOVERED","heartbeat"); }
        evaluate(h,now,recovered?"heartbeat_restored":h->armed?"armed":"disarmed",f->sender); return;
    case MSG_BEAM: event=1; cause="beam_break_simulated"; break;
    case MSG_SOUND: event=2; cause="sound_simulated"; break;
    case MSG_DOOR: event=3; cause=f->payload[0]?"door_open_simulated":"door_close_simulated"; break;
    default: event=4; cause="shock_simulated"; break;
    }
    n->events[event]++; log_event(h,now,f->sender,"SIM_EVENT",cause);
    if (f->type==MSG_DOOR) h->door_open=f->payload[0];
    if (!h->armed) return;
    switch (f->type) {
    case MSG_BEAM: h->latched=1; break;
    case MSG_DOOR:
        if (h->door_open && !h->door_pending) { h->door_pending=1; h->door_since=now; }
        if (!h->door_open) h->door_pending=0;
        break;
    case MSG_SHOCK:
        if (!h->shock_pending) { h->shock_pending=1; h->shock_since=now; }
        h->last_shock=now; h->have_shock=1;
        if (h->have_sound && (uint32_t)(now-h->last_sound)<=500u) {
            h->latched=1; cause="shock_sound_500ms";
        }
        break;
    case MSG_SOUND:
        h->last_sound=now; h->have_sound=1;
        if (h->have_shock && (uint32_t)(now-h->last_shock)<=500u) {
            h->latched=1; cause="shock_sound_500ms";
        }
        break;
    default: break;
    }
    evaluate(h,now,cause,f->sender);
}
