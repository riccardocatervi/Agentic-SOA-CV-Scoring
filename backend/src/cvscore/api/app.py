"""HTTP API: upload a CV and a job description, poll for the result.

The frontend already exists, so the exact paths and fields come from docs/api-contract.md.
Until that document says otherwise, this is the shape we assume.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

    from cvscore.jobs import JobManager


def build_manager() -> "JobManager":
    """Real wiring: settings -> OpenAICompatibleClient -> make_runner -> JobManager.

    Read everything from get_settings(). Import OpenAICompatibleClient inside the function.
    """
    raise NotImplementedError


def create_app(manager: "JobManager | None" = None) -> "FastAPI":
    """Build the FastAPI app. Pass a manager in tests, leave None in production.

    - lifespan: setup_logging(), build the manager if needed, manager.start(), yield,
      manager.stop(). Keep the manager in app.state.
    - GET /api/health -> {"status": "ok"}
    - POST /api/analyze (multipart: file field `cv`, form field `jd_text`) -> 202 {"job_id": ...}
        422 empty JD, 413 JD over 20000 chars, 400 for anything storage.save_cv rejects
        (type, size, magic bytes), 503 if the queue is full (delete the CV you just saved).
        Read at most MAX_UPLOAD_BYTES + 1 bytes from the upload.
    - GET /api/jobs/{job_id} -> JobState, 404 if unknown.
    Never log the CV or JD content.
    """
    raise NotImplementedError


def app_factory() -> "FastAPI":
    """Entry point for uvicorn: `uvicorn cvscore.api.app:app_factory --factory`."""
    return create_app()
