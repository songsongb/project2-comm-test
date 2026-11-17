import streamlit as st
import pandas as pd
import time
from dashboard.config import LABELS, MODES
from dashboard.protocol_parser import decode_flags


def render(rt, snap):
    st.subheader("시스템 상태")
    st.metric("Central Hub", snap["hub_state"])
    status = snap["status"]
    cols = st.columns(4)
    for col, (device, info) in zip(cols, snap["devices"].items()):
        with col:
            st.markdown(f"**{LABELS[device]}**")
            st.write("수신 중" if info["fresh"] else ("대기/수신 만료" if info["connected"] else "Disconnected"))
            st.caption(f"{info['port'] or '포트 미선택'} · 세션 {info['session']}")
            st.caption(f"마지막 수신: {info['last_received'] or 'Unknown'}")
            if info["error"]:
                st.caption("연결 오류: " + info["error"])
            latest = info["latest"]
            if device in ("window", "door"):
                if latest:
                    d = latest["data"]
                    st.write("READY" if d["ready"] else "NOT READY")
                    if device == "window":
                        st.write(MODES[d["mode"]] + f" · LOAD {d['load']}")
                    else:
                        st.write(f"ACTIVE: {bool(d['open'])} · SENSOR_FAULT: {bool(d['fault'])}")
                else:
                    st.write("센서 상태: Unknown")
    if status and time.time() - status["at"] <= 2.5 and snap["devices"]["hub"]["fresh"]:
        st.metric("허브가 보고한 Window 모드", MODES.get(status["WINDOW_MODE"], "Unknown"))
        st.caption("허브가 보고한 센서 플래그 (통신 경로는 노드 USB 연결과 별개)")
        st.dataframe(pd.DataFrame([
            {"node": "Window", **decode_flags(status["WINDOW_FLAGS"])},
            {"node": "Door", **decode_flags(status["DOOR_FLAGS"])}]), hide_index=True, width="stretch")
    st.caption("UART ORE · DMA 오버런 · MCU 전체 CPU 사용률: Not measured / 추가 계측 필요")
    st.subheader("최근 이벤트")
    if snap["events"]:
        st.dataframe(pd.DataFrame([{"PC 수신 시각": r["received_at"], "source": r["source"],
                                   "MCU ms": r["mcu_ms"], **r["data"]} for r in snap["events"][-40:]][::-1]), hide_index=True, width="stretch")
    else:
        st.info("아직 수신된 허브 이벤트가 없습니다.")
