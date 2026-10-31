"""In-process job queue: one asyncio.Queue and K consumer tasks.

Known limits to write in the report: jobs live in memory, so a restart loses them, and the
service cannot run in more than one process. Orphan CVs are purged by file age, so a job that
waits in the queue longer than the TTL could lose its CV (unlikely with TTL >> job timeout).
"""

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from cvscore.agents import JobFailed
from cvscore.llm.base import LLMError
from cvscore.logging_setup import job_id_var
from cvscore.mcp_client import GatewayError
from cvscore.schemas import AnalysisResult, JobState
from cvscore.storage import delete_cv, purge_expired

log = logging.getLogger("cvscore.jobs")

# (job_id, cv_id, jd_text, on_step) -> result. The real one comes from make_runner().
JobRunner = Callable[[str, str, str, Callable[[str], None]], Awaitable[AnalysisResult]]

# Messages shown to the user: they never carry exception text from the model or the services.
MSG_TIMEOUT = "The analysis took too long. Please try again later."
MSG_UNAVAILABLE = "A required service is not available. Please try again later."
MSG_SHUTDOWN = "The service is shutting down. Please try again later."
MSG_UNEXPECTED = "Unexpected error during the analysis. Please try again later."


class QueueFull(Exception):
    """Too many jobs are waiting. The API turns it into a 503."""


@dataclass
class _Job:
    state: JobState
    cv_id: str
    jd_text: str | None  # dropped as soon as the job ends
    finished_at: float | None = None


class JobManager:
    def __init__(
        self,
        runner: JobRunner,
        *,
        k_consumers: int = 2,
        max_queue: int = 100,
        job_timeout: float = 600.0,
        ttl_seconds: int = 3600,
        storage_dir: Path | None = None,
    ):
        """Keep the settings. Queue and job dict are created here, tasks only in start()."""
        self._runner = runner
        self._k_consumers = k_consumers
        self._job_timeout = job_timeout
        self._ttl_seconds = ttl_seconds
        self._storage_dir = storage_dir
        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=max_queue)
        self._jobs: dict[str, _Job] = {}
        self._tasks: list[asyncio.Task] = []

    def start(self) -> None:
        """Create K consumer tasks plus one janitor task. Call it from the app lifespan."""
        if self._tasks:
            return
        self._tasks = [
            asyncio.create_task(self._consume(worker), name=f"job-consumer-{worker}")
            for worker in range(self._k_consumers)
        ]
        self._tasks.append(asyncio.create_task(self._janitor(), name="job-janitor"))

    async def stop(self) -> None:
        """Cancel every task and wait for them."""
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    def submit(self, cv_id: str, jd_text: str) -> str:
        """Register a job as `queued`, put it in the queue and return its id (uuid4 hex)."""
        job_id = uuid.uuid4().hex
        try:
            self._queue.put_nowait(job_id)
        except asyncio.QueueFull:
            raise QueueFull from None
        # No await since put_nowait: no consumer can pick the id before it is registered.
        self._jobs[job_id] = _Job(JobState(id=job_id, status="queued"), cv_id, jd_text)
        log.info("queued job=%s waiting=%d", job_id, self._queue.qsize())
        return job_id

    def get(self, job_id: str) -> JobState | None:
        """Current state of a job, None if unknown or already swept."""
        job = self._jobs.get(job_id)
        return job.state.model_copy() if job else None

    async def _consume(self, worker: int) -> None:
        """Forever: take a job id, process it. A worker must never die, whatever happens."""
        while True:
            job_id = await self._queue.get()
            try:
                await self._process(job_id)
            except Exception:
                log.exception("worker %d failed on job %s", worker, job_id)
            finally:
                self._queue.task_done()

    async def _process(self, job_id: str) -> None:
        """Run one job: processing -> done | failed, then forget the JD and delete the CV."""
        job = self._jobs.get(job_id)
        if job is None:
            return
        token = job_id_var.set(job_id)
        state = job.state
        state.status = "processing"

        def on_step(step: str) -> None:
            state.step = step

        try:
            log.info("processing")
            async with asyncio.timeout(self._job_timeout):
                result = await self._runner(job_id, job.cv_id, job.jd_text, on_step)
        except JobFailed as exc:
            self._fail(state, str(exc), exc)
        except TimeoutError as exc:
            self._fail(state, MSG_TIMEOUT, exc)
        except (LLMError, GatewayError) as exc:
            self._fail(state, MSG_UNAVAILABLE, exc)
        except asyncio.CancelledError as exc:
            self._fail(state, MSG_SHUTDOWN, exc)
            raise
        except Exception as exc:
            log.exception("unexpected error")
            self._fail(state, MSG_UNEXPECTED, exc)
        else:
            state.status = "done"
            state.result = result
            state.step = None
            log.info("done score=%d", result.score)
        finally:
            job.finished_at = time.time()
            job.jd_text = None
            delete_cv(job.cv_id, self._storage_dir)  # a CV is personal data
            job_id_var.reset(token)

    @staticmethod
    def _fail(state: JobState, message: str, exc: BaseException) -> None:
        state.status = "failed"
        state.error = message
        state.step = None
        log.warning("failed reason=%s", type(exc).__name__)  # never the exception text

    def sweep(self, now: float | None = None) -> int:
        """Forget finished jobs older than the TTL, delete orphan CV files.

        Returns how many jobs were forgotten. Never touches jobs that are not finished.
        """
        now = time.time() if now is None else now
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if job.finished_at is not None and now - job.finished_at > self._ttl_seconds
        ]
        for job_id in expired:
            del self._jobs[job_id]
        purge_expired(self._ttl_seconds, self._storage_dir, now=now)
        return len(expired)

    async def _janitor(self) -> None:
        """Call sweep() every ttl/4 seconds, clamped between 1 and 300."""
        interval = min(300.0, max(1.0, self._ttl_seconds / 4))
        while True:
            await asyncio.sleep(interval)
            try:
                if forgotten := self.sweep():
                    log.info("swept %d finished jobs", forgotten)
            except Exception:
                log.exception("sweep failed")
