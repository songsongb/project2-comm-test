import ctypes as C
import random
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
lib = C.CDLL(str(ROOT / "build/libcommtest.so"))
u8p = C.POINTER(C.c_uint8)
for name in ("reset", "arm", "disarm", "tick"):
    getattr(lib, "test_" + name).argtypes = [C.c_uint32]
lib.test_feed.argtypes = [C.c_uint, u8p, C.c_uint, C.c_uint32]
lib.test_encode.argtypes = [C.c_uint8, C.c_uint8, u8p, C.c_uint8, u8p, C.c_uint]
lib.test_encode.restype = C.c_uint
lib.test_dma_write.argtypes = [C.c_uint, u8p, C.c_uint]
lib.test_dma_poll.argtypes = [C.c_uint, C.c_uint32]
lib.test_dma_base.argtypes = [C.c_uint, C.c_uint32]
for name in ("parser", "stream", "node"):
    getattr(lib, "test_" + name).argtypes = [C.c_uint, C.c_uint]
    getattr(lib, "test_" + name).restype = C.c_uint32
lib.test_reason.restype = C.c_char_p
DISARMED, ARMED, SUSPECT, ALARM, FAULT = range(5)
HB, BEAM, SOUND, DOOR, SHOCK = 0x10, 0x20, 0x21, 0x30, 0x31


def array(data):
    return (C.c_uint8 * len(data))(*data)


def frame(node, kind, payload, capacity=13):
    out = (C.c_uint8 * 13)()
    n = lib.test_encode(node, kind, array(payload), len(payload), out, capacity)
    return bytes(out[:n])


def raw_frame(node, kind, payload):
    body = bytes([len(payload), node, kind]) + bytes(payload)
    checksum = 0
    for b in body:
        checksum ^= b
    return b"\xaa" + body + bytes([checksum])


