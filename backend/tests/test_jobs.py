import asyncio

import pytest
from fakes import SAMPLE_JD, FakeGateway, ScriptedAgentsLLM

from cvscore.agents import JobFailed, run_job
from cvscore.jobs import JobManager, QueueFull
from cvscore.llm import LLMError
from cvscore.schemas import AnalysisResult, ScoreResult

CV_ID = "a" * 32


pytestmark = pytest.mark.skip(reason="job queue is not implemented yet")


def result(score=50) -> AnalysisResult:
    breakdown = ScoreResult(
        score=score, must_met=0, must_total=0, nice_met=0, nice_total=0, per_requirement=[]
    )
    return AnalysisResult(score=score, breakdown=breakdown, suggestions=[])


async def wait_for(manager, job_id, statuses=("done", "failed"), timeout=2.0):
    async with asyncio.timeout(timeout):
        while manager.get(job_id).status not in statuses:
            await asyncio.sleep(0.01)
    return manager.get(job_id)


@pytest.fixture
async def make_manager(tmp_path):
    managers = []

    def make(runner, **kwargs):
        manager = JobManager(runner, storage_dir=tmp_path, **kwargs)
        managers.append(manager)
        return manager

    yield make
    for manager in managers:
        await manager.stop()


async def test_job_goes_from_queued_to_done_and_reports_steps(make_manager):
    seen = []

    async def runner(job_id, cv_id, jd_text, on_step):
        on_step("Reading the job description")
        seen.append(jd_text)
        return result(70)

    manager = make_manager(runner)
    job_id = manager.submit(CV_ID, "the jd")
    assert manager.get(job_id).status == "queued"
    manager.start()

    state = await wait_for(manager, job_id)

    assert (state.status, state.result.score) == ("done", 70)
    assert seen == ["the jd"]


async def test_unknown_job_is_none(make_manager):
    assert make_manager(None).get("nope") is None


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (JobFailed("The job description is too short."), "too short"),
        (LLMError("secret details"), "not available"),
        (RuntimeError("secret details"), "Unexpected"),
    ],
)
async def test_failures_become_a_failed_state_with_a_safe_message(make_manager, error, expected):
    async def runner(*_):
        raise error

    manager = make_manager(runner)
    manager.start()
    job_id = manager.submit(CV_ID, "jd")

    state = await wait_for(manager, job_id)

    assert state.status == "failed"
    assert expected in state.error
    assert "secret" not in state.error


async def test_job_timeout(make_manager):
    async def runner(*_):
        await asyncio.sleep(10)

    manager = make_manager(runner, job_timeout=0.05)
    manager.start()
    job_id = manager.submit(CV_ID, "jd")

    state = await wait_for(manager, job_id)

    assert state.status == "failed"
    assert "too long" in state.error


async def test_queue_limit(make_manager):
    manager = make_manager(None, max_queue=2)  # not started: nothing consumes

    manager.submit(CV_ID, "a")
    manager.submit(CV_ID, "b")
    with pytest.raises(QueueFull):
        manager.submit(CV_ID, "c")


async def test_at_most_k_jobs_run_at_the_same_time(make_manager):
    running = peak = 0

    async def runner(*_):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.02)
        running -= 1
        return result()

    manager = make_manager(runner, k_consumers=3)
    ids = [manager.submit(CV_ID, "jd") for _ in range(12)]
    manager.start()

    for job_id in ids:
        assert (await wait_for(manager, job_id)).status == "done"

    assert peak == 3


async def test_cv_is_deleted_when_the_job_ends(make_manager, tmp_path, monkeypatch):
    deleted = []
    monkeypatch.setattr(
        "cvscore.jobs.manager.delete_cv", lambda cv_id, d=None: deleted.append(cv_id)
    )

    async def runner(*_):
        return result()

    manager = make_manager(runner)
    manager.start()
    job_id = manager.submit(CV_ID, "jd")
    await wait_for(manager, job_id)
    await asyncio.sleep(0)

    assert deleted == [CV_ID]


async def test_sweep_forgets_old_finished_jobs_only(make_manager):
    async def runner(*_):
        return result()

    manager = make_manager(runner, ttl_seconds=100)
    manager.start()
    done_id = manager.submit(CV_ID, "jd")
    await wait_for(manager, done_id)
    await asyncio.sleep(0.01)

    assert manager.sweep(now=manager._jobs[done_id].finished_at + 50) == 0
    assert manager.get(done_id) is not None
    assert manager.sweep(now=manager._jobs[done_id].finished_at + 101) == 1
    assert manager.get(done_id) is None


async def test_many_jobs_through_the_real_orchestrator(make_manager):
    """40 users at once, with the scripted model and no sleeping: nothing blocks, nothing fails."""

    async def runner(job_id, cv_id, jd_text, on_step):
        return await run_job(
            job_id, cv_id, jd_text, llm=ScriptedAgentsLLM(), gateway=FakeGateway(), on_step=on_step
        )

    manager = make_manager(runner, k_consumers=4, max_queue=100)
    ids = [manager.submit(CV_ID, SAMPLE_JD) for _ in range(40)]
    manager.start()

    states = [await wait_for(manager, job_id, timeout=10) for job_id in ids]

    assert [s.status for s in states] == ["done"] * 40
    assert {s.result.score for s in states} == {70}
