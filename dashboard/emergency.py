"""Local preparation only. No network/telephone client and no dispatch API."""
import uuid
from .models import utc_now


def alarm_events(events):
    return [e for e in events if str(e.get("data", {}).get("event", "")).startswith("ALARM_")]


def incident_summary(snap, location="", source_mode="live"):
    lines = ["Laser Guard 사건 요약 — 신고 접수 결과가 아닌 준비 자료"]
    if source_mode != "live":
        lines.append("[DEMO/REPLAY 연습 자료: 실제 사건 아님]")
    lines += ["사용자 입력 위치: " + (location.strip() or "미입력 — 사용자 확인 필요"),
              "현재 수신 상태: " + snap.get("hub_state", "Unknown")]
    alarms = alarm_events(snap.get("events", []))
    if alarms:
        for e in alarms[-5:]:
            d = e.get("data", {})
            lines.append(f"관측 로그: {d.get('event', 'Unknown')} / 노드 {d.get('node', 'Unknown')} / PC 수신 {e.get('received_at', 'Unknown')} / Hub MCU {e.get('mcu_ms', 'Unknown')}ms / 당시 {d.get('state', 'Unknown')} / 출처 {e.get('source', 'Unknown')}")
    else:
        lines.append("관측 로그: 수신된 경보 이벤트 없음")
    lines.append("추가 확인: 실제 침입 여부, 정확한 사건 발생 시각·위치·현장 상황은 확인되지 않았습니다. PC 수신 시각과 MCU 시각은 별개입니다.")
    return "\n".join(lines)


def record_manual_report(storage, snap, location, source_mode, confirmed=False):
    if not confirmed:
        raise ValueError("사용자가 직접 신고했다는 명시적 확인이 필요합니다")
    item = {"id": uuid.uuid4().hex, "created_at": utc_now(), "source": source_mode,
            "kind": "user_declared_report" if source_mode == "live" else "practice_record",
            "user_declared": True, "receipt_verified": False,
            "summary": incident_summary(snap, location, source_mode)}
    storage.save("manual_report", item)
    return item
