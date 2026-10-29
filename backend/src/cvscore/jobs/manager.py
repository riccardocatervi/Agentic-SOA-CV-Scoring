"""In-process job queue: one asyncio.Queue and K consumer tasks.

Known limits to write in the report: jobs live in memory, so a restart loses them, and the
service cannot run in more than one process.
"""

from collections.abc import Awaitable, Callable
from pathlib import Path

from cvscore.schemas import AnalysisResult, JobState

# (job_id, cv_id, jd_text, on_step) -> result. The real one comes from make_runner().
JobRunner = Callable[[str, str, str, Callable[[str], None]], Awaitable[AnalysisResult]]


class QueueFull(Exception):
    """Too many jobs are waiting. The API turns it into a 503."""


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
        raise NotImplementedError

    def start(self) -> None:
        """Create K consumer tasks plus one janitor task. Call it from the app lifespan."""
        raise NotImplementedError

    async def stop(self) -> None:
        """Cancel every task and wait for them."""
        raise NotImplementedError

    def submit(self, cv_id: str, jd_text: str) -> str:
        """Register a job as `queued`, put it in the queue and return its id (uuid4 hex).

        Use put_nowait: if the queue is full raise QueueFull and do NOT register the job.
        """
        raise NotImplementedError

    def get(self, job_id: str) -> JobState | None:
        """Current state of a job, None if unknown or already swept."""
        raise NotImplementedError

    async def _consume(self, worker: int) -> None:
        """Forever: take a job id, process it. A worker must never die, whatever happens."""
        raise NotImplementedError

    async def _process(self, job_id: str) -> None:
        """Run one job.

        - state -> processing; the on_step callback updates `step` (this is what the UI shows).
        - Wrap the runner in asyncio.timeout(job_timeout).
        - Success -> done with the result.
        - Failure -> failed with a SAFE message for the user, by error type:
            JobFailed: its own message; TimeoutError: "took too long"; LLMError / GatewayError:
            "a required service is not available"; anything else: a generic message, and log the
            traceback. Never put exception text from the model or the services in the state.
        - In every case, at the end: remember when it finished, drop the JD text from memory and
          delete the CV file (storage.delete_cv). A CV is personal data.
        """
        raise NotImplementedError

    def sweep(self, now: float | None = None) -> int:
        """Forget finished jobs older than the TTL, delete orphan CV files (storage.purge_expired).

        Returns how many jobs were forgotten. Never touch jobs that are not finished.
        """
        raise NotImplementedError

    async def _janitor(self) -> None:
        """Call sweep() every now and then (about ttl/4, but between 1 and 300 seconds)."""
        raise NotImplementedError