class CommunicationTests(unittest.TestCase):
    def setUp(self):
        lib.test_reset(0)
        self.seq = [0, 0]

    def feed(self, node, kind=HB, payload=None, now=0):
        if payload is None:
            payload = [self.seq[node - 1], 0]
            self.seq[node - 1] = (self.seq[node - 1] + 1) & 255
        self.bytes(node - 1, frame(node, kind, payload), now)

    def bytes(self, port, data, now=0):
        lib.test_feed(port, array(data), len(data), now)

    def alive(self, now):
        self.feed(1, now=now)
        self.feed(2, now=now)
        lib.test_tick(now)

    def advance(self, start, end):
        for t in range(start + 200, end, 200):
            self.alive(t)
        self.alive(end)

    def state(self, expected, gpio=None):
        self.assertEqual(lib.test_state(), expected)
        if gpio is not None:
            self.assertEqual(lib.test_gpio(), gpio)

    def test_encoder_known_vectors(self):
        self.assertEqual(frame(1, HB, [0, 0]).hex(), "aa020110000013")
        self.assertEqual(frame(1, BEAM, [50, 0, 100, 0]).hex(), "aa0401203200640073")
        self.assertEqual(frame(2, DOOR, [1, 0x84, 3]).hex(), "aa030230018403b7")
        for kind, payload in [(HB, [255, 0]), (BEAM, [0xaa, 0xaa, 0xaa, 0xaa]),
                              (SOUND, [0xaa, 0]), (DOOR, [0, 10, 0]), (SHOCK, [3])]:
            node = 2 if kind in (DOOR, SHOCK) else 1
            self.assertEqual(frame(node, kind, payload), raw_frame(node, kind, payload))
        self.assertEqual(frame(1, HB, [0, 0], capacity=6), b"")
        self.assertEqual(frame(1, HB, []), b"")
        self.assertEqual(frame(2, DOOR, [2, 0, 0]), b"")
        self.assertEqual(frame(1, HB, list(range(9))), b"")

    def test_T1_two_independent_heartbeat_streams(self):
        for now in range(0, 10001, 200):
            for node in (1, 2):
                data = frame(node, HB, [(now // 200) & 255, 0])
                self.bytes(node - 1, data[:3], now)
                self.bytes(node - 1, data[3:], now + 1)
            lib.test_tick(now + 1)
            self.state(DISARMED)
        for port in (0, 1):
            self.assertEqual(lib.test_parser(port, 0), 51)
            self.assertEqual(lib.test_node(port, 0), 10001)
            self.assertEqual(lib.test_node(port, 1), 0)
            self.assertEqual(lib.test_node(port, 4), 0)

    def test_T2_beam_alarm_latched_until_disarm(self):
        self.alive(0)
        self.feed(1, BEAM, [50, 0, 100, 0], 1)
        self.state(DISARMED, 0)
        lib.test_arm(2)
        self.feed(1, BEAM, [50, 0, 100, 0], 3)
        self.state(ALARM, 2)
        self.assertEqual(lib.test_reason(), b"beam_break_simulated")
        self.advance(3, 10003)
        lib.test_arm(10004)
        self.state(ALARM)
        lib.test_disarm(10005)
        self.state(DISARMED, 0)

    def test_T3_door_deadline_not_extended_by_repeat_or_arm(self):
        self.alive(0)
        lib.test_arm(0)
        self.feed(2, DOOR, [1, 0x84, 3], 10)
        self.state(SUSPECT, 1)
        self.advance(10, 9010)
        self.feed(2, DOOR, [1, 0x84, 3], 9011)
        lib.test_arm(9012)
        self.advance(9010, 10009)
        self.state(SUSPECT)
        self.alive(10010)
        self.state(ALARM)
        self.assertEqual(lib.test_reason(), b"door_open_10s")

    def test_door_close_cancels_and_open_when_disarmed(self):
        self.alive(0)
        self.feed(2, DOOR, [1, 0, 0], 1)
        self.state(DISARMED)
        lib.test_arm(2)
        self.state(SUSPECT)
        self.feed(2, DOOR, [0, 0, 0], 100)
        self.state(ARMED)
        self.advance(100, 11000)
        self.state(ARMED)

    def test_T4_shock_five_second_return(self):
        self.alive(0)
        lib.test_arm(0)
        self.feed(2, SHOCK, [3], 10)
        self.state(SUSPECT)
        self.advance(10, 4000)
        self.feed(2, SHOCK, [3], 4001)
        self.advance(4000, 5009)
        self.state(SUSPECT)
        self.alive(5010)
        self.state(ARMED, 0)
        self.assertEqual(lib.test_reason(), b"shock_expired_5s")
        self.alive(5011)
        self.assertEqual(lib.test_reason(), b"shock_expired_5s")

    def test_shock_expiry_does_not_cancel_open_door(self):
        self.alive(0)
        lib.test_arm(0)
        self.feed(2, DOOR, [1, 0, 0], 1)
        self.feed(2, SHOCK, [3], 2)
        self.advance(2, 5002)
        self.state(SUSPECT)
        self.alive(10001)
        self.state(ALARM)

    def test_T5_combo_both_orders_at_500ms_and_timestamp_zero(self):
        for reverse in (False, True):
            with self.subTest(reverse=reverse):
                self.setUp()
                self.alive(0)
                lib.test_arm(0)
                events = [(2, SHOCK, [3]), (1, SOUND, [44, 1])]
                if reverse:
                    events.reverse()
                self.feed(*events[0], now=0)
                self.alive(500)
                self.feed(*events[1], now=500)
                self.state(ALARM)
                self.assertEqual(lib.test_reason(), b"shock_sound_500ms")

    def test_combo_501ms_disarmed_and_rearm_history(self):
        self.alive(0)
        lib.test_arm(0)
        self.feed(2, SHOCK, [3], 0)
        self.feed(1, SOUND, [44, 1], 501)
        self.state(SUSPECT)
        lib.test_disarm(502)
        self.feed(2, SHOCK, [3], 503)
        lib.test_arm(504)
        self.feed(1, SOUND, [44, 1], 505)
        self.state(ARMED)

    def test_T6_T7_timeout_exact_boundary_and_recovery(self):
        for stopped in (1, 2):
            with self.subTest(stopped=stopped):
                self.setUp()
                self.alive(0)
                lib.test_arm(0)
                self.feed(3 - stopped, now=400)
                lib.test_tick(599)
                self.state(ARMED)
                lib.test_tick(600)
                self.state(FAULT, 3)
                self.assertEqual(lib.test_node(stopped - 1, 2), 1)
                lib.test_tick(601)
                self.assertEqual(lib.test_node(stopped - 1, 2), 1)
                self.feed(stopped, now=602)
                self.state(ARMED)
                self.assertEqual(lib.test_node(stopped - 1, 3), 1)

    def test_startup_grace_and_alarm_fault_priority(self):
        lib.test_tick(999)
        self.state(DISARMED)
        lib.test_tick(1000)
        self.state(FAULT)
        self.alive(1001)
        self.state(DISARMED)
        lib.test_arm(1002)
        self.feed(1, BEAM, [10, 0, 100, 0], 1003)
        lib.test_tick(1601)
        self.state(ALARM, 2)
        self.assertEqual(lib.test_node(0, 1), 1)
        self.assertEqual(lib.test_node(1, 1), 1)
        lib.test_disarm(1602)
        self.state(FAULT, 3)
        self.alive(1603)
        self.state(DISARMED, 0)

    def test_T8_bad_xor_does_not_refresh_heartbeat_and_recovers(self):
        self.alive(0)
        bad = bytearray(frame(1, HB, [1, 0]))
        bad[-1] ^= 1
        self.bytes(0, bad + frame(1, SOUND, [0xaa, 1]), 400)
        self.assertEqual(lib.test_parser(0, 1), 1)
        self.assertEqual(lib.test_parser(0, 0), 2)
        self.assertEqual(lib.test_node(0, 0), 0)
        self.feed(2, now=500)
        lib.test_tick(600)
        self.state(FAULT)
        self.feed(1, now=601)
        self.state(DISARMED)

    def test_invalid_schema_and_wrong_port(self):
        bad = [raw_frame(9, HB, [0, 0]), raw_frame(1, 0xff, [0, 0]),
               raw_frame(1, HB, [0]), raw_frame(1, HB, list(range(9))),
               raw_frame(2, DOOR, [2, 0, 0]), raw_frame(1, SHOCK, [3])]
        for b in bad:
            self.bytes(0, b)
        self.bytes(0, frame(2, HB, [0, 0]))
        self.assertEqual(lib.test_parser(0, 0), 0)
        self.assertGreaterEqual(lib.test_parser(0, 2), len(bad) + 1)
        self.feed(1)
        self.assertEqual(lib.test_parser(0, 0), 1)

    def test_invalid_door_boolean_on_correct_port(self):
        self.alive(0)
        lib.test_arm(0)
        self.bytes(1, raw_frame(2, DOOR, [2, 0, 0]), 1)
        self.state(ARMED)
        self.assertEqual(lib.test_parser(1, 2), 1)
        self.assertEqual(lib.test_node(1, 8), 0)  # DOOR event count
        self.feed(2, DOOR, [1, 0, 0], 2)
        self.state(SUSPECT)

    def test_partial_frames_all_split_positions_and_embedded_sof(self):
        data = frame(1, BEAM, [0xaa, 0, 0xaa, 0])
        for split in range(1, len(data)):
            self.setUp()
            self.bytes(0, data[:split], 0)
            self.assertEqual(lib.test_parser(0, 0), 0)
            self.bytes(0, data[split:], 1)
            self.assertEqual(lib.test_parser(0, 0), 1)
        self.bytes(0, data[:4], 2)
        lib.test_tick(52)
        self.assertEqual(lib.test_parser(0, 3), 1)
        self.feed(1, now=53)
        self.assertEqual(lib.test_parser(0, 0), 2)

    def test_corrupt_length_then_concatenated_recovery(self):
        good = frame(1, HB, [0, 0])
        self.bytes(0, b"noise\xaa\x04\x01\x20\x01" + good + good)
        self.assertEqual(lib.test_parser(0, 1), 1)
        self.assertEqual(lib.test_parser(0, 0), 2)

    def test_T9_dma_bursts_wraps_two_ports_random_chunks(self):
        rng = random.Random(1303)
        for port in (0, 1):
            frames = b"".join(frame(port + 1, HB, [i & 255, 0]) for i in range(2000))
            index = 0
            while index < len(frames):
                n = rng.randint(1, 400)
                data = frames[index:index + n]
                lib.test_dma_write(port, array(data), len(data))
                lib.test_dma_poll(port, 1)
                index += len(data)
            self.assertEqual(lib.test_parser(port, 0), 2000)
            self.assertEqual(lib.test_parser(port, 1), 0)
            self.assertEqual(lib.test_parser(port, 2), 0)
            self.assertEqual(lib.test_stream(port, 0), 14000)
            self.assertEqual(lib.test_stream(port, 1), 0)

    def test_dma_full_lap_overrun_recovery_and_u32_wrap(self):
        lib.test_dma_write(0, array(bytes(512)), 512)
        lib.test_dma_poll(0, 0)
        self.assertEqual(lib.test_stream(0, 0), 512)
        self.assertEqual(lib.test_stream(0, 1), 0)
        lib.test_dma_write(0, array(bytes(700)), 700)
        lib.test_dma_poll(0, 1)
        self.assertEqual(lib.test_stream(0, 1), 1)
        self.assertEqual(lib.test_stream(0, 2), 700)
        data = frame(1, HB, [0, 0])
        lib.test_dma_write(0, array(data), len(data))
        lib.test_dma_poll(0, 2)
        self.assertEqual(lib.test_parser(0, 0), 1)
        lib.test_dma_base(0, 0xfffffffc)
        lib.test_dma_write(0, array(data), len(data))
        lib.test_dma_poll(0, 3)
        self.assertEqual(lib.test_parser(0, 0), 2)

    def test_T10_gpio_codes_host_mapping_only(self):
        self.alive(0)
        self.state(DISARMED, 0)
        lib.test_arm(0)
        self.state(ARMED, 0)
        self.feed(2, SHOCK, [3], 1)
        self.state(SUSPECT, 1)
        self.feed(1, BEAM, [50, 0, 100, 0], 2)
        self.state(ALARM, 2)
        lib.test_disarm(3)
        lib.test_tick(600)
        self.state(FAULT, 3)

    def test_u32_time_wrap_and_sequence_wrap(self):
        base = 0xffffff00
        lib.test_reset(base)
        self.feed(1, HB, [255, 0], base)
        self.feed(1, HB, [0, 0], (base + 200) & 0xffffffff)
        self.feed(2, now=(base + 500) & 0xffffffff)
        lib.test_tick((base + 799) & 0xffffffff)
        self.assertEqual(lib.test_node(0, 1), 0)
        lib.test_tick((base + 800) & 0xffffffff)
        self.assertEqual(lib.test_node(0, 1), 1)
        self.assertEqual(lib.test_node(0, 4), 0)
        self.feed(1, HB, [2, 0], (base + 801) & 0xffffffff)
        self.assertEqual(lib.test_node(0, 4), 1)


if __name__ == "__main__":
    unittest.main()
