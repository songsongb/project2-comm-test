from copy import deepcopy
import json
import time
from urllib.error import URLError
import pytest
from dashboard.anomaly_detector import AnomalyDetector
from dashboard.diagnosis_manager import DiagnosisManager
from dashboard.llm_client import OllamaClient, validate, ValidationError
from dashboard.runtime import Runtime
from conftest import stat, event


EVIDENCE = [{"id": "r1", "device": "window", "source": "live", "fields": {"ready": 0, "event": "SENSOR_FAULT"}}]
GOOD = {"anomaly": "SENSOR_FAULT", "facts": [{"evidence_id": "r1", "field": "ready", "value": 0}],
        "causes": [{"cause": "센서 보정 또는 배선 문제 가능성", "reason": "센서 미준비 관측만으로 원인 미확정", "evidence_ids": ["r1"]}],
        "steps": ["센서 배선과 기준 환경을 확인하세요"], "unknowns": ["취득 경로 추가 계측 필요"], "actions": []}


def wait_job(storage, jid):
    end = time.monotonic() + 3
    while time.monotonic() < end:
        job = next(j for j in storage.history("diagnosis") if j["id"] == jid)
        if job["status"] not in ("queued", "running"):
            return job
        time.sleep(.01)
    raise AssertionError("작업 미완료")


def test_valid_diagnosis_and_reject_invented_evidence():
    assert validate(deepcopy(GOOD), EVIDENCE, "SENSOR_FAULT") == GOOD
    for field, value in (("value", 999), ("field", "dma_overrun"), ("evidence_id", "made-up")):
        bad = deepcopy(GOOD)
        bad["facts"][0][field] = value
        with pytest.raises(ValidationError):
            validate(bad, EVIDENCE, "SENSOR_FAULT")


@pytest.mark.parametrize("command", ["ARM", "DISARM", "MODE 9", "LASER ON", "RESET", "MODE 2\nARM"])
def test_llm_nonexistent_or_forbidden_command_rejected(command):
    bad = deepcopy(GOOD)
    bad["actions"] = [command]
    with pytest.raises(ValidationError):
        validate(bad, EVIDENCE, "SENSOR_FAULT")


def test_hallucinated_numbers_logs_and_control_prose_rejected():
    for text in ("손실은 98765입니다", "DMA_BROKEN가 확인됨", "LASER ON 실행"):
        bad = deepcopy(GOOD)
        bad["steps"] = [text]
        with pytest.raises(ValidationError):
            validate(bad, EVIDENCE, "SENSOR_FAULT")


def test_ollama_payload_uses_schema_and_timeout(monkeypatch):
    captured = {}
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self, size):
            return json.dumps({"response": json.dumps(GOOD), "total_duration": 123}).encode()
    def fake_open(req, timeout):
        captured.update(json.loads(req.data), timeout=timeout)
        return Response()
    monkeypatch.setattr("dashboard.llm_client.urlopen", fake_open)
    result = OllamaClient(timeout=5).diagnose("SENSOR_FAULT", EVIDENCE)
    assert captured["stream"] is False and captured["timeout"] == 5
    assert captured["format"]["type"] == "object"
    assert result["result"] == GOOD and result["latency_s"] >= 0


@pytest.mark.parametrize("exc", [URLError("connection refused"), TimeoutError("timeout")])
def test_offline_llm_does_not_stop_acquisition(tmp_path, monkeypatch, exc):
    def unavailable(*args, **kwargs):
        raise exc
    monkeypatch.setattr("dashboard.llm_client.urlopen", unavailable)
    rt = Runtime(tmp_path)
    try:
        jid = rt.diagnosis.submit("SENSOR_FAULT", EVIDENCE)
        for ms in (2000, 3000, 4000):
            rt.receive(stat(ms))
        rt.queue.join()
        assert len(rt.state.metric_rows) == 3
        assert rt.state.metric_rows[-1]["eligible"]
        job = wait_job(rt.storage, jid)
        assert job["status"] == "unavailable" and job["elapsed_s"] >= 0
    finally:
        rt.close()


def test_deduplicated_diagnosis(storage):
    class Offline:
        model = "fake"
        def diagnose(self, *args):
            raise ConnectionError("off")
    manager = DiagnosisManager(storage, Offline())
    try:
        a = manager.submit("SENSOR_FAULT", EVIDENCE)
        b = manager.submit("SENSOR_FAULT", EVIDENCE)
        assert a == b
        wait_job(storage, a)
        assert len(storage.history("diagnosis")) == 1
    finally:
        manager.close()


def test_active_anomaly_dedup_even_when_recent_context_changes(storage):
    import threading
    release = threading.Event()
    class Blocking:
        model = "fake"
        def diagnose(self, *args):
            release.wait(2)
            raise ConnectionError("off")
    manager = DiagnosisManager(storage, Blocking())
    try:
        a = manager.submit("SENSOR_FAULT", EVIDENCE, anomaly_id="same-alert")
        changed = deepcopy(EVIDENCE)
        changed[0]["fields"]["new_stat"] = 10
        b = manager.submit("SENSOR_FAULT", changed, anomaly_id="same-alert")
        assert a == b
        release.set()
        wait_job(storage, a)
    finally:
        release.set()
        manager.close()


def test_explicit_retry_after_unavailable(storage):
    class Offline:
        model = "fake"
        def diagnose(self, *args):
            raise ConnectionError("off")
    manager = DiagnosisManager(storage, Offline())
    try:
        a = manager.submit("SENSOR_FAULT", EVIDENCE)
        wait_job(storage, a)
        b = manager.submit("SENSOR_FAULT", EVIDENCE, retry=True)
        assert a != b
        assert wait_job(storage, b)["status"] == "unavailable"
    finally:
        manager.close()


def test_anomaly_rules_and_cooldown():
    detector = AnomalyDetector()
    first = event(name="SENSOR_FAULT", node=1, value=4, ingested_at=100)
    assert detector.check(first)[0]["code"] == "SENSOR_FAULT"
    assert detector.check(first) == []
    detector.check(event(name="WINDOW_FRAME_ERRORS", node=1, value=4))
    assert detector.check(event(name="WINDOW_FRAME_ERRORS", node=1, value=5))[0]["code"] == "FRAME_ERRORS_INCREASE"
    codes = [a["code"] for a in detector.check(stat(pairs=0, ready=0))]
    assert "DMA_COLLECTION_STOPPED" in codes


def test_only_anomalies_trigger_auto_llm(tmp_path):
    class Offline:
        model = "fake"
        def diagnose(self, *args):
            raise ConnectionError("off")
    rt = Runtime(tmp_path, Offline())
    try:
        rt.auto_diagnose = True
        for ms in (2000, 3000, 4000):
            rt.process(stat(ms))
        assert not rt.storage.history("diagnosis")
        rt.process(stat(5000, pairs=0, ready=0))
        assert rt.storage.history("diagnosis")
    finally:
        rt.close()
