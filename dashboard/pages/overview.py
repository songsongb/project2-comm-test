"""Security monitoring: current observations and explicitly historical events."""
from html import escape
import time
import streamlit as st
from dashboard.config import LABELS
from dashboard.emergency import incident_summary, record_manual_report, alarm_events
from dashboard.presentation import table
from dashboard.ui_components import copy_button

STATES = {
    'DISARMED': ('감시 해제', '센서 상태와 별개로 침입 감시는 활성화되지 않았습니다.', '#64748b', '#f1f5f9'),
    'ARMED': ('감시 중', '허브가 감시 활성 상태를 보고했습니다.', '#15805c', '#edf8f2'),
    'SUSPECT': ('의심 이벤트 발생', '문·충격·소리 등 최근 이벤트를 확인하세요.', '#b97710', '#fff7e6'),
    'ALARM': ('침입 경보', '센서 경보가 보고되었습니다. 현장 상황을 직접 확인하세요.', '#c13232', '#fff1f0'),
    'FAULT': ('센서·통신 이상', '장애 노드와 연결 상태를 확인하세요.', '#a95618', '#fff3e8'),
    'Unknown': ('상태 확인 불가', '허브 미연결 또는 수신 만료입니다. 과거 정상 상태로 안전을 판단하지 마세요.', '#64748b', '#f1f5f9'),
}
NODES = {'1': 'Window', '2': 'Door', '3': 'Central Hub', 'window': 'Window', 'door': 'Door', 'hub': 'Central Hub', 'uno': 'Arduino Uno'}


def sensor_observation(snap, device):
    """USB telemetry and Hub path are independent. Stale flags never imply healthy."""
    info = snap['devices'][device]
    latest = info.get('latest')
    d = latest.get('data', {}) if latest else {}
    status = snap.get('status')
    hub_fresh = snap['devices']['hub']['fresh']
    use_status = status and hub_fresh and time.time() - status['at'] <= 2.5
    flags = status.get('WINDOW_FLAGS' if device == 'window' else 'DOOR_FLAGS') if use_status else None
    health = snap.get('node_health', {}).get('1' if device == 'window' else '2')
    if d:
        ready = bool(d.get('ready'))
        fault = bool(d.get('fault')) if device == 'door' else None
        active = bool(d.get('open')) if device == 'door' else None
        path = '직접 USB 센서 로그'
        if device == 'window' and flags is not None:
            fault, active = bool(flags & 4), bool(flags & 2)
            path += ' + 광 경로·오류는 허브 STATUS'
    elif flags is not None:
        ready, fault, active = bool(flags & 1), bool(flags & 4), bool(flags & 2)
        path = '허브 STATUS 보고'
    else:
        ready = fault = active = None
        path = '최신 센서 정보 없음'
    link = 'Unknown'
    if hub_fresh and use_status and snap['hub_state'] in ('DISARMED', 'ARMED', 'SUSPECT'):
        link = '허브 경로 정상 보고'
    if hub_fresh and health:
        # Health events are transition-only. Always describe the retained observation.
        link = '마지막 허브 보고: ' + health['event']
        if flags is not None and status['at'] >= health['at'] and snap['hub_state'] == 'DISARMED':
            link = '허브 경로 정상 보고'
        if health['event'] == 'LINK_LOST' and (not use_status or status['at'] <= health['at'] or snap['hub_state'] == 'FAULT'):
            link = 'LINK_LOST 관측'
            if not d:
                ready = active = None
        if health['event'] == 'SENSOR_FAULT' and (not use_status or status['at'] <= health['at']):
            fault = True
    if ready is not True or fault is True:
        active = None  # An unready sensor's cleared ACTIVE bit cannot prove a clear path.
    return dict(ready=ready, fault=fault, active=active, data=d, path=path, link=link)


