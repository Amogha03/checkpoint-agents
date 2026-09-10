"""Thread-safe in-memory tracking for research jobs."""

from dataclasses import dataclass
from threading import RLock
from typing import Literal

JobStatus = Literal["queued", "running", "done", "failed"]


@dataclass
class JobRecord:
    """Mutable state for one research request."""

    job_id: str
    status: JobStatus = "queued"
    report: str | None = None
    error: str | None = None


class JobStore:
    """Small process-local job registry suitable for a single service instance."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = RLock()

    def create(self, job_id: str) -> JobRecord:
        with self._lock:
            record = JobRecord(job_id=job_id)
            self._jobs[job_id] = record
            return self._copy(record)

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            record = self._jobs.get(job_id)
            return self._copy(record) if record else None

    def mark_running(self, job_id: str) -> None:
        self._update(job_id, status="running")

    def mark_done(self, job_id: str, report: str) -> None:
        self._update(job_id, status="done", report=report, error=None)

    def mark_failed(self, job_id: str, error: str) -> None:
        self._update(job_id, status="failed", error=error)

    def _update(self, job_id: str, **changes: object) -> None:
        with self._lock:
            record = self._jobs[job_id]
            for field, value in changes.items():
                setattr(record, field, value)

    @staticmethod
    def _copy(record: JobRecord) -> JobRecord:
        return JobRecord(
            job_id=record.job_id,
            status=record.status,
            report=record.report,
            error=record.error,
        )
