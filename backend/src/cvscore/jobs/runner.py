"""Glue between the job queue and the agents: one gateway connection per job."""

from collections.abc import Callable

from cvscore.agents import run_job
from cvscore.jobs.manager import JobRunner
from cvscore.llm.base import LLMClient
from cvscore.mcp_client import Gateway
from cvscore.schemas import AnalysisResult


def make_runner(
    llm: LLMClient, *, gateway_url: str | None = None, max_steps: int = 10
) -> JobRunner:
    async def run(
        job_id: str, cv_id: str, jd_text: str, on_step: Callable[[str], None]
    ) -> AnalysisResult:
        async with Gateway(gateway_url) as gateway:
            return await run_job(
                job_id,
                cv_id,
                jd_text,
                llm=llm,
                gateway=gateway,
                max_steps=max_steps,
                on_step=on_step,
            )

    return run
