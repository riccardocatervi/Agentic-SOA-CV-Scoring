"""The Orchestrator: Goal -> Plan -> Act -> Observe, repeated until the goal is reached.

It is an LLM agent whose only tools are `delegate` (hand work to a sub-agent) and `finish`.
It never touches the services and never sees the CV or the raw job description: it reads the
short results that `delegate` returns, and the shared state lives in JobMemory.
"""

import logging
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from cvscore.agents import evaluator
from cvscore.agents.cv_matcher import match_requirements
from cvscore.agents.jd_analyst import analyze_jd
from cvscore.agents.loop import (
    AgentOutputError,
    StepLimitExceeded,
    load_prompt,
    run_loop,
)
from cvscore.agents.memory import MAX_MATCH_ATTEMPTS, JobMemory
from cvscore.agents.registry import REGISTRY, describe
from cvscore.llm.base import LLMClient
from cvscore.logging_setup import job_id_var
from cvscore.mcp_client import Gateway, ToolResult
from cvscore.schemas import AnalysisResult

log = logging.getLogger("cvscore.job")


class JobFailed(Exception):
    """The job cannot be completed. The message is safe to show to the user."""


class DelegateArgs(BaseModel):
    agent: Literal["jd_analyst", "cv_matcher", "evaluator"]
    task: str | None = Field(
        default=None, description="For the evaluator only: 'verify' or 'report'."
    )
    requirement_ids: list[int] | None = Field(
        default=None,
        description="For cv_matcher: only these requirements (use it to retry the failed ones).",
    )


def _ok(text: str) -> ToolResult:
    return ToolResult(text=text, data=None, is_error=False)


def _err(text: str) -> ToolResult:
    return ToolResult(text=f"ERROR: {text}", data=None, is_error=True)


