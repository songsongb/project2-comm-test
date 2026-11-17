"""Run from repository root: python -m streamlit run dashboard/app.py"""
from pathlib import Path
import atexit
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st
from dashboard.config import LABELS, ROOT
from dashboard.replay import Replay, read_jsonl
from dashboard.runtime import Runtime
from dashboard.serial_manager import ports
from dashboard.pages import overview, dma_performance, sensor_experiment, ai_diagnostics, recovery_control

st.set_page_config(page_title="DMA Lab · Laser Guard", page_icon="📊", layout="wide")


@st.cache_resource
def services():
    runtime = Runtime()
    atexit.register(runtime.close)
    return runtime


rt = services()


def sidebar():
    with st.sidebar:
        st.markdown("### DMA LAB / PC CONSOLE")
        st.caption("Embedded Systems Project 2")
        mode_labels = {"live": "실제 USB Serial", "demo": "Demo · 합성 데이터", "replay": "로그 파일 재생"}
        mode = st.selectbox("입력 소스", list(mode_labels), index=list(mode_labels).index(rt.mode), format_func=mode_labels.get)
        if mode != rt.mode:
            rt.switch_mode(mode)
            st.rerun()
        if mode == "live":
            discovered = ports()
            with st.expander("검색된 시리얼 포트", expanded=False):
                st.write(discovered or "검색된 포트 없음")
            device = st.selectbox("장치 역할 (수동 확인)", list(LABELS), format_func=LABELS.get)
            available = [p["port"] for p in discovered]
            selected = st.selectbox("포트 선택", ["직접 입력"] + available)
            port = st.text_input("COM 포트 또는 장치 경로", "" if selected == "직접 입력" else selected)
            st.caption("115200bps · 8N1 · 각 장치에 서로 다른 포트 사용")
            c1, c2 = st.columns(2)
            if c1.button("연결"):
                try:
                    rt.serial.connect(device, port.strip())
                except (ValueError, RuntimeError) as exc:
                    st.error(str(exc))
            if c2.button("해제"):
                rt.serial.disconnect(device)
        else:
            speed = st.select_slider("재생 속도", [0.5, 1.0, 2.0, 4.0, 10.0], value=4.0)
            entries = None
            if mode == "replay":
                uploaded = st.file_uploader("원본 JSONL 로그 (source 필수)", type="jsonl")
                if uploaded:
                    try:
                        entries = read_jsonl(uploaded.getvalue().decode("utf-8-sig"))
                    except (ValueError, UnicodeError) as exc:
                        st.error(str(exc))
            if st.button("Demo 시작" if mode == "demo" else "재생 시작", disabled=mode == "replay" and entries is None):
                rt.switch_mode(mode)
                if mode == "demo":
                    entries = read_jsonl((ROOT / "samples" / "synthetic_demo.jsonl").read_text(encoding="utf-8"))
                rt.replay = Replay(entries, rt.receive, speed, demo=mode == "demo")
                rt.replay.start()
            if st.button("재생 중지") and rt.replay:
                rt.replay.close()
        st.divider()
        st.caption("원본 시각은 UTC ISO 8601. MCU ms와 PC 수신 시각은 서로 다른 시간 기준입니다.")
        st.caption("SQLite: " + str(rt.data_dir / "dashboard.sqlite3"))
        st.caption("이 프로세스의 모든 브라우저 세션은 수집기와 제어 상태를 공유합니다.")


@st.fragment(run_every="1s")
def dashboard_view():
    snap = rt.state.snapshot()
    st.title("DMA Performance & AI Diagnostics")
    st.caption("LASER GUARD  /  REGISTER-LEVEL ACQUISITION  /  FOUR-BOARD TELEMETRY")
    if rt.mode != "live":
        sources = sorted({r["source"] for r in snap["records"]})
        st.warning("DEMO / REPLAY — 실제 현재 하드웨어 상태가 아닙니다 · " + (", ".join(sources) or "재생 대기"))
    else:
        st.caption("LIVE · 실제 수신 로그만 표시 · 미연결 장치는 Unknown / Disconnected")
    if rt.replay:
        st.caption(f"재생 {rt.replay.position}/{len(rt.replay.entries)}" + (f" · 오류: {rt.replay.error}" if rt.replay.error else ""))
    if rt.queue_drops:
        st.error(f"PC 수집 큐 초과로 {rt.queue_drops}행 유실. 해당 측정은 공정한 비교에서 제외하세요.")
    if rt.error:
        st.error("처리 오류: " + rt.error)
    tabs = st.tabs(["Overview", "DMA Performance", "Sensor & Experiment", "AI Diagnostics", "Recovery & Control"])
    for tab, module in zip(tabs, [overview, dma_performance, sensor_experiment, ai_diagnostics, recovery_control]):
        with tab:
            module.render(rt, snap)
    with st.expander("원본 로그 / 내보내기"):
        for record in snap["records"][-80:]:
            st.text(f"{record['received_at']} [{record['source']}/{record['device']}/{record['port']}/S{record['session']}] {record['raw']}")
        # Export from SQLite: includes data outside the bounded UI ring (latest 10,000 rows).
        logs = rt.storage.raw_records()
        payload = "\n".join(json.dumps(r, ensure_ascii=False) for r in logs)
        st.download_button("원본 JSONL 다운로드 (최근 10,000행)", payload, "raw_records.jsonl", "application/x-ndjson")


def main():
    sidebar()
    dashboard_view()


# Explicit navigation prevents helpers under pages/ from becoming blank auto-pages.
st.navigation([st.Page(main, title="DMA Dashboard")], position="hidden").run()
