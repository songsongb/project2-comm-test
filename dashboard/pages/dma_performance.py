"""DMA lab: one filtered measurement scope, four graphs, exact original statistics."""
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from dashboard.presentation import comparison, table
from dashboard.runtime import csv_bytes
from dashboard.ui_components import cache

NUMERIC = ('load', 'session', 'intervals', 'samples_s', 'observed_skip_pct', 'irqs_s', 'acquisition_pct', 'acq_cycles', 'cycles_s', 'excluded')


def figures(rows):
    colors = ('#286a85', '#d59a39')
    result = []
    for field, title, unit in (
        ('samples_s', 'Throughput Comparison', 'pairs/s'),
        ('observed_skip_pct', 'Observed Sample Loss', '관측 누락률 (%)'),
        ('irqs_s', 'Interrupt Frequency', 'IRQ/s'),
        ('acquisition_pct', 'CPU Acquisition Burden', '취득·처리 계측 시간 (%)'),
    ):
        fig = make_subplots(specs=[[{'secondary_y': True}]]) if field == 'acquisition_pct' else go.Figure()
        for load, color in enumerate(colors):
            group = [r for r in rows if r['load'] == load]
            args = dict(x=[r['mode'] for r in group], y=[r[field] for r in group],
                        name=f'LOAD {"ON" if load else "OFF"}', marker_color=color,
                        customdata=[[r['validity'], r['intervals'], r['acq_cycles']] for r in group],
                        hovertemplate='%{x}: %{y}<br>%{customdata[0]} · 구간 %{customdata[1]}<extra>%{fullData.name}</extra>')
            if field == 'acquisition_pct':
                fig.add_trace(go.Bar(**args), secondary_y=False)
                fig.add_trace(go.Scatter(x=args['x'], y=[r['cycles_s'] for r in group],
                                        mode='markers', marker=dict(color=color, symbol='diamond-open', size=10),
                                        name=f'LOAD {load} cycles/s'), secondary_y=True)
            else:
                fig.add_trace(go.Bar(**args))
            for r in group:
                if r[field] is None:
                    fig.add_annotation(x=r['mode'], y=0, text=f'L{load} No data', showarrow=False, yshift=12 + load * 14, font_size=10)
        if field == 'samples_s':
            fig.add_hline(y=10000, line_dash='dash', line_color='#7c8d9a', annotation_text='목표 10,000')
        if field == 'acquisition_pct':
            fig.update_yaxes(title_text='취득 사이클/s (동일 시간 기준)', secondary_y=True, rangemode='tozero')
        fig.update_layout(title=dict(text=title, font_size=17), barmode='group', height=300,
                          margin=dict(l=12, r=12, t=50, b=30), legend=dict(orientation='h', y=-.18),
                          xaxis=dict(categoryorder='array', categoryarray=['Polling', 'Interrupt', 'DMA']),
                          yaxis=dict(title=unit, rangemode='tozero'), uirevision='lab-v1')
        result.append(fig)
    return result


