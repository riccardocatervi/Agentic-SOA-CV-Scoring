import asyncio

import pytest
from helpers import make_pdf
from httpx import ASGITransport, AsyncClient

from cvscore.api import create_app
from cvscore.config import get_service_settings
from cvscore.jobs import JobManager
from cvscore.schemas import AnalysisResult, ScoreResult

JD = "We are hiring a Python developer who knows Docker."
PDF = make_pdf(["JOHN DOE", "Python developer"])


pytestmark = pytest.mark.skip(reason="API is not implemented yet")


def a_result() -> AnalysisResult:
    breakdown = ScoreResult(
        score=80, must_met=1, must_total=1, nice_met=0, nice_total=0, per_requirement=[]
    )
    return AnalysisResult(score=80, breakdown=breakdown, suggestions=[])


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    get_service_settings.cache_clear()

    async def runner(job_id, cv_id, jd_text, on_step):
        on_step("Working")
        return a_result()

    manager = JobManager(runner, max_queue=2, storage_dir=tmp_path)
    app = create_app(manager)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c,
    ):
        yield c
    get_service_settings.cache_clear()


def upload(content=PDF, name="cv.pdf", jd=JD):
    return {"files": {"cv": (name, content, "application/pdf")}, "data": {"jd_text": jd}}


async def poll(client, job_id):
    async with asyncio.timeout(2):
        while True:
            body = (await client.get(f"/api/jobs/{job_id}")).json()
            if body["status"] in ("done", "failed"):
                return body
            await asyncio.sleep(0.01)


async def test_health(client):
    assert (await client.get("/api/health")).json() == {"status": "ok"}


async def test_upload_returns_202_and_the_job_completes(client):
    response = await client.post("/api/analyze", **upload())

    assert response.status_code == 202
    body = await poll(client, response.json()["job_id"])
    assert body["status"] == "done"
    assert body["result"]["score"] == 80


async def test_unknown_job_is_404(client):
    assert (await client.get("/api/jobs/" + "f" * 32)).status_code == 404


@pytest.mark.parametrize(
    ("kwargs", "status"),
    [
        (upload(name="cv.exe"), 400),
        (upload(content=b"not a pdf", name="cv.pdf"), 400),
        (upload(content=b"", name="cv.pdf"), 400),
        (upload(jd="   "), 422),
        (upload(jd="x" * 30_000), 413),
    ],
)
async def test_bad_uploads_are_rejected(client, kwargs, status):
    assert (await client.post("/api/analyze", **kwargs)).status_code == status


async def test_missing_fields_are_422(client):
    assert (await client.post("/api/analyze", data={"jd_text": JD})).status_code == 422


async def test_503_when_the_queue_is_full(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path))
    get_service_settings.cache_clear()
    manager = JobManager(None, max_queue=1, storage_dir=tmp_path)  # never started
    app = create_app(manager)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as c:
        app.state.manager = manager  # no lifespan here: the queue is never consumed
        assert (await c.post("/api/analyze", **upload())).status_code == 202
        response = await c.post("/api/analyze", **upload())
    get_service_settings.cache_clear()

    assert response.status_code == 503
    assert len(list(tmp_path.glob("*"))) == 1  # the rejected upload left no file behind
