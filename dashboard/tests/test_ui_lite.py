import json
import sys
import threading
from pathlib import Path
import pyarrow as pa
import pandas as pd
import pytest
from conftest import stat, event
from dashboard.anomaly_detector import AnomalyDetector
from dashboard.emergency import incident_summary, record_manual_report
from dashboard.presentation import table, comparison, extrema_points, RenderCache
from dashboard.runtime import Runtime
from dashboard.replay import Replay, read_jsonl
from dashboard.config import ROOT


def test_arrow_mixed_node_nested_and_missing_fields():
    rows = [{'node': 1, 'value': 4, 'nested': {'flag': 1}}, {'node': 'window', 'value': 2.5, 'nested': 'text'}, {'other': [1, 2]}, {'node': None, 'value': 'invalid'}]
    frame = table(rows, numeric=('value',))
    encoded = pa.Table.from_pandas(frame, preserve_index=False)
    assert str(frame['node'].dtype) == 'string'
    assert frame['node'].iloc[0] == '1' and frame['node'].iloc[1] == 'window'
    assert str(frame['value'].dtype) == 'Float64' and pd.isna(frame['value'].iloc[-1])
    assert encoded.num_rows == 4
    pa.Table.from_pandas(table([], columns=['node', 'value'], numeric=('value',)))


def test_anomalies_node_string_and_original_numeric_id():
    detector = AnomalyDetector()
    a = detector.check(event(name='SENSOR_FAULT', node=1, value=4))[0]
    b = detector.check(stat(ready=0))[0]
    assert a['node'] == '1' and a['node_id'] == 1
    assert b['node'] == 'window' and b['node_id'] is None
    pa.Table.from_pandas(table([a, b], numeric=('node_id', 'session')))


def test_rules_cooldown_and_frame_errors_maintained():
    detector = AnomalyDetector()
    fault = event(name='SENSOR_FAULT', node=1, value=4)
    assert detector.check(fault) and not detector.check(fault)
    detector.check(event(name='WINDOW_FRAME_ERRORS', node=1, value=4))
    assert detector.check(event(name='WINDOW_FRAME_ERRORS', node=1, value=5))[0]['code'] == 'FRAME_ERRORS_INCREASE'
    assert 'DMA_COLLECTION_STOPPED' in [a['code'] for a in detector.check(stat(pairs=0, ready=0))]


def test_six_conditions_preserve_zero_vs_no_data_and_scope(state):
    for ms in (2000, 3000, 4000):
        state.ingest(stat(ms))
    six, _ = comparison(list(state.metric_rows), 'live', 'COM12', 0)
    dma = next(r for r in six if r['mode'] == 'DMA' and r['load'] == 0)
    assert dma['observed_skip_pct'] == 0 and dma['validity'] == '유효'
    missing = next(r for r in six if r['mode'] == 'Polling')
    assert missing['observed_skip_pct'] is None and missing['validity'] == 'No data'
    assert comparison(list(state.metric_rows), 'demo', 'COM12', 0)[1] == []
    pa.Table.from_pandas(table(six, numeric=('samples_s', 'observed_skip_pct', 'irqs_s', 'acquisition_pct', 'acq_cycles')))


def test_downsampling_retains_spikes_and_all_gaps():
    rows = [{'x': i, 'value': 10} for i in range(2000)]
    rows[753]['value'] = 9999
    rows[1001]['value'] = -123
    for i in range(1100, 1120):
        rows[i]['value'] = None
    visible = extrema_points(rows, 'value', 100)
    assert rows[753] in visible and rows[1001] in visible
    assert all(rows[i] in visible for i in range(1099, 1121))
    assert rows[0] in visible and rows[-1] in visible


def test_bounded_cache_reuses_unchanged_charts():
    cache = RenderCache(3)
    calls = []
    first = cache.get('revision1', lambda: calls.append(1) or object())
    assert cache.get('revision1', lambda: object()) is first
    for i in range(20):
        cache.get(i, lambda: object())
    assert len(cache.items) == 3 and calls == [1]