def render(rt, snap):
    state = snap.get('hub_state', 'Unknown')
    label, explanation, color, background = STATES.get(state, STATES['Unknown'])
    st.markdown(f'<div class="lg-status" style="--state:{color};--bg:{background};border-left-color:{color};background:{background}"><strong>{escape(label)} <span style="font-size:16px;font-weight:500">{escape(state)}</span></strong><p>{escape(explanation)}</p></div>', unsafe_allow_html=True)
    cards = []
    for device in ('window', 'door', 'hub', 'uno'):
        info = snap['devices'][device]
        usb = '연결됨' if info['connected'] else ('재생 데이터' if rt.mode != 'live' and info['last_received'] else 'Disconnected')
        lines = [f'USB: {usb} · ' + ('최근 수신' if info['fresh'] else '수신 만료 / Unknown')]
        if device in ('window', 'door'):
            obs = sensor_observation(snap, device)
            ready = 'READY' if obs['ready'] is True else 'NOT READY' if obs['ready'] is False else 'Unknown'
            fault = 'SENSOR_FAULT' if obs['fault'] else '오류 여부: Not measured' if obs['fault'] is None else '오류 플래그 없음'
            lines += [f'센서: {ready} · {fault}', obs['path'], obs['link']]
            active = obs['active']
            if device == 'door':
                lines += ['문: ' + ('열림' if active is True else '닫힘 보고' if active is False else 'Unknown')]
            else:
                lines += ['광 경로: ' + ('차단 보고' if active is True else '비차단 보고' if active is False else 'Unknown')]
                d = obs['data']
                lines += [f"LDR {d.get('ldr', 'Unknown')} / 임계값 {d.get('ldr_threshold', 'Unknown')}"]
            names = ('BEAM', 'SOUND') if device == 'window' else ('SHOCK', 'DOOR_OPEN')
            recent = [e for e in snap['events'] if e.get('data', {}).get('event') in names]
            if recent:
                e = recent[-1]
                lines += [f"최근 이력: {e['data']['event']} · {e['received_at']}"]
        elif device == 'hub':
            lines += ['보안 상태: ' + state]
            for node in ('window', 'door'):
                lines += [NODES[node] + ': ' + sensor_observation(snap, node)['link']]
            alarms = alarm_events(snap['events'])
            lines += ['최근 경보 이력: ' + (alarms[-1]['data']['event'] if alarms else '없음')]
        else:
            lines += ['릴레이 / RGB / 부저: Not measured']
            e = snap.get('uno_event')
            lines += ['실험: Unknown (주기 상태 미제공)']
            if e:
                lines += ['마지막 보고: ' + e['data'].get('event', 'Unknown') + ' · ' + e['received_at']]
        body = ''.join('<p>' + escape(str(line)) + '</p>' for line in lines)
        cards.append(f'<article class="lg-card"><h3>{escape(LABELS[device])}</h3><div class="lg-kicker">{escape(info.get("port") or "포트 미선택")} · 세션 {info["session"]}</div>{body}<small>마지막 PC 수신 {escape(info["last_received"] or "Unknown")}</small></article>')
    st.markdown('<div class="lg-cards">' + ''.join(cards) + '</div>', unsafe_allow_html=True)
    st.subheader('보안 이벤트 타임라인')
    st.caption('최근 수신 이력 · 아래 이벤트는 현재 진행 상태를 의미하지 않습니다. PC 시각은 수신 시각입니다.')
    events = snap.get('events', [])[-12:][::-1]
    if not events:
        st.info('수신된 보안 이벤트가 없습니다.')
    for e in events:
        d = e.get('data', {})
        event = str(d.get('event', 'Unknown'))
        alarm = ' alarm' if event.startswith('ALARM_') else ''
        node = NODES.get(str(d.get('node')), str(d.get('node', 'Unknown')))
        st.markdown(f'<div class="lg-event{alarm}"><b>{escape(event)}</b> · {escape(node)} · 당시 {escape(str(d.get("state", "Unknown")))}<small>PC {escape(str(e.get("received_at", "Unknown")))} · Hub {escape(str(e.get("mcu_ms", "Unknown")))} ms · {escape(str(e.get("source", "Unknown")))}</small></div>', unsafe_allow_html=True)
    with rt.lock:
        anomalies = list(rt.anomalies)[-6:][::-1]
    if anomalies:
        st.subheader('규칙 기반 이상 관측')
        st.dataframe(table(anomalies, columns=['received_at', 'code', 'device', 'node', 'source', 'status']), hide_index=True, width='stretch')


def emergency_panel(rt):
    snap = rt.state.snapshot(view='security')
    st.subheader('경찰 신고 (112)')
    st.caption('번호와 요약을 준비하는 기능입니다. Dashboard는 신고를 전송하거나 접수를 확인하지 않습니다.')
    if rt.mode != 'live':
        st.warning('DEMO / REPLAY 연습 화면입니다. 실제 사건이 아니며 전화 앱 링크를 제공하지 않습니다.')
    c1, c2 = st.columns([1, 3])
    with c1:
        st.metric('경찰 긴급 신고 번호', '112')
        copy_button('112', '전화번호 복사')
        if rt.mode == 'live' and st.checkbox('전화 앱을 지원하는 기기에서 직접 열겠습니다'):
            st.markdown('[전화 앱 열기 · 112](tel:112)')
            st.caption('기기 지원 시에만 열립니다. 신고 접수를 의미하지 않습니다.')
    with c2:
        location = st.text_input('사용자 입력 주소 또는 위치 설명', max_chars=500, key='incident_location')
        summary = incident_summary(snap, location, rt.mode)
        st.code(summary, language=None, wrap_lines=True)
        copy_button(summary, '사건 요약 복사')
    with st.form('manual-report'):
        confirmed = st.checkbox('사용자가 직접 신고했습니다 (Demo/Replay에서는 연습 기록)')
        if st.form_submit_button('수동 기록 저장'):
            try:
                record_manual_report(rt.storage, snap, location, rt.mode, confirmed)
                st.success('사용자 진술을 로컬 저장했습니다. 신고 접수 여부는 확인하지 않았습니다.')
            except ValueError as exc:
                st.error(str(exc))
