import streamlit as st
import pandas as pd


IMPACTS = {"MODE 0": "Window ADC를 Polling으로 변경", "MODE 1": "Window ADC를 Interrupt로 변경",
           "MODE 2": "Window ADC를 DMA로 설정 (범용 고장 복구 아님)",
           "LOAD 0": "Window 추가 CPU 부하 중지", "LOAD 1": "Window 추가 CPU 부하 활성화",
           "CAL": "Window와 Door 기준값 재보정: 두 노드 모두 영향"}


def render(rt, snap):
    st.subheader("제한적 복구 · 사용자 승인")
    st.caption("허용: STATUS · HELP · MODE 0/1/2 · LOAD 0/1 · CAL. ARM/DISARM·레이저·릴레이·임의 제어는 차단합니다.")
    if rt.mode != "live":
        st.warning("Demo/Replay에서는 하드웨어 명령을 전송하지 않습니다.")
    c1, c2 = st.columns(2)
    for col, command in ((c1, "STATUS"), (c2, "HELP")):
        with col:
            if st.button(command + " 조회", disabled=rt.mode != "live"):
                try:
                    if not rt.controller.query(command):
                        st.info("연결 확인 또는 조회 간격(1초)을 기다리세요.")
                except ValueError as exc:
                    st.error(str(exc))
    st.caption("연결된 Hub에는 1초마다 STATUS만 자동 조회합니다. 읽기 전용 자동 조회입니다.")
    with st.expander("현재 명령 실행 조건"):
        checks = []
        for command in IMPACTS:
            ok, reason = rt.controller.check(command)
            checks.append({"command": command, "가능": ok, "조건": reason})
        st.dataframe(pd.DataFrame(checks), hide_index=True, width="stretch")
        st.caption("허브는 실험/내부 pending 상태를 STATUS로 제공하지 않습니다. 사용자 확인 및 MCU의 최종 거부 결과가 필요합니다. FAULT 중 CAL은 PC에서 보수적으로 차단합니다.")
    suggestions = []
    recommendations = {}
    for job in rt.storage.history("diagnosis", 30):
        if job.get("status") == "complete":
            for command in job["result"]["actions"]:
                recommendations[job["id"] + ":" + command] = (job["id"], command, job["code"], ",".join(job["source"]))
                if command not in suggestions:
                    suggestions.append(command)
    if suggestions:
        st.write("LLM 제안 (과거 데이터 포함 가능): " + ", ".join(suggestions))
    origin = st.selectbox("조치 후보 출처", ["manual"] + list(recommendations),
                          format_func=lambda i: "수동 선택" if i == "manual" else f"LLM {recommendations[i][2]} · {recommendations[i][1]} · {recommendations[i][3]}")
    if origin == "manual":
        command = st.selectbox("허브에 요청할 명령", list(IMPACTS), format_func=lambda c: f"{c} — {IMPACTS[c]}")
    else:
        job_id, command, _, _ = recommendations[origin]
        origin = "diagnosis:" + job_id
        st.write(command + " — " + IMPACTS[command])
    idle = st.checkbox("UNO 실험·PB0 펄스가 진행 중이지 않음을 실제로 확인했습니다")
    baseline = st.checkbox("CAL: 광 경로가 정상이고 문이 기준 위치에 있으며 센서 환경이 안정적임을 확인했습니다", disabled=command != "CAL")
    ok, reason = rt.controller.check(command, idle_confirmed=idle, baseline_confirmed=baseline)
    st.write("현재 조건: " + reason)
    if st.button("승인 요청 준비", disabled=not ok or rt.mode != "live"):
        try:
            proposal = rt.controller.propose(command, idle, baseline, origin=origin)
            st.session_state["proposal_id"] = proposal["id"]
        except ValueError as exc:
            st.error(str(exc))
    proposal_id = st.session_state.get("proposal_id")
    proposal = rt.controller.proposals.get(proposal_id)
    if proposal and proposal["status"] == "proposed":
        st.warning(f"대상: Hub → {IMPACTS[proposal['command']]} · 20초 후 승인 만료")
        st.caption("승인하면 해당 명령을 한 번 전송합니다. 전송 직전 상태가 변경·만료되면 거부합니다.")
        with st.expander("승인 전 상태"):
            st.json(proposal["before"])
        if st.button("위 명령의 실제 전송을 승인합니다", type="primary"):
            try:
                rt.controller.approve(proposal_id, approved=True)
                st.success("명령 큐에 등록했습니다. 후속 검증 결과를 확인하세요.")
            except ValueError as exc:
                st.error(str(exc))
    history = rt.storage.history("command", 100)
    if history:
        st.dataframe(pd.DataFrame([{k: str(p.get(k, "")) for k in ("id", "command", "created_at", "approved", "status", "acks", "result")} for p in history]), hide_index=True, width="stretch")
        pid = st.selectbox("명령 전후 상세 이력", [p["id"] for p in history])
        st.json(next(p for p in history if p["id"] == pid))