def render(rt, snap):
    st.caption('DMA ACCESS · DMA1 Ch1 순환 버퍼  |  REGISTER MANIPULATION · ADC / DMA / TIM / DWT 직접 제어  |  ADVANTAGE · 동일 조건 6종 비교')
    rows = snap.get('metrics', [])
    scopes = list(dict.fromkeys((r['source'], r['port'], r['session']) for r in rows))
    if scopes:
        scope = st.selectbox('비교할 데이터 출처 · 보드 포트 · 부팅 세션', scopes, index=len(scopes)-1,
                             format_func=lambda s: f'{s[0]} / {s[1]} / Session {s[2]}', key='lab-scope')
    else:
        scope = (None, None, None)
    key = ('lab', rt.state.identity, snap['revisions']['metrics'], scope)
    six, selected, charts = cache().get(key, lambda: build_lab(rows, scope))
    latest = selected[-1] if selected else None
    current = snap['devices']['window']['latest']
    values = [
        ('현재 Mode / LOAD', f"{current['data']['mode']} / {'ON' if current['data']['load'] else 'OFF'}" if current else 'Unknown'),
        ('최근 처리량 · pairs/s', fmt(latest.get('samples_s') if latest else None)),
        ('관측 누락률 · %', fmt(latest.get('observed_skip_pct') if latest else None, 3)),
        ('취득 IRQ/s', fmt(latest.get('irqs_s') if latest else None, 1)),
        ('취득·처리 시간 · %', fmt(latest.get('acquisition_pct') if latest else None, 1)),
        ('최근 비교 유효성', '유효' if latest and latest['eligible'] else 'No data / 제외'),
    ]
    from dashboard.config import MODES
    if current:
        values[0] = ('현재 Mode / LOAD', MODES.get(current['data']['mode'], 'Unknown') + ' / ' + ('ON' if current['data']['load'] else 'OFF'))
    for col, (label, value) in zip(st.columns(6), values):
        col.metric(label, value)
    if latest and not current:
        st.caption('위 성능 수치는 마지막 수신 이력입니다. 현재 Window 데이터는 만료되었습니다.')
    if latest and latest['excluded_reason']:
        st.caption('최근 비교 제외 사유: ' + latest['excluded_reason'])
    with st.container(key='lab-grid'):
        for pair in (charts[:2], charts[2:]):
            for col, fig in zip(st.columns(2), pair):
                with col:
                    st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
    st.caption('0은 실제 관측값이며 No data는 미측정입니다. 설계상 기대 IRQ는 Interrupt 약 10,000/s, DMA 약 312.5/s이며 실측치가 아닙니다.')
    st.caption('acq_permille/10은 취득·처리 코드의 계측 시간 비율입니다. 전체 CPU 사용률이 아닙니다. cycles/s는 acq_cycles 합계/유효 측정 초이며 원본 사이클 합계는 아래 표에 보존합니다.')
    st.subheader('6조건 성능 비교')
    st.dataframe(table(six, numeric=NUMERIC), hide_index=True, width='stretch', height=255)
    st.caption('pairs는 LDR+마이크 동시 샘플 수입니다. 관측 누락률은 TIM4 슬롯 누락만 포함하며 모든 ADC 유실의 절대 손실률이 아닙니다. 통계는 원본 유효 구간과 기존 summarize()로 계산합니다.')
    if st.button('현재 비교 CSV 준비'):
        st.session_state['comparison_export'] = (rt.state.identity, csv_bytes(six), csv_bytes(selected))
    prepared = st.session_state.get('comparison_export')
    if prepared and prepared[0] == rt.state.identity:
        c1, c2 = st.columns(2)
        c1.download_button('6조건 비교 CSV', prepared[1], 'dma_comparison.csv', 'text/csv', on_click='ignore')
        c2.download_button('원본 구간 CSV · 제외 사유 포함', prepared[2], 'dma_intervals.csv', 'text/csv', on_click='ignore')


def fmt(value, digits=0):
    return f'{value:,.{digits}f}' if value is not None else 'Unknown'


def build_lab(rows, scope):
    six, selected = comparison(rows, *scope)
    return six, selected, figures(six)


def experiments(rt):
    with rt.state.lock:
        exp = rt.state.experiment
        metadata = {k: getattr(exp, k) for k in ('id', 'source', 'started_at', 'mode', 'load', 'port', 'session')} if exp else None
    if metadata:
        st.write(metadata)
        if st.button('실험 종료·저장'):
            rt.state.stop_experiment()
            st.rerun()
    else:
        warmup = st.number_input('시작 안정화 시간 (s)', 0.0, 30.0, 2.0)
        if st.button('현재 조건으로 측정 시작'):
            try:
                rt.state.start_experiment(rt.mode, warmup)
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    st.caption('같은 센서 환경·표시/캡처 설정·측정 길이를 유지하세요. 한 실험은 7,200개 보고 구간에서 자동 저장·종료하며 원본 수집은 계속됩니다.')
    # Metadata-only lookup avoids decoding the retained rows of every saved experiment.
    history = rt.storage.experiment_index(30)
    if history:
        st.dataframe(table(history, numeric=('mode', 'load', 'session', 'excluded', 'interval_count')), hide_index=True, width='stretch')
        selected = st.selectbox('저장한 실험', [e['id'] for e in history])
        if st.button('선택 실험 상세 불러오기'):
            st.session_state['selected_experiment'] = rt.storage.artifact(selected)
        item = st.session_state.get('selected_experiment')
        if item and item['id'] == selected:
            st.dataframe(table(item.get('summary', []), numeric=('load', 'intervals', 'duration_s', 'pairs', 'skipped', 'samples_s', 'observed_skip_pct', 'irqs_s', 'acq_cycles', 'acquisition_pct', 'target_hz')), hide_index=True, width='stretch')
            st.download_button('선택 실험 CSV', csv_bytes(item.get('rows', [])), f'experiment_{selected[:8]}.csv', 'text/csv', on_click='ignore')
