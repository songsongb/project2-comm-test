"""Local Laser Guard console. UI mode never owns or reconnects serial ports."""
from pathlib import Path
from itertools import islice
import atexit
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st
from dashboard.config import LABELS, ROOT
from dashboard.replay import Replay, read_jsonl
from dashboard.runtime import Runtime
from dashboard.serial_manager import ports
from dashboard.presentation import table
from dashboard.ui_components import CSS, lazy_panel
from dashboard.pages import overview, dma_performance, sensor_experiment, recovery_control

st.set_page_config(page_title='Laser Guard · Security & DMA Lab', page_icon='◈', layout='wide')


@st.cache_resource
def services():
    runtime = Runtime()
    atexit.register(runtime.close)
    return runtime


@st.cache_data(ttl=10, max_entries=1)
def discovered_ports():
    return ports()


rt = services()


def sidebar():
    with st.sidebar:
        st.markdown('### LASER GUARD')
        st.caption('4-BOARD TELEMETRY CONSOLE')
        labels = {'live': '실제 USB Serial', 'demo': 'Demo · 합성 데이터', 'replay': '로그 파일 재생'}
        mode = st.selectbox('입력 소스', list(labels), index=list(labels).index(rt.mode), format_func=labels.get)
        if mode != rt.mode:
            rt.switch_mode(mode)
            for key in ('raw_export', 'comparison_export', 'trace_csv', 'trial_csv', 'selected_experiment'):
                st.session_state.pop(key, None)
            st.rerun()
        interval = st.selectbox('화면 갱신 간격 (초)', [2, 3, 5], index=1, key='refresh_interval')
        st.caption('수집·저장·STATUS 조회는 화면 주기와 독립적으로 계속됩니다.')
        if mode == 'live':
            found = discovered_ports()
            if st.button('포트 다시 검색'):
                discovered_ports.clear()
                st.rerun()
            device = st.selectbox('장치 역할 (수동 확인)', list(LABELS), format_func=LABELS.get)
            selected = st.selectbox('포트 선택', ['직접 입력'] + [p['port'] for p in found])
            port = st.text_input('COM 포트 또는 장치 경로', '' if selected == '직접 입력' else selected)
            st.caption('115200bps · 8N1 · 각 장치별 다른 USB 포트')
            c1, c2 = st.columns(2)
            if c1.button('연결'):
                try:
                    rt.serial.connect(device, port.strip())
                except (ValueError, RuntimeError) as exc:
                    st.error(str(exc))
            if c2.button('해제'):
                rt.serial.disconnect(device)
        else:
            speed = st.select_slider('재생 속도', [.5, 1., 2., 4., 10.], value=4.)
            entries = None
            if mode == 'replay':
                upload = st.file_uploader('원본 JSONL 로그 (source 필수)', type='jsonl')
                if upload:
                    try:
                        entries = read_jsonl(upload.getvalue().decode('utf-8-sig'))
                    except (ValueError, UnicodeError) as exc:
                        st.error(str(exc))
            if st.button('Demo 시작' if mode == 'demo' else '재생 시작', disabled=mode == 'replay' and entries is None):
                rt.switch_mode(mode)
                if mode == 'demo':
                    entries = read_jsonl((ROOT / 'samples/synthetic_demo.jsonl').read_text(encoding='utf-8'))
                rt.replay = Replay(entries, rt.receive, speed, demo=mode == 'demo')
                rt.replay.start()
            if st.button('재생 중지') and rt.replay:
                rt.replay.close()
        st.divider()
        st.caption('PC UTC 수신 시각과 MCU ms는 별도 시간 기준입니다.')
        st.caption('SQLite: ' + str(rt.data_dir / 'dashboard.sqlite3'))
        st.caption('화면 모드 전환은 연결과 데이터를 유지합니다. 입력 소스 변경은 연결을 닫고 현재 뷰를 초기화하며 DB는 보존합니다.')
    return interval


