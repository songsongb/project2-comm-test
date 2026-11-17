"""No model text reaches UART. Approvals are single use, expire, and bind state."""
import threading
import time
import uuid
from .config import ALLOWED, STATUS_SECONDS, FRESH_SECONDS
from .models import utc_now


def fingerprint(ctx):
    s = ctx.get("status") or {}
    h = ctx.get("hub_state") or {}
    return tuple(s.get(k) for k in ("session", "source", "state", "WINDOW_FLAGS", "DOOR_FLAGS", "WINDOW_MODE")) + (h.get("state"), ctx.get("experiment_active"), ctx.get("safety_epoch"))


class CommandController:
    def __init__(self, state, serial, storage, clock=time.time):
        self.state, self.serial, self.storage = state, serial, storage
        self.clock = clock
        self.lock = threading.RLock()
        self.proposals = {}
        self.current = None
        self.last_query = -float("inf")

    def check(self, command, ctx=None, idle_confirmed=False, baseline_confirmed=False):
        ctx = ctx or self.state.control_context()
        if command not in ALLOWED:
            return False, "허용 목록에 없는 명령"
        if not ctx["connected"]:
            return False, "허브 연결 없음"
        if command in ("STATUS", "HELP"):
            return True, "읽기 전용 조회"
        s, h = ctx.get("status"), ctx.get("hub_state")
        now = self.clock()
        if not s or now - s["at"] > STATUS_SECONDS or s["source"] != "live":
            return False, "최신 실제 STATUS 묶음 필요"
        if not h or now - h["at"] > STATUS_SECONDS or h["state"] != s["state"]:
            return False, "허브 상태 변경/만료"
        # FAULT alone cannot distinguish lost links from a recalibratable sensor.
        if s["state"] != "DISARMED":
            return False, "DISARMED 상태에서만 허용 (FAULT는 수동 점검 필요)"
        if s["WINDOW_FLAGS"] & 7 != 1 or s["DOOR_FLAGS"] & 7 != 1:
            return False, "두 센서 READY 및 비활성 상태 필요"
        if ctx.get("experiment_active") is True or not idle_confirmed:
            return False, "실험/펄스 유휴 상태 사용자 확인 필요"
        if ctx.get("pending_nodes"):
            return False, "허브에 다른 명령 대기 중"
        if command == "CAL" and not baseline_confirmed:
            return False, "광 경로·문 기준 위치·환경 명시적 승인 필요"
        if self.current and self.current["status"] in ("queued", "sent", "awaiting_verification"):
            return False, "처리 중인 명령 존재"
        return True, "실행 가능; MCU 내부 전제 조건은 MCU가 최종 검사"

    def propose(self, command, idle_confirmed=False, baseline_confirmed=False, origin="manual"):
        with self.lock:
            if command in ("STATUS", "HELP"):
                raise ValueError("읽기 전용 명령은 상태 조회 버튼을 사용하세요")
            ctx = self.state.control_context()
            ok, reason = self.check(command, ctx, idle_confirmed, baseline_confirmed)
            if not ok:
                raise ValueError(reason)
            p = {"id": uuid.uuid4().hex, "command": command, "origin": origin,
                 "source": "live", "created_at": utc_now(), "created_pc": self.clock(),
                 "status": "proposed", "approved": False, "fingerprint": fingerprint(ctx),
                 "idle_confirmed": idle_confirmed, "baseline_confirmed": baseline_confirmed,
                 "before": ctx, "acks": {}, "result": "미실행"}
            self.proposals[p["id"]] = p
            self.storage.save("command", p)
            return dict(p)

    def approve(self, proposal_id, approved=False):
        with self.lock:
            p = self.proposals.get(proposal_id)
            if not p or p["status"] != "proposed":
                raise ValueError("없거나 사용된 승인 요청")
            if not approved:
                raise ValueError("사용자 승인 필요")
            if self.current and self.current["status"] in ("queued", "sent", "awaiting_verification"):
                raise ValueError("처리 중인 명령 존재")
            p["approved"] = True
            try:
                self._validate(p)
            except ValueError as exc:
                self._finish(p, "blocked", str(exc))
                raise
            p.update(status="queued", approved_at=utc_now())
            self.current = p
            self.storage.save("command", p)
            try:
                self.serial.enqueue("hub", lambda ser: self._write(p, ser))
            except Exception as exc:
                self._finish(p, "failed", str(exc))
                raise
            return p["id"]

    def _validate(self, p):
        if self.clock() - p["created_pc"] > 20:
            raise ValueError("승인 만료: 상태 조회 후 다시 제안하세요")
        ctx = self.state.control_context()
        # Exclude the current queued command from duplicate checking only.
        current, self.current = self.current, None
        try:
            ok, reason = self.check(p["command"], ctx, p["idle_confirmed"], p["baseline_confirmed"])
        finally:
            self.current = current
        if not ok or fingerprint(ctx) != tuple(p["fingerprint"]):
            raise ValueError(reason if not ok else "승인 이후 상태 변경")

    def _write(self, p, ser):
        with self.lock, self.state.lock:
            try:
                if p["status"] != "queued" or not p["approved"]:
                    raise ValueError("유효한 단일 승인 없음")
                self._validate(p)
                if ser is None:
                    raise ValueError("전송 전 포트 연결 끊김")
                payload = (p["command"] + "\r\n").encode("ascii")
                # A partial write is uncertain; it is never retried.
                p["sent_pc"] = self.clock()
                if ser.write(payload) != len(payload):
                    raise IOError("부분 전송: 결과 확인 불가, 재전송 금지")
                p.update(status="sent", sent_at=utc_now(), before=self.state.control_context())
                self.storage.save("command", p)
            except Exception as exc:
                self._finish(p, "unknown" if p.get("sent_pc") else "blocked", str(exc))

    def query(self, command="STATUS"):
        with self.lock:
            if command not in ("STATUS", "HELP") or self.clock() - self.last_query < 1:
                return False
            ok, _ = self.check(command)
            if not ok:
                return False
            self.last_query = self.clock()
            def send(ser):
                if ser is not None:
                    ser.write((command + "\r\n").encode("ascii"))
            self.serial.enqueue("hub", send)
            return True

    def _finish(self, p, status, result):
        p.update(status=status, result=result, ended_at=utc_now())
        self.storage.save("command", p)

    def on_record(self, r):
        with self.lock:
            p = self.current
            if not p or p["status"] not in ("sent", "awaiting_verification") or r.source != "live":
                return
            if r.ingested_at < p["sent_pc"]:
                return
            watched = ("hub", "window", "door") if p["command"] == "CAL" else ("hub", "window")
            if r.kind == "BOOT" and r.device in watched:
                self._finish(p, "unknown", "명령 후 장치 재부팅: 요청 결과 확인 불가")
                return
            if r.kind == "HUB":
                d = r.data
                if d["event"] in ("CMD_BUSY_OR_ARMED", "BAD_COMMAND"):
                    self._finish(p, "failed", d["event"])
                    return
                if d["event"] in ("CMD_ACK", "CMD_REJECT", "CMD_TIMEOUT"):
                    cmd = p["command"]
                    typ = 0x82 if cmd == "CAL" else 0x80 if cmd.startswith("MODE") else 0x83
                    val = 0 if cmd == "CAL" else int(cmd[-1])
                    targets = (1, 2) if cmd == "CAL" else (1,)
                    if d["node"] in targets and (d["command_type"], d["command_value"]) == (typ, val):
                        p["acks"][str(d["node"])] = d["event"]
                        if d["event"] != "CMD_ACK":
                            self._finish(p, "failed", d["event"])
                            return
                        if len(p["acks"]) == len(targets):
                            p.update(status="awaiting_verification", ack_pc=self.clock())
                        self.storage.save("command", p)
            self._verify(p)

    def _verify(self, p):
        if p["status"] != "awaiting_verification":
            return
        ctx = self.state.control_context()
        s, w = ctx.get("status"), ctx.get("window")
        if s and s["session"] != p["before"]["status"]["session"]:
            self._finish(p, "unknown", "허브 세션 변경: 요청 결과 확인 불가")
            return
        for device in ("window", "door") if p["command"] == "CAL" else ("window",):
            before, after = p["before"].get(device), ctx.get(device)
            if before and after and before["session"] != after["session"]:
                self._finish(p, "unknown", "센서 세션 변경: 요청 결과 확인 불가")
                return
        if not s or s["at"] <= p["ack_pc"] or self.clock() - s["at"] > STATUS_SECONDS:
            return
        p["after"] = ctx
        cmd = p["command"]
        ready = s["state"] == "DISARMED" and s["WINDOW_FLAGS"] & 7 == 1 and s["DOOR_FLAGS"] & 7 == 1
        fresh_window = (w and w["source"] == "live" and w["ingested_at"] > p["ack_pc"] and
                        self.clock() - w["ingested_at"] <= FRESH_SECONDS and w["data"]["ready"])
        if cmd.startswith("MODE"):
            match = fresh_window and s["WINDOW_MODE"] == int(cmd[-1]) and w["data"]["mode"] == int(cmd[-1])
        elif cmd.startswith("LOAD"):
            match = fresh_window and w["data"]["load"] == int(cmd[-1])
        else:
            door = ctx.get("door")
            match = (fresh_window and door and door["source"] == "live" and
                     door["ingested_at"] > p["ack_pc"] and self.clock() - door["ingested_at"] <= FRESH_SECONDS and
                     door["data"]["ready"] and not door["data"]["fault"])
        if ready and match:
            self._finish(p, "verified", "요청 상태를 STATUS·센서 로그로 확인. 원인 장애 복구 여부는 별도 관측 필요")

    def tick(self):
        with self.lock:
            p = self.current
            if p and p["status"] in ("sent", "awaiting_verification"):
                ctx = self.state.control_context()
                if not ctx["connected"] or (ctx.get("status") and ctx["status"]["session"] != p["before"]["status"]["session"]):
                    self._finish(p, "unknown", "연결/허브 세션 변경: 결과 확인 불가")
                elif self.clock() - p["sent_pc"] > 12:
                    self._finish(p, "unknown", "ACK 미수신 또는 후속 계측 부족: 확인 불가; 자동 재시도 없음")
