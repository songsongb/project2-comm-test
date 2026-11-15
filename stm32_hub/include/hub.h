#ifndef HUB_H
#define HUB_H
#include "comm_protocol.h"
enum hub_state { DISARMED, ARMED, SUSPECT, ALARM, FAULT };
enum { HUB_GRACE_MS=1000, HUB_TIMEOUT_MS=600 };
typedef void (*hub_log_fn)(void *, uint32_t, uint8_t, const char *, const char *);
typedef struct {
    uint32_t last_hb, events[5], seq_gaps;
    uint8_t seen, fault, seq, health;
} hub_node_t;
typedef struct {
    hub_node_t nodes[2];
    uint32_t started, door_since, shock_since, last_shock, last_sound;
    uint8_t armed, latched, door_open, door_pending, shock_pending;
    uint8_t have_shock, have_sound;
    enum hub_state state;
    const char *reason;
    hub_log_fn log;
    void *log_context;
} hub_t;
void hub_init(hub_t *, uint32_t, hub_log_fn, void *);
void hub_receive(void *, const comm_frame_t *, uint32_t);
void hub_tick(hub_t *, uint32_t);
void hub_arm(hub_t *, uint32_t);
void hub_disarm(hub_t *, uint32_t);
const char *hub_state_name(enum hub_state);
uint8_t hub_output(const hub_t *);
#endif
