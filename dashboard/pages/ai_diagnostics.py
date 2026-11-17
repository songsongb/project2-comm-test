import streamlit as st
import pandas as pd


def render(rt, snap):
    st.subheader("AI Diagnostics · 근거 기반 원인 후보")
    st.caption("규칙 탐지는 Ollama 없이 동작합니다. LLM 출력은 가설이며 명령 실행 권한이 없습니다.")
    rt.auto_diagnose = st.checkbox("새 이상 탐지 시 Ollama 진단 요청", value=rt.auto_diagnose)
    with st.expander("Ollama 설정"):
        with st.form("ollama-settings"):
            url = st.text_input("로컬 Ollama 주소", rt.diagnosis.client.base_url)
            model = st.text_input("모델 이름", rt.diagnosis.client.model)
            timeout = st.number_input("응답 제한 (초)", 1, 120, int(rt.diagnosis.client.timeout))
            if st.form_submit_button("설정 적용"):
                try:
                    rt.diagnosis.configure(url, model, timeout)
                    st.success("적용했습니다. 모델 다운로드는 Ollama에서 수행하세요.")
                except ValueError as exc:
                    st.error(str(exc))
    anomalies = rt.storage.history("anomaly", 100)
    if anomalies:
        st.dataframe(pd.DataFrame([{k: a[k] for k in ("id", "code", "device", "node", "source", "received_at", "status")} for a in anomalies]), hide_index=True, width="stretch")
        selected = st.selectbox("진단할 이상", [a["id"] for a in anomalies], format_func=lambda i: next(f"{a['received_at']} · {a['code']} · {a['source']}" for a in anomalies if a["id"] == i))
        alert = next(a for a in anomalies if a["id"] == selected)
        if st.button("선택한 이상 진단 요청"):
            try:
                st.success("진단 요청: " + rt.request_diagnosis(alert)[:8])
            except ValueError as exc:
                st.error(str(exc))
    else:
        st.info("발견된 이상 이력이 없습니다. 미연결 상태의 센서 원인은 Unknown입니다.")
    with st.form("ask-question"):
        question = st.text_input("실제 수집 데이터에 질문", placeholder="Polling과 DMA의 차이를 최근 결과로 설명해 줘.")
        if st.form_submit_button("질문 보내기"):
            try:
                if not question.strip():
                    raise ValueError("질문을 입력하세요")
                job = rt.diagnosis.submit("QUESTION", rt.evidence(), question[:2000])
                st.success("질문 요청: " + job[:8])
            except ValueError as exc:
                st.error(str(exc))
    history = rt.storage.history("diagnosis", 100)
    if history:
        options = {j["id"]: f"{j['created_at']} · {j['code']} · {j['status']} · {','.join(j['source'])}" for j in history}
        jid = st.selectbox("진단 이력", options, format_func=options.get)
        job = next(j for j in history if j["id"] == jid)
        st.write(f"상태: {job['status']} · 모델: {job['model']} · 소요: {job.get('elapsed_s', 0):.2f}s")
        if job.get("error"):
            st.warning("LLM 비가용/응답 검증 실패: " + job["error"])
            if st.button("같은 근거로 다시 진단"):
                try:
                    new_id = rt.diagnosis.submit(job["code"], job["evidence"], job.get("question"), job.get("anomaly_id"), retry=True)
                    st.success("재진단 요청: " + new_id[:8])
                except ValueError as exc:
                    st.error(str(exc))
        result = job.get("result")
        if result:
            st.markdown("**관측 사실 — 입력 근거와 값 일치 검증 완료**")
            st.dataframe(pd.DataFrame([{**f, "value": str(f["value"])} for f in result["facts"]]), hide_index=True, width="stretch")
            st.markdown("**가능한 원인 — 확정되지 않은 LLM 가설**")
            for cause in result["causes"]:
                st.write(cause["cause"])
                st.caption(cause["reason"] + " · 근거: " + ", ".join(cause["evidence_ids"]))
            st.markdown("**권장 점검 절차**")
            for step in result["steps"]:
                st.write("• " + step)
            st.markdown("**추가 확인 / 미계측**")
            for unknown in result["unknowns"]:
                st.write("• " + unknown)
            st.write("허용 조치 제안: " + (", ".join(result["actions"]) or "없음"))
            st.caption("실행 가능 여부와 사용자 승인·조치 전후 결과는 Recovery & Control에서 확인하세요.")
            linked = [p for p in rt.storage.history("command", 200) if p.get("origin") == "diagnosis:" + job["id"]]
            if linked:
                st.markdown("**이 진단에서 승인한 조치**")
                st.dataframe(pd.DataFrame([{k: str(p.get(k, "")) for k in ("command", "approved", "status", "result")} for p in linked]), hide_index=True, width="stretch")
        with st.expander("요청에 포함한 근거 로그·측정값"):
            st.json(job["evidence"])
