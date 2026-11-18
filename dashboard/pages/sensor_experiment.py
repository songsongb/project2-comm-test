"""Optional sensor detail panel. Executed only when the user opens it."""
from collections import defaultdict
import streamlit as st
import plotly.graph_objects as go
from dashboard.presentation import table, extrema_points
from dashboard.runtime import csv_bytes
from dashboard.ui_components import cache


def render(rt, snap):
    st.caption('수동 계측만 지원합니다. PLOT은 5Hz 표시용 필터값, TRACE는 고속 원파형입니다. 레이저·릴레이는 제어하지 않습니다.')
    if rt.mode == 'live':
        for col, label, command in zip(st.columns(3), ('PLOT 표시 시작', 'PLOT 표시 중지', 'TRACE 캡처 요청'), ('PLOT', 'PLOTOFF', 'TRACE')):
            if col.button(label):
                try:
                    rt.serial.enqueue('window', lambda ser, cmd=command: ser.write((cmd + '\r\n').encode()) if ser else None)
                except (ValueError, RuntimeError) as exc:
                    st.error(str(exc))
    latest = snap['devices']['window']['latest']
    d = latest.get('data', {}) if latest else {}
    for col, label, field in zip(st.columns(3), ('마이크 RMS · ADC counts', 'LDR Threshold', 'LDR 기준값'), ('mic_rms', 'ldr_threshold', 'lit_baseline')):
        col.metric(label, d.get(field, 'Unknown'))
    if snap.get('trace_status'):
        st.caption('최근 TRACE 보고: ' + str(snap['trace_status']))
    data_key = (rt.state.identity, snap['revisions']['sensors'])
    groups = defaultdict(list)
    for row in snap.get('plots', []):
        groups[(row.get('source'), row.get('session'))].append(row)
    if groups:
        def ldr_chart():
            fig = go.Figure()
            for (source, session), rows in groups.items():
                visible = extrema_points(rows, 'ldr')
                fig.add_trace(go.Scatter(x=[r.get('time_ms') for r in visible], y=[r.get('ldr') for r in visible], name=f'{source}/S{session}', connectgaps=False))
            fig.update_layout(height=270, xaxis_title='Window MCU ms', yaxis_title='LDR', margin=dict(t=20, b=30), uirevision='ldr')
            return fig
        st.plotly_chart(cache().get(('ldr', data_key), ldr_chart), width='stretch', key='ldr-plot')
    traces = snap.get('traces', [])
    if traces:
        selected = st.selectbox('TRACE 기록', [t['id'] for t in traces], index=len(traces)-1,
                                format_func=lambda i: next(f"{t['received_at']} · {t['source']} · {t['status']}" for t in traces if t['id'] == i))
        trace = next(t for t in traces if t['id'] == selected)
        def trace_chart():
            fig = go.Figure()
            # At most 2001 points per capture: keep every sample and every gap.
            for field in ('ldr', 'mic'):
                fig.add_trace(go.Scatter(x=[r['time_ms'] for r in trace['rows']], y=[r[field] for r in trace['rows']], name=field, connectgaps=False))
            fig.add_hline(y=trace['meta']['threshold'], line_dash='dot')
            fig.add_vline(x=0, line_dash='dash')
            start = None
            for r in trace['rows'] + [{'gap': False, 'time_ms': trace['meta']['last'] * 1000 / trace['meta']['sample_hz'] + .1}]:
                if r['gap'] and start is None:
                    start = r['time_ms']
                elif not r['gap'] and start is not None:
                    fig.add_vrect(x0=start, x1=r['time_ms'], fillcolor='red', opacity=.15, line_width=0)
                    start = None
            fig.update_layout(height=300, xaxis_title='감지 onset 기준 ms', yaxis_title='ADC counts', uirevision=trace['id'])
            return fig
        st.plotly_chart(cache().get(('trace', data_key, selected), trace_chart), width='stretch', key='trace-wave')
        st.caption(f"{trace['status']} · 누락 슬롯 {sum(r['gap'] for r in trace['rows'])} · {trace['reason'] or ''}")
        if st.button('TRACE CSV 준비'):
            st.session_state['trace_csv'] = (selected, csv_bytes(trace['rows']))
        export = st.session_state.get('trace_csv')
        if export and export[0] == selected:
            st.download_button('TRACE CSV', export[1], 'trace.csv', 'text/csv', on_click='ignore')
    trials = snap.get('trials', [])
    st.subheader('TRIAL · 유효 시험만 성공률 집계')
    if trials:
        by_condition = defaultdict(list)
        for trial in trials:
            by_condition[(trial.get('source'), trial.get('mode'), trial.get('load'), trial.get('command_ms'))].append(trial)
        summary = []
        for (source, mode, load, width), rows in by_condition.items():
            valid = [r for r in rows if r.get('valid') == 1]
            summary.append(dict(source=source, mode=mode, load=load, pulse_ms=width, valid=len(valid), invalid=len(rows)-len(valid),
                                hit_pct=100*sum(r.get('hit', 0) for r in valid)/len(valid) if valid else None))
        st.dataframe(table(summary, numeric=('mode', 'load', 'pulse_ms', 'valid', 'invalid', 'hit_pct')), hide_index=True, width='stretch')
        if st.button('TRIAL CSV 준비'):
            st.session_state['trial_csv'] = (rt.state.identity, csv_bytes(trials))
        export = st.session_state.get('trial_csv')
        if export and export[0] == rt.state.identity:
            st.download_button('TRIAL CSV', export[1], 'trials.csv', 'text/csv', on_click='ignore')
    else:
        st.info('TRIAL 수신 이력이 없습니다.')
    st.caption('command_ms는 PB0 기준 펄스 폭이며 센서 검출 지연이 아닙니다. 무효 시험은 분모에서 제외합니다.')