class DelegateTools:
    """The orchestrator's tools. They run in-process; the sub-agents use MCP underneath."""

    done = False

    def __init__(
        self,
        memory: JobMemory,
        jd_text: str,
        llm: LLMClient,
        gateway: Gateway,
        *,
        max_steps: int,
        on_step: Callable[[str], None] | None = None,
    ):
        self._memory = memory
        self._jd_text = jd_text
        self._llm = llm
        self._gateway = gateway
        self._max_steps = max_steps
        self._on_step = on_step or (lambda _: None)

    async def specs(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "delegate",
                    "description": "Hand a piece of work to a specialist agent and get a short "
                    "report back.",
                    "parameters": DelegateArgs.model_json_schema(),
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "finish",
                    "description": "Call it when the score and the suggestions are ready.",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ]

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        if name == "finish":
            return self._finish()
        if name != "delegate":
            return _err(f"unknown tool '{name}'. Use delegate or finish.")
        try:
            args = DelegateArgs.model_validate(arguments)
        except ValidationError as exc:
            problems = "; ".join(f"{e['loc'][0]}: {e['msg']}" for e in exc.errors())
            return _err(f"bad arguments ({problems})")
        match args.agent:
            case "jd_analyst":
                return await self._jd_analyst()
            case "cv_matcher":
                return await self._cv_matcher(args.requirement_ids)
            case "evaluator":
                return await self._evaluator(args.task)

    # --- actions -------------------------------------------------------------------------

    async def _jd_analyst(self) -> ToolResult:
        memory = self._memory
        if memory.requirements:
            return _err(f"jd_analyst already ran: {len(memory.requirements)} requirements.")
        self._on_step("Analyzing the job description")
        try:
            outcome = await analyze_jd(self._llm, self._jd_text)
        except ValueError as exc:
            raise JobFailed(str(exc)) from exc  # e.g. empty job description: retrying is useless
        except AgentOutputError as exc:
            return _err(f"jd_analyst could not produce valid output ({exc}).")
        memory.requirements = outcome.value.requirements
        memory.usage = memory.usage + outcome.usage
        musts = sum(1 for r in memory.requirements if r.kind == "must")
        return _ok(f"{len(memory.requirements)} requirements extracted ({musts} must, "
                   f"{len(memory.requirements) - musts} nice).")  # fmt: skip

    async def _cv_matcher(self, requested: list[int] | None) -> ToolResult:
        memory = self._memory
        if not memory.requirements:
            return _err("no requirements yet: run jd_analyst first.")
        known = set(memory.requirement_ids())
        ids = requested if requested else memory.unmatched_ids()
        if not ids:
            return _err("nothing to match. Pass requirement_ids to retry specific ones.")
        unknown = [i for i in ids if i not in known]
        if unknown:
            return _err(f"unknown requirement ids {unknown}. Valid ids: {sorted(known)}.")
        exhausted = [i for i in ids if memory.attempts.get(i, 0) >= MAX_MATCH_ATTEMPTS]
        ids = [i for i in ids if i not in exhausted]
        if not ids:
            return _err(f"retry limit reached for {exhausted}. Continue with the evaluator report.")

        feedback = None
        retrying = [i for i in ids if i in memory.failed_ids()]
        if retrying:
            feedback = (
                f"For requirements {retrying} the quotes you gave before were NOT found in the "
                "CV. Search again. If there is no real evidence, answer 'no' with null evidence."
            )
        self._on_step("Searching the CV for evidence")
        try:
            outcome = await match_requirements(
                self._llm,
                self._gateway.toolbox(REGISTRY["cv_matcher"].allowed_tools),
                memory.cv_id,
                [r for r in memory.requirements if r.id in ids],
                feedback=feedback,
                max_steps=self._max_steps,
            )
        except (AgentOutputError, StepLimitExceeded) as exc:
            return _err(f"cv_matcher failed ({exc}).")
        memory.record_matches(outcome.value)
        memory.usage = memory.usage + outcome.usage
        counts = {
            v: sum(1 for m in outcome.value if m.verdict == v) for v in ("yes", "partial", "no")
        }
        text = f"matched {len(outcome.value)} requirements: {counts}."
        if memory.unmatched_ids():
            text += f" Still without an answer: {memory.unmatched_ids()}."
        return _ok(text)

    async def _evaluator(self, task: str | None) -> ToolResult:
        if task == "verify":
            return await self._verify()
        if task == "report":
            return await self._report()
        return _err("evaluator needs task 'verify' or 'report'.")

    async def _verify(self) -> ToolResult:
        memory = self._memory
        if not memory.matches:
            return _err("nothing to verify: run cv_matcher first.")
        pending = memory.unchecked_ids()
        if not pending:
            return _err("everything is already verified.")
        self._on_step("Verifying the quotes against the CV")
        toolbox = self._gateway.toolbox(REGISTRY["evaluator"].allowed_tools)
        checked = await evaluator.verify_matches(
            toolbox, memory.cv_id, [memory.matches[i] for i in pending]
        )
        for item in checked:
            memory.verified[item.requirement_id] = item
        failed = memory.failed_ids()
        text = f"checked {len(checked)} answers; quotes not found for requirement_ids {failed}."
        if failed:
            retry = memory.retryable_ids()
            text += (
                f" cv_matcher can retry {retry}." if retry
                else " No retries left: they will score 0."
            )  # fmt: skip
        else:
            text = f"checked {len(checked)} answers; all quotes found."
        return _ok(text)

    async def _report(self) -> ToolResult:
        memory = self._memory
        if memory.unmatched_ids():
            return _err(f"requirements {memory.unmatched_ids()} have no answer: run cv_matcher.")
        if memory.unchecked_ids():
            return _err("some answers are not verified yet: run the evaluator with task 'verify'.")
        self._on_step("Computing the score")
        toolbox = self._gateway.toolbox(REGISTRY["evaluator"].allowed_tools)
        verified = [memory.verified[r.id] for r in memory.requirements]
        score = await evaluator.compute_score(toolbox, memory.requirements, verified)
        self._on_step("Writing suggestions")
        advice = await evaluator.write_suggestions(self._llm, memory.requirements, score)
        memory.usage = memory.usage + advice.usage
        memory.result = AnalysisResult(score=score.score, breakdown=score, suggestions=advice.value)
        return _ok(
            f"score {score.score}/100 (must {score.must_met}/{score.must_total}); "
            f"{len(advice.value)} suggestions written. Call finish."
        )

    def _finish(self) -> ToolResult:
        memory = self._memory
        if memory.result is None:
            return _err("not ready: run evaluator with task 'report' first.")
        self.done = True
        return _ok("done.")


async def run_job(
    job_id: str,
    cv_id: str,
    jd_text: str,
    *,
    llm: LLMClient,
    gateway: Gateway,
    max_steps: int = 10,
    on_step: Callable[[str], None] | None = None,
) -> AnalysisResult:
    """Run one job from start to finish. Raises JobFailed (safe message) or an infrastructure error."""
    memory = JobMemory(job_id=job_id, cv_id=cv_id)
    tools = DelegateTools(memory, jd_text, llm, gateway, max_steps=max_steps, on_step=on_step)
    system_prompt = load_prompt("orchestrator").replace("{agents}", describe())
    goal = (
        f"Goal: analyze the CV with id {cv_id} against the job description and finish with a "
        "verified score and suggestions."
    )
    token = job_id_var.set(job_id)
    try:
        log.info("start")
        try:
            run = await run_loop(
                llm,
                system_prompt=system_prompt,
                user_message=goal,
                tools=tools,
                max_steps=max_steps,
                max_tokens=256,
                label="orchestrator",
            )
        except StepLimitExceeded as exc:
            raise JobFailed(f"the analysis needed more than {max_steps} steps") from exc
        memory.usage = memory.usage + run.usage
        if memory.result is None:
            raise JobFailed("the analysis stopped before producing a result")
        log.info(
            "done score=%d prompt_tokens=%d completion_tokens=%d",
            memory.result.score, memory.usage.prompt_tokens, memory.usage.completion_tokens,
        )  # fmt: skip
        return memory.result
    finally:
        job_id_var.reset(token)
