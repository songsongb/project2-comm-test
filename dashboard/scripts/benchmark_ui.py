"""Isolated AppTest rendering benchmark, runnable against an old checkout too.

python dashboard/scripts/benchmark_ui.py --root /tmp/old-checkout --output /tmp/old.json
No Ollama server/model is invoked. The old code's idle worker is counted as baseline.
"""
import argparse
import gc
import json
import os
from pathlib import Path
import resource
import statistics
import sys
import tempfile
import threading
import time


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    p.add_argument('--samples', type=Path, default=Path(__file__).resolve().parents[1] / 'samples/synthetic_demo.jsonl')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--runs', type=int, default=8)
    args = p.parse_args()
    sys.path.insert(0, str(args.root.resolve()))
    os.environ['DASHBOARD_DATA_DIR'] = tempfile.mkdtemp(prefix='laser-guard-benchmark-')
    import dashboard.runtime as module
    from dashboard.replay import read_jsonl, to_record
    from dashboard.models import Record
    from streamlit.testing.v1 import AppTest
    created = []
    original = module.Runtime
    def track(*a, **kw):
        rt = original(*a, **kw)
        created.append(rt)
        return rt
    module.Runtime = track
    app = AppTest.from_file(str(args.root / 'dashboard/app.py'), default_timeout=40).run()
    rt = created[0]
    queried = []
    raw = rt.storage.raw_records
    def count(*a, **kw):
        result = raw(*a, **kw)
        queried.append(len(result))
        return result
    rt.storage.raw_records = count
    try:
        rt.mode = 'demo'
        for entry in read_jsonl(args.samples.read_text()):
            rt.process(to_record(entry, demo=True))
        # Fill the metric ring to capacity using identical synthetic input in both versions.
        for i in range(7400):
            ms = 200000 + i*1000
            rt.process(Record('window', 'synthetic:window', f'STAT,{ms},2,1,10000,9984,0,6500000,101,312,3000,2900,3100,3000,1500,18,1,0', source='demo'))
        app.run()
        assert not app.exception
        times = {}
        modes = ['보안 관제', 'DMA 성능 분석'] if app.radio else ['legacy-five-tabs']
        for mode in modes:
            if app.radio:
                next(w for w in app.radio if w.key == 'screen_mode').set_value(mode).run()
            app.run()
            durations = []
            for _ in range(args.runs):
                start = time.perf_counter()
                app.run()
                assert not app.exception
                durations.append((time.perf_counter()-start)*1000)
            times[mode] = {'median_render_ms': statistics.median(durations), 'min_ms': min(durations),
                           'max_ms': max(durations), 'charts': len(app.get('plotly_chart'))}
        gc.collect()
        result = {'root': str(args.root), 'runs_per_mode': args.runs, 'metric_rows': len(rt.state.metric_rows),
                  'db_records': len(rt.storage.raw_records(20000)), 'render': times,
                  'raw_query_calls': len(queried)-1, 'raw_rows_decoded_for_ui': sum(queried[:-1]),
                  'peak_rss_mib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
                  'threads': [t.name for t in threading.enumerate()]}
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        rt.close()


if __name__ == '__main__':
    main()
