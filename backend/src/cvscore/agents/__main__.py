"""Run one job from the command line.

    uv run python -m cvscore.agents path/to/cv.pdf path/to/job_description.txt

The tool gateway must already be running (`uv run python -m cvscore.mcp_server`).
"""

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

from cvscore.agents.orchestrator import JobFailed, run_job
from cvscore.config import get_settings
from cvscore.llm.base import LLMError
from cvscore.logging_setup import setup_logging
from cvscore.mcp_client import Gateway, GatewayError
from cvscore.storage import StorageError, delete_cv, save_cv


async def main(cv_path: Path, jd_path: Path) -> int:
    # Imported here: the module needs the `openai` package, which the agents never import.
    from cvscore.llm.openai_client import OpenAICompatibleClient

    settings = get_settings()
    llm = OpenAICompatibleClient(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        timeout=settings.llm_timeout_seconds,
    )
    jd_text = jd_path.read_text(encoding="utf-8")
    try:
        cv_id = save_cv(cv_path.read_bytes(), cv_path.name)
    except StorageError as exc:
        print(f"Cannot use the CV: {exc}", file=sys.stderr)
        return 2

    job_id = uuid.uuid4().hex[:8]
    try:
        async with Gateway() as gateway:
            result = await run_job(
                job_id,
                cv_id,
                jd_text,
                llm=llm,
                gateway=gateway,
                max_steps=settings.max_agent_steps,
                on_step=lambda step: print(f"... {step}", file=sys.stderr),
            )
    except (JobFailed, LLMError, GatewayError) as exc:
        print(f"Job failed: {exc}", file=sys.stderr)
        return 1
    finally:
        delete_cv(cv_id)

    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Score a CV against a job description.")
    parser.add_argument("cv", type=Path, help="CV file (.pdf or .docx)")
    parser.add_argument("jd", type=Path, help="text file with the job description")
    args = parser.parse_args()
    setup_logging()
    sys.exit(asyncio.run(main(args.cv, args.jd)))