def raw_panel():
    with rt.state.lock:
        recent = [r.as_dict() for r in islice(reversed(rt.state.records), 30)]
    st.dataframe(table(recent, columns=['received_at', 'device', 'port', 'source', 'session', 'raw'], numeric=('session',)), hide_index=True, width='stretch')
    sources = {'live': ('live',), 'demo': ('demo',), 'replay': ('replay-live', 'replay-synthetic')}[rt.mode]
    st.caption('원본 로그는 조회 버튼을 눌렀을 때만 DB에서 읽습니다. 현재 입력 소스의 최근 2,000행을 준비합니다. 전체 로그는 export_logs CLI로 스트리밍 내보내세요.')
    if st.button('원본 JSONL 다운로드 준비'):
        st.session_state['raw_export'] = (rt.state.identity, rt.mode, rt.storage.raw_jsonl(sources, 2000))
    prepared = st.session_state.get('raw_export')
    if prepared and prepared[:2] == (rt.state.identity, rt.mode):
        st.download_button('원본 JSONL 다운로드', prepared[2], f'raw_{rt.mode}.jsonl', 'application/x-ndjson', on_click='ignore')


def main():
    interval = sidebar()
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown('<div class="lg-brand">LASER GUARD / EMBEDDED SYSTEMS PROJECT 2</div>', unsafe_allow_html=True)
    screen = st.radio('화면 모드', ['보안 관제', 'DMA 성능 분석'], horizontal=True, label_visibility='collapsed', key='screen_mode')
    st.title('Security Monitoring' if screen == '보안 관제' else 'DMA Performance Lab')
    if rt.mode == 'live':
        st.caption('LIVE · 실제 수신 자료만 표시 · 미연결·만료 상태는 Unknown')
    else:
        st.warning('DEMO / REPLAY — 합성 또는 과거 로그입니다. 실제 현재 상태·성능·사건을 의미하지 않습니다.')

    @st.fragment(run_every=f'{interval}s')
    def live_view():
        if rt.replay:
            st.caption(f'재생 {rt.replay.position}/{len(rt.replay.entries)} · 처리 대기 {rt.queue.qsize()}행' + (f' · 오류 {rt.replay.error}' if rt.replay.error else ''))
        if rt.queue_drops:
            st.error(f'PC 큐 초과: {rt.queue_drops}행 유실. 해당 비교 구간을 점검하세요.')
        if rt.error:
            st.error('처리 오류: ' + rt.error)
        view = 'security' if screen == '보안 관제' else 'dma'
        snap = rt.state.snapshot(view=view)
        (overview if view == 'security' else dma_performance).render(rt, snap)
    live_view()

    if screen == '보안 관제':
        panel = lazy_panel('경찰 신고 지원 · 112', 'emergency-panel')
        if panel.open:
            with panel:
                overview.emergency_panel(rt)
        panel = lazy_panel('장치 연결 · 통신 진단 · 원본 이벤트', 'security-details')
        if panel.open:
            with panel:
                snap = rt.state.snapshot(view='security')
                st.dataframe(table([{'device': d, **{k: i.get(k) for k in ('connected', 'fresh', 'port', 'last_received', 'age_s', 'error')}} for d, i in snap['devices'].items()], numeric=('age_s',), boolean=('connected', 'fresh')), hide_index=True, width='stretch')
                st.caption('UART ORE · DMA 오버런 · 실제 릴레이/RGB/부저 상태: Not measured. 규칙 탐지는 유지하며 LLM 기능은 제거했습니다.')
                raw_panel()
    else:
        panel = lazy_panel('센서 파형 · TRACE · TRIAL', 'sensor-panel')
        if panel.open:
            with panel:
                @st.fragment(run_every=f'{interval}s')
                def sensor_view():
                    sensor_experiment.render(rt, rt.state.snapshot(view='sensors', details=True))
                sensor_view()
        panel = lazy_panel('실험 구간 관리 · 저장 결과 · CSV', 'experiment-panel')
        if panel.open:
            with panel:
                dma_performance.experiments(rt)
        panel = lazy_panel('장치 설정 및 실험 제어', 'control-panel')
        if panel.open:
            with panel:
                recovery_control.render(rt, rt.state.snapshot(view='dma'))
        panel = lazy_panel('원본 로그 · 다운로드', 'raw-panel')
        if panel.open:
            with panel:
                raw_panel()


st.navigation([st.Page(main, title='Laser Guard')], position='hidden').run()
