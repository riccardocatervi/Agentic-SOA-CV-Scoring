"""Logging that can be followed per job: every line carries the job id, without passing it around.

Rule: logs never contain CV or job description content, only ids, step names and counters.
"""

import logging
from contextvars import ContextVar

job_id_var: ContextVar[str] = ContextVar("job_id", default="-")


class JobIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.job_id = job_id_var.get()
        return True


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.addFilter(JobIdFilter())
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s job=%(job_id)s %(name)s %(message)s")
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
