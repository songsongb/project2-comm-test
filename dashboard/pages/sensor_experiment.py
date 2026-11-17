import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dashboard.runtime import csv_bytes


def render(rt, snap):
    st.subheader("센서와 레이저 차단 관측")
    st.caption("이 화면은 센서 수집과 로그 표시만 수행합니다. 레이저·릴레이 제어는 제공하지 않습니다.")
    if snap["trace_status"]:
        st.caption("최근 TRACE 상태: " + str(snap["trace_status"]))
    if rt.mode == "live":
        c1, c2, c3 = st.columns(3)
        for col, label, command in ((c1, "PLOT 표시 시작", "PLOT"), (c2, "PLOT 표시 중지", "PLOTOFF"), (c3, "TRACE 캡처 요청", "TRACE")):
            with col:
                if st.button(label):
                    try:
                        # Fixed, non-actuating instrumentation commands on Window VCP only.
                        rt.serial.enqueue("window", lambda ser, cmd=command: ser.write((cmd + "\r\n").encode()) if ser else None)
                    except (ValueError, RuntimeError) as exc:
                        st.error(str(exc))
    latest = snap["devices"]["window"]["latest"]
    c1, c2, c3 = st.columns(3)
    c1.metric("마이크 RMS (ADC counts)", latest["data"]["mic_rms"] if latest else "Unknown")
    c2.metric("LDR 임계값", latest["data"]["ldr_threshold"] if latest else "Unknown")
    c3.metric("LDR 밝은 기준값", latest["data"]["lit_baseline"] if latest else "Unknown")
    if snap["plots"]:
        df = pd.DataFrame(snap["plots"])
        df["series"] = df["source"] + "/S" + df["session"].astype(str)
        st.plotly_chart(px.line(df, x="time_ms", y="ldr", color="series", labels={"time_ms": "Window MCU ms", "ldr": "LDR 저속 필터 표시값"}), width="stretch", key="ldr-plot")
        st.caption("PLOT은 5 Hz 표시용 필터값입니다. 고속 원파형은 TRACE를 사용하세요.")
    else:
        st.info("PLOT 로그를 기다리는 중입니다.")
    traces = snap["traces"]
    if traces:
        selection = st.selectbox("TRACE 기록", [t["id"] for t in traces], format_func=lambda i: next(f"{t['received_at']} · {t['source']} · {t['status']}" for t in traces if t["id"] == i))
        trace = next(t for t in traces if t["id"] == selection)
        df = pd.DataFrame(trace["rows"])
        fig = go.Figure()
        for field, label in (("ldr", "LDR"), ("mic", "Microphone")):
            fig.add_trace(go.Scatter(x=df["time_ms"], y=df[field], name=label, connectgaps=False, mode="lines"))
        fig.add_hline(y=trace["meta"]["threshold"], line_dash="dot", annotation_text="LDR threshold")
        fig.add_vline(x=0, line_dash="dash")
        # Shade gaps including absent rows caused by PC-side loss.
        start = None
        for row in trace["rows"] + [{"gap": False, "time_ms": df["time_ms"].iloc[-1] + .1}]:
            if row["gap"] and start is None:
                start = row["time_ms"]
            elif not row["gap"] and start is not None:
                fig.add_vrect(x0=start, x1=row["time_ms"], fillcolor="red", opacity=.15, line_width=0)
                start = None
        fig.update_layout(xaxis_title="감지 onset 기준 시간 (ms)", yaxis_title="ADC counts")
        st.plotly_chart(fig, width="stretch", key="trace-wave")
        st.write(f"캡처: {trace['status']} · 누락 슬롯: {int(df['gap'].sum())} · {trace['reason'] or ''}")
        st.download_button("TRACE CSV", csv_bytes(trace["rows"]), "trace.csv", "text/csv")
    st.subheader("TRIAL 감지 실험")
    trials = snap["trials"]
    if trials:
        valid = [t for t in trials if t["valid"]]
        hits = sum(t["hit"] for t in valid)
        c1, c2, c3 = st.columns(3)
        c1.metric("유효 시험", len(valid))
        c2.metric("무효 시험 (분모에서 제외)", len(trials) - len(valid))
        c3.metric("유효 시험 감지 성공률", f"{hits / len(valid):.1%}" if valid else "Unknown")
        df = pd.DataFrame(trials)
        groups = []
        for (source, mode, load, width), subset in df.groupby(["source", "mode", "load", "command_ms"]):
            v = subset[subset["valid"] == 1]
            groups.append({"source": source, "mode": mode, "load": load, "pulse_ms": width,
                           "valid": len(v), "invalid": len(subset) - len(v),
                           "hit_pct": 100 * v["hit"].mean() if len(v) else None})
        st.dataframe(pd.DataFrame(groups), hide_index=True, width="stretch")
        st.dataframe(df, hide_index=True, width="stretch")
        st.download_button("TRIAL CSV", csv_bytes(trials), "trials.csv", "text/csv")
    else:
        st.info("TRIAL 수신 이력이 없습니다. command_ms는 PB0에서 측정한 기준 펄스 폭이며 센서 검출 지연이 아닙니다.")
