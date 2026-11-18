"""Bounded-buffer synthetic soak, separate from real COM/hardware qualification."""
import argparse
import gc
import json
from pathlib import Path
import resource
import sys
import tempfile
import time
import tracemalloc
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dashboard.runtime import Runtime
from dashboard.models import Record


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--chunk', type=int, default=20000)
    args=p.parse_args()
    rt=Runtime(tempfile.mkdtemp(prefix='laser-guard-soak-'))
    result={'kind':'synthetic accelerated soak; no real hardware', 'stages': []}
    tracemalloc.start()
    start=time.perf_counter()
    try:
        for stage in range(2):
            for i in range(stage*args.chunk, (stage+1)*args.chunk):
                ms=2000+i*1000
                rt.process(Record('window','soak',f'STAT,{ms},2,0,10000,9984,0,6400000,100,312,3000,2900,3100,3000,1500,18,1,0',source='synthetic'))
            gc.collect()
            current,peak=tracemalloc.get_traced_memory()
            result['stages'].append({'records_processed':(stage+1)*args.chunk,'python_heap_mib':current/1048576,
                                     'python_peak_mib':peak/1048576,'metric_buffer':len(rt.state.metric_rows),
                                     'raw_buffer':len(rt.state.records),'anomaly_keys':len(rt.detector.last_alert)})
        result['elapsed_s']=time.perf_counter()-start
        result['peak_rss_mib']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
        with rt.storage.lock:
            result['stored_raw_records']=rt.storage.db.execute('SELECT count(*) FROM records').fetchone()[0]
        args.output.write_text(json.dumps(result,indent=2))
        print(json.dumps(result,indent=2))
    finally:
        tracemalloc.stop()
        rt.close()


if __name__=='__main__':
    main()
