#ifndef COMM_PARSER_H
#define COMM_PARSER_H
#include "comm_protocol.h"
#define COMM_PARTIAL_TIMEOUT_MS 50u
typedef void (*comm_receive_fn)(void *, const comm_frame_t *, uint32_t);
typedef struct {
    uint8_t data[COMM_MAX_FRAME], used, expected_id;
    uint32_t last_byte_ms, valid, checksum_errors, invalid, partial_timeouts;
    comm_receive_fn receive;
    void *context;
} comm_parser_t;
void comm_parser_init(comm_parser_t *, uint8_t, comm_receive_fn, void *);
void comm_parser_feed(comm_parser_t *, uint8_t, uint32_t);
void comm_parser_expire(comm_parser_t *, uint32_t);
void comm_parser_reset(comm_parser_t *);
#endif
