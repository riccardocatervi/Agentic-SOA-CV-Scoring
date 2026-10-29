import pytest
from fakes import SAMPLE_JD, FakeGateway, ScriptedAgentsLLM

from cvscore.agents import JobFailed, run_job
from cvscore.agents.memory import MAX_MATCH_ATTEMPTS, JobMemory
from cvscore.agents.orchestrator import DelegateTools
from cvscore.llm import FakeLLMClient
from cvscore.llm.fake import text, tool_call
from cvscore.logging_setup import job_id_var
from cvscore.schemas import Requirement

CV_ID = "a" * 32


async def run(llm, jd=SAMPLE_JD, gateway=None, **kwargs):
    steps: list[str] = []
    result = await run_job(
        "job-1",
        CV_ID,
        jd,
        llm=llm,
        gateway=gateway or FakeGateway(),
        on_step=steps.append,
        **kwargs,
    )
    return result, steps


# --- a whole job ------------------------------------------------------------------------------


async def test_whole_job_with_a_hallucinated_quote_that_gets_caught_and_retried():
    llm, gateway = ScriptedAgentsLLM(), FakeGateway()

    result, steps = await run(llm, gateway=gateway)

    by_id = {r.requirement_id: r for r in result.breakdown.per_requirement}
    assert result.score == 70  # python 3 + docker 3 + pytest 1, kubernetes 0 -> 7/10
    assert by_id[3].verdict == "no"  # the invented Kubernetes quote did not survive the retry
    assert (result.breakdown.must_met, result.breakdown.must_total) == (2, 3)
    assert [s.requirement_id for s in result.suggestions] == [3]
    # The matcher ran twice (first pass + targeted retry); each run is search + answer.
    assert llm.calls_by_agent == {
        "JD Analyst": 1, "Orchestrator": 7, "CV Matcher": 4, "Evaluator": 1,
    }  # fmt: skip
    assert steps.count("Verifying the quotes against the CV") == 2


async def test_each_agent_only_touches_its_own_tools():
    gateway = FakeGateway()

    await run(ScriptedAgentsLLM(), gateway=gateway)

    used = {box.allowed: {name for name, _ in box.calls} for box in gateway.toolboxes}
    for allowed, names in used.items():
        assert names <= allowed
    assert len(gateway.toolboxes) >= 3


async def test_job_id_context_is_cleaned_up():
    await run(ScriptedAgentsLLM())

    assert job_id_var.get() == "-"


# --- when things go wrong ---------------------------------------------------------------------


async def test_orchestrator_that_never_finishes_hits_the_step_limit():
    llm = FakeLLMClient([tool_call("finish", {})] * 3)

    with pytest.raises(JobFailed, match="more than 3 steps"):
        await run(llm, max_steps=3)

    assert len(llm.calls) == 3


async def test_orchestrator_that_gives_up_early_fails_with_a_clear_message():
    llm = FakeLLMClient([text("I think we are done.")])

    with pytest.raises(JobFailed, match="before producing a result"):
        await run(llm)


async def test_a_job_description_that_is_too_short_fails_the_job_immediately():
    llm = FakeLLMClient([tool_call("delegate", {"agent": "jd_analyst"})])

    with pytest.raises(JobFailed, match="too short"):
        await run(llm, jd="hi")


# --- the guards inside the orchestrator's tools -----------------------------------------------


@pytest.fixture
def tools():
    memory = JobMemory(job_id="j", cv_id=CV_ID)
    memory.requirements = [
        Requirement(id=1, text="Python", kind="must"),
        Requirement(id=2, text="Docker", kind="nice"),
    ]
    return DelegateTools(memory, SAMPLE_JD, ScriptedAgentsLLM(), FakeGateway(), max_steps=5)


async def delegate(tools, **arguments):
    return await tools.call("delegate", arguments)


async def test_unknown_agent_is_a_readable_error(tools):
    result = await delegate(tools, agent="cto")

    assert result.is_error and "agent" in result.text


async def test_matcher_cannot_run_before_the_analyst():
    memory = JobMemory(job_id="j", cv_id=CV_ID)
    tools = DelegateTools(memory, SAMPLE_JD, ScriptedAgentsLLM(), FakeGateway(), max_steps=5)

    result = await delegate(tools, agent="cv_matcher")

    assert result.is_error and "jd_analyst first" in result.text


async def test_analyst_runs_only_once(tools):
    result = await delegate(tools, agent="jd_analyst")

    assert result.is_error and "already ran" in result.text


async def test_unknown_requirement_ids_are_rejected(tools):
    result = await delegate(tools, agent="cv_matcher", requirement_ids=[1, 42])

    assert result.is_error and "[42]" in result.text


async def test_retry_limit_is_enforced_in_code_not_by_the_model(tools):
    tools._memory.attempts = {1: MAX_MATCH_ATTEMPTS}

    result = await delegate(tools, agent="cv_matcher", requirement_ids=[1])

    assert result.is_error and "retry limit" in result.text


async def test_evaluator_needs_a_valid_task(tools):
    result = await delegate(tools, agent="evaluator", task="dance")

    assert result.is_error and "verify" in result.text


async def test_cannot_verify_or_report_too_early(tools):
    assert (await delegate(tools, agent="evaluator", task="verify")).is_error
    report = await delegate(tools, agent="evaluator", task="report")
    assert report.is_error and "run cv_matcher" in report.text


async def test_finish_is_refused_until_there_is_a_result(tools):
    result = await tools.call("finish", {})

    assert result.is_error
    assert not tools.done