def test_snapshot_security_skips_metric_and_trace_materialization(state, monkeypatch):
    state.ingest(stat())
    from dashboard.state_manager import TraceCapture
    monkeypatch.setattr(TraceCapture, 'as_dict', lambda self: (_ for _ in ()).throw(AssertionError('trace materialized')))
    view = state.snapshot(view='security')
    assert 'metrics' not in view and 'traces' not in view
    assert not view['records']
    assert len(state.snapshot(view='dma')['metrics']) == 1


def test_unready_sensor_never_reports_clear_path(state):
    from conftest import feed_status
    from dashboard.pages.overview import sensor_observation
    feed_status(state, flags=4)
    state.ingest(stat(ready=0))
    observation = sensor_observation(state.snapshot(view='security'), 'window')
    assert observation['fault'] is True
    assert observation['active'] is None


def test_legacy_sqlite_artifacts_preserved_and_export_filtered(tmp_path):
    from dashboard.storage import Storage
    path = tmp_path / 'dashboard.sqlite3'
    store = Storage(path)
    store.save('diagnosis', {'id': 'old-llm', 'source': ['live'], 'text': 'old response'})
    store.record(stat(source='live'))
    store.record(stat(source='demo'))
    store.close()
    rt = Runtime(tmp_path)
    try:
        assert rt.storage.artifact('old-llm')['text'] == 'old response'
        data = rt.storage.raw_jsonl(('live',))
        assert len(data.splitlines()) == 1
        assert json.loads(data)['source'] == 'live'
        assert len(rt.storage.raw_records()) == 2
        assert not hasattr(rt, 'diagnosis') and not hasattr(rt, 'auto_diagnose')
        assert not any('ollama' in t.name.lower() for t in threading.enumerate())
    finally:
        rt.close()


def test_replay_collection_source_and_hardware_block(tmp_path):
    rt = Runtime(tmp_path)
    try:
        rt.switch_mode('replay')
        entries = read_jsonl((ROOT / 'samples/synthetic_demo.jsonl').read_text())[:20]
        replay = Replay(entries, rt.receive, speed=10000)
        replay.start()
        replay.thread.join(3)
        rt.queue.join()
        assert replay.position == len(entries)
        assert all(r['source'] == 'replay-synthetic' for r in rt.storage.raw_records())
        rt.state.set_connection('hub', True, 'FAKE')
        assert not rt.controller.check('STATUS')[0]
        assert not rt.controller.check('MODE 2', idle_confirmed=True)[0]
    finally:
        rt.close()


def test_emergency_preparation_never_dispatches_and_is_source_marked(storage):
    snap = {'hub_state': 'Unknown', 'events': [event(name='ALARM_BEAM', state='ALARM').as_dict()]}
    summary = incident_summary(snap, '사용자 입력 위치', 'demo')
    assert '연습 자료' in summary and '사용자 입력 위치' in summary and 'ALARM_BEAM' in summary
    assert not storage.history('manual_report')
    with pytest.raises(ValueError):
        record_manual_report(storage, snap, '', 'live')
    entry = record_manual_report(storage, snap, '', 'demo', True)
    assert entry['kind'] == 'practice_record' and not entry['receipt_verified']
    assert '미입력' in entry['summary']


def test_anomaly_indexes_bounded_over_many_sessions():
    d = AnomalyDetector(cooldown=0)
    for i in range(1000):
        r = event(name='SENSOR_FAULT', node=1, value=4)
        r.session = i
        d.check(r)
    assert len(d.last_alert) <= 512


def test_no_llm_modules_present_or_imported():
    for module in ('dashboard.llm_client', 'dashboard.diagnosis_manager', 'dashboard.pages.ai_diagnostics'):
        assert module not in sys.modules
        assert not (ROOT.parent / (module.replace('.', '/') + '.py')).exists()
