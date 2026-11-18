from pathlib import Path
import time
import pyarrow as pa


def test_two_screens_lazy_panels_shared_runtime_ports_and_exports(tmp_path, monkeypatch):
    monkeypatch.setenv('DASHBOARD_DATA_DIR', str(tmp_path))
    from dashboard.runtime import Runtime
    from dashboard.tests.test_serial_runtime import FakePort, until
    from dashboard.replay import read_jsonl, to_record
    from dashboard.config import ROOT
    from streamlit.testing.v1 import AppTest
    import streamlit as st
    st.cache_resource.clear()
    created = []
    def track(*args, **kwargs):
        rt = Runtime(*args, **kwargs)
        created.append(rt)
        return rt
    monkeypatch.setattr('dashboard.runtime.Runtime', track)
    app = AppTest.from_file(str(ROOT / 'app.py'), default_timeout=20)
    app.run()
    assert not app.exception and not app.tabs
    assert app.title[0].value == 'Security Monitoring'
    assert not app.get('plotly_chart')
    assert '상태 확인 불가' in '\n'.join(m.value for m in app.markdown)
    rt = created[0]
    try:
        opened = []
        def serial_factory(port):
            opened.append(port)
            return FakePort()
        rt.serial.factory = serial_factory
        rt.serial.connect('window', 'ui-test-window')
        until(lambda: rt.serial.workers['window'].connected)
        worker = rt.serial.workers['window']
        # Screen navigation must not reset source, data, or the COM worker.
        next(w for w in app.radio if w.key == 'screen_mode').set_value('DMA 성능 분석').run()
        assert not app.exception
        assert rt.serial.workers['window'] is worker and not worker.stop.is_set()
        assert len(created) == 1 and len(opened) == 1
        assert len(app.get('plotly_chart')) == 4
        assert len(app.dataframe[0].value) == 6
        next(w for w in app.radio if w.key == 'screen_mode').set_value('보안 관제').run()
        assert not app.get('plotly_chart')
        assert rt.serial.workers['window'] is worker
        next(w for w in app.selectbox if w.label == '입력 소스').set_value('demo').run()
        next(b for b in app.button if b.label == 'Demo 시작').click().run()
        assert not app.exception
        assert rt.replay is not None
        rt.switch_mode('demo')
        for entry in read_jsonl((ROOT / 'samples/synthetic_demo.jsonl').read_text()):
            rt.process(to_record(entry, demo=True))
        # Mixed historical node types must serialize without Arrow recovery warnings.
        rt.anomalies.append({'id': 'legacy', 'node': 1, 'device': 'hub', 'code': 'SENSOR_FAULT', 'source': 'demo'})
        rt.anomalies.append({'id': 'legacy2', 'node': 'window', 'device': 'window', 'code': 'OBSERVED_SKIPS', 'source': 'demo'})
        exports = []
        original_export = rt.storage.raw_jsonl
        def export(*args, **kwargs):
            exports.append(args)
            return original_export(*args, **kwargs)
        monkeypatch.setattr(rt.storage, 'raw_jsonl', export)
        monkeypatch.setattr(rt.storage, 'raw_records', lambda *args: (_ for _ in ()).throw(AssertionError('eager DB raw query')))
        app.run()
        assert not app.exception and not exports
        next(w for w in app.radio if w.key == 'screen_mode').set_value('DMA 성능 분석').run()
        assert len(app.get('plotly_chart')) == 4
        six = app.dataframe[0].value
        assert len(six) == 6 and set(six['validity']) == {'유효'}
        app.session_state['sensor-panel'] = True
        app.run()
        assert not app.exception and len(app.get('plotly_chart')) == 6
        app.session_state['experiment-panel'] = True
        app.run()
        assert not app.exception
        assert any(b.label == '현재 조건으로 측정 시작' for b in app.button)
        app.session_state['control-panel'] = True
        app.run()
        assert not app.exception
        assert next(b for b in app.button if b.label == '승인 요청 준비').disabled
        app.session_state['raw-panel'] = True
        app.run()
        assert not exports
        # AppTest 1.65 does not send stateful-expander widget values on button
        # clicks. The real Chromium test exercises prepare + actual download.
        payload = rt.storage.raw_jsonl(('demo',), 2000)
        assert len(exports) == 1 and payload
        next(w for w in app.radio if w.key == 'screen_mode').set_value('보안 관제').run()
        app.session_state['emergency-panel'] = True
        app.run()
        assert not app.exception and not app.get('plotly_chart')
        assert not any('tel:' in m.value for m in app.markdown)
        assert not rt.storage.history('manual_report')
        for data in app.dataframe:
            pa.Table.from_pandas(data.value, preserve_index=False)
    finally:
        rt.close()
        st.cache_resource.clear()
