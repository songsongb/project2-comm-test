import hashlib
import json
import queue
import threading
import time
import uuid
from .llm_client import OllamaClient
from .models import utc_now


class DiagnosisManager:
    def __init__(self, storage, client=None):
        self.storage = storage
        self.client = client or OllamaClient()
        self.lock = threading.RLock()
        self.queue = queue.Queue(maxsize=16)
        self.jobs = {}
        self.seen = {}
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, name="ollama-diagnosis", daemon=True)
        self.thread.start()

    def configure(self, base_url, model, timeout):
        with self.lock:
            self.client = OllamaClient(base_url, model, timeout)

    def submit(self, code, evidence, question=None, anomaly_id=None, retry=False):
        if not evidence:
            raise ValueError("수신된 근거 데이터가 없습니다")
        with self.lock:
            sources = sorted({e["source"] for e in evidence})
            for pending in self.jobs.values():
                same_request = ((anomaly_id is not None and pending.get("anomaly_id") == anomaly_id) or
                                (question is not None and pending.get("question") == question and pending["source"] == sources))
                if same_request and pending["model"] == self.client.model and pending["status"] in ("queued", "running"):
                    return pending["id"]
            key = hashlib.sha256(json.dumps([code, evidence, question, self.client.model], sort_keys=True).encode()).hexdigest()
            if key in self.seen and not retry:
                return self.seen[key]
            if self.queue.full():
                raise ValueError("진단 큐가 가득 찼습니다")
            job = {"id": uuid.uuid4().hex, "code": code, "anomaly_id": anomaly_id,
                   "source": sources, "created_at": utc_now(),
                   "question": question, "status": "queued", "evidence": evidence, "model": self.client.model}
            self.jobs[job["id"]] = job
            self.seen[key] = job["id"]
            # Bounded in-memory indexes; SQLite keeps the complete audit history.
            if len(self.seen) > 500:
                self.seen.pop(next(iter(self.seen)))
            if len(self.jobs) > 200:
                for jid in list(self.jobs):
                    if self.jobs[jid]["status"] not in ("queued", "running"):
                        self.jobs.pop(jid)
                        break
            self.storage.save("diagnosis", job)
            self.queue.put_nowait((job, self.client))
            return job["id"]

    def _run(self):
        while not self.stop.is_set():
            try:
                job, client = self.queue.get(timeout=.2)
            except queue.Empty:
                continue
            start = time.perf_counter()
            with self.lock:
                job["status"] = "running"
                self.storage.save("diagnosis", job)
            try:
                result = client.diagnose(job["code"], job["evidence"], job["question"])
                with self.lock:
                    job.update(result, status="complete")
            except Exception as exc:
                with self.lock:
                    job.update(status="unavailable", error=f"{type(exc).__name__}: {exc}")
            finally:
                with self.lock:
                    job.update(elapsed_s=time.perf_counter() - start, ended_at=utc_now())
                    self.storage.save("diagnosis", job)

    def close(self):
        self.stop.set()
        # Retain terminal status for accepted but not yet started requests.
        while True:
            try:
                job, _ = self.queue.get_nowait()
            except queue.Empty:
                break
            job.update(status="cancelled", ended_at=utc_now(), error="프로그램 종료로 대기 요청 취소")
            self.storage.save("diagnosis", job)
        self.thread.join(timeout=.5)  # An in-flight HTTP request has its own finite timeout.
