import streamlit as st
import pandas as pd
import plotly.express as px
from dashboard.metrics import summarize
from dashboard.runtime import csv_bytes


def render(rt, snap):
    st.subheader("DMA 성능 계측 · 목표 10,000 pairs/s")
    st.caption("1 pair = 광센서 + 마이크 동시 샘플. 관측 skipped는 TIM4 슬롯 간격 기반이며 모든 ADC 유실을 검출하지 않습니다.")
    rows = snap["metrics"]
    summary = summarize(rows)
    if not rows:
        st.info("STM32 #1 STAT를 연결하거나 Demo/Replay를 시작하세요.")
    else:
        latest = rows[-1]
        cols = st.columns(4)
        cols[0].metric("최근 처리량 (pairs/s)", f"{latest['samples_s']:,.0f}" if latest["samples_s"] is not None else "Unknown")
        cols[1].metric("관측 누락률 (%)", f"{latest['observed_skip_pct']:.3f}" if latest["observed_skip_pct"] is not None else "Unknown")
        cols[2].metric("취득·처리 계측 구간 (%)", f"{latest['acquisition_pct']:.1f}")
        cols[3].metric("현재 MODE / LOAD", f"{latest['mode_name']} / {latest['load']}")
        if latest["excluded_reason"]:
            st.warning("최근 구간 비교 제외: " + latest["excluded_reason"])
        if not snap["devices"]["window"]["latest"]:
            st.warning("최신 STAT가 없습니다. 위 수치는 마지막 수신 이력입니다.")
        data = pd.DataFrame(rows)
        # Do not connect graph lines across reboot sessions or different input sources.
        data["series"] = data["source"] + "/S" + data["session"].astype(str) + "/" + data["mode_name"] + "/L" + data["load"].astype(str)
        fig = px.scatter(data, x="received_at", y="samples_s", color="series", labels={"received_at": "PC 수신 시각", "samples_s": "pairs/s"})
        fig.add_hline(y=10000, line_dash="dash", annotation_text="목표 10 kHz")
        st.plotly_chart(fig, width="stretch", key="throughput-time")
        st.caption(f"비교 가능 {sum(r['eligible'] for r in rows)} / 전체 {len(rows)} 구간 · 최초/전환/안정화/보고 누락/미준비 제외")
        if summary:
            df = pd.DataFrame(summary)
            df["조건"] = df["mode"] + " / LOAD " + df["load"].astype(str)
            c1, c2 = st.columns(2)
            for col, metric, title in ((c1, "samples_s", "처리량 (pairs/s)"), (c2, "observed_skip_pct", "관측 누락률 (%)"),
                                       (c1, "irqs_s", "취득 인터럽트 (IRQ/s)"), (c2, "acquisition_pct", "취득·처리 계측 구간 시간 비율 (%)")):
                with col:
                    st.plotly_chart(px.bar(df, x="조건", y=metric, color="source", title=title), width="stretch", key=metric)
            st.dataframe(df, hide_index=True, width="stretch")
            st.download_button("비교 통계 CSV", csv_bytes(summary), "dma_summary.csv", "text/csv")
        st.download_button("구간 원자료 CSV (제외 사유 포함)", csv_bytes(rows), "dma_intervals.csv", "text/csv")
    st.info("Interrupt는 ADC EOC마다, DMA는 32 pairs Half/Full 블록마다 인터럽트가 발생합니다. 이상적 기대치는 각각 약 10,000 IRQ/s와 312.5 IRQ/s이며 실측 결과가 아닙니다. Polling의 취득 IRQ는 0이며 다른 MCU 인터럽트는 집계하지 않습니다.")
    st.caption("acq_cycles는 DWT CYCCNT로 잰 취득·처리 경로의 사이클 수입니다. acq_permille/10은 해당 구간의 시간 비율이며 전체 CPU 사용률이 아닙니다.")
    st.subheader("실험 구간 관리")
    if snap["experiment"]:
        exp = snap["experiment"]
        st.write(f"진행 중: {exp['id'][:8]} · MODE {exp['mode']} · LOAD {exp['load']} · {exp['started_at']}")
        if st.button("실험 종료·저장"):
            rt.state.stop_experiment()
            st.rerun()
    else:
        warmup = st.number_input("시작 안정화 시간 (s)", 0.0, 30.0, 2.0)
        if st.button("현재 조건으로 측정 시작"):
            try:
                rt.state.start_experiment(rt.mode, warmup)
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    history = rt.storage.history("experiment", 50)
    if history:
        options = {e["id"]: f"{e['started_at']} · {e['source']} · MODE {e['mode']} / LOAD {e['load']}" for e in history}
        selected = st.selectbox("저장한 실험", options, format_func=options.get)
        exp = next(e for e in history if e["id"] == selected)
        st.write({k: v for k, v in exp.items() if k not in ("rows", "summary")})
        st.dataframe(pd.DataFrame(exp["summary"]), width="stretch", hide_index=True)
        st.download_button("선택 실험 CSV", csv_bytes(exp["rows"]), f"experiment_{selected[:8]}.csv", "text/csv")
