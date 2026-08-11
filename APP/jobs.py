"""In-process job store for long-running ingests.

Why this exists: a 44-page PDF ingests in ~93s and a 180-page one takes
several minutes, while Azure Container Apps' ingress cuts requests at ~240s by
default. Phase 3's parser router adds per-file OCR round-trips on top, so the
synchronous path only gets slower. Returning a job id immediately decouples
ingest duration from any HTTP timeout.

Deliberately in-memory, not SQLite: jobs are ephemeral progress state, worth
nothing after a restart, and the app already runs at maxReplicas 1 so there's
no second process to share them with. If replicas ever go above 1, this must
move into the database — a job created on one replica is invisible to another.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

# Terminal states are the ones a client can stop polling on.
QUEUED = "queued"
RUNNING = "running"
SUCCEEDED = "succeeded"
FAILED = "failed"
TERMINAL = {SUCCEEDED, FAILED}

# Keep finished jobs around long enough for a client to read the result, then
# drop them so a long-lived process doesn't accumulate them forever.
RETENTION_SECONDS = 3600
MAX_JOBS = 500


@dataclass
class Job:
    id: str
    owner_id: str
    filename: str
    status: str = QUEUED
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.id,
            "status": self.status,
            "filename": self.filename,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, owner_id: str, filename: str) -> Job:
        job = Job(id=str(uuid4()), owner_id=owner_id, filename=filename)
        with self._lock:
            self._jobs[job.id] = job
            self._evict_locked()
        return job

    def get(self, job_id: str, owner_id: str) -> Job | None:
        """Owner-scoped on purpose: a job id must not be a capability that
        leaks another user's filenames or ingest results.
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.owner_id != owner_id:
                return None
            return job

    def mark(self, job_id: str, status: str, *, result: dict | None = None, error: str | None = None) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = status
            job.updated_at = time.time()
            if result is not None:
                job.result = result
            if error is not None:
                job.error = error

    def _evict_locked(self) -> None:
        now = time.time()
        stale = [
            jid for jid, j in self._jobs.items()
            if j.status in TERMINAL and (now - j.updated_at) > RETENTION_SECONDS
        ]
        for jid in stale:
            del self._jobs[jid]

        # Hard cap as a backstop if retention alone isn't keeping up: drop the
        # oldest terminal jobs first, never anything still in flight.
        if len(self._jobs) > MAX_JOBS:
            finished = sorted(
                (j for j in self._jobs.values() if j.status in TERMINAL),
                key=lambda j: j.updated_at,
            )
            for job in finished[: len(self._jobs) - MAX_JOBS]:
                self._jobs.pop(job.id, None)


job_store = JobStore()
