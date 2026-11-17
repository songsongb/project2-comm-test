from pathlib import Path
import pytest


def test_streamlit_five_tabs_disconnected_and_demo(tmp_path, monkeypatch):
    monkeypatch.setenv("DASHBOARD_DATA_DIR", str(tmp_path))
    from dashboard.runtime import Runtime
    created = []
    def track(*args, **kwargs):
        rt = Runtime(*args, **kwargs)
        created.append(rt)
        return rt
    monkeypatch.setattr("dashboard.runtime.Runtime", track)
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=20)
    app.run()
    assert not app.exception
    assert len(app.tabs) == 5
    assert any(m.value == "Unknown" for m in app.metric)
    # The single cached process Runtime persists across UI reruns.
    next(w for w in app.selectbox if w.label == "입력 소스").set_value("demo").run()
    assert not app.exception
    button = next(b for b in app.button if b.label == "Demo 시작")
    button.click().run()
    import time
    time.sleep(.5)
    app.run()
    assert not app.exception
    assert any("DEMO / REPLAY" in w.value for w in app.warning)
    assert len(app.tabs) == 5
    assert len(created) == 1
    rt = created[0]
    try:
        rt.switch_mode("demo")
        from dashboard.replay import read_jsonl, to_record
        from dashboard.config import ROOT
        for entry in read_jsonl((ROOT / "samples/synthetic_demo.jsonl").read_text()):
            rt.process(to_record(entry, demo=True))
        app.run()
        assert not app.exception
        # Exercise all plots/tables, including a complete trace and grouped TRIAL statistics.
        assert len(app.get("plotly_chart")) >= 7
        assert len(app.dataframe) >= 5
        assert str(rt.data_dir) == str(tmp_path)
    finally:
        rt.close()
