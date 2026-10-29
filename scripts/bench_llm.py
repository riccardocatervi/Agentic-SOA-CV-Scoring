"""Benchmark an OpenAI-compatible LLM server. Run it before choosing K, model and tool mode.

    uv run python scripts/bench_llm.py

Reads LLM_* from .env, prints a markdown table to paste into docs/. Use synthetic prompts only,
never a real CV.

What to measure (see HANDOFF section 6b and M2):
- latency of one call, and the cold start (first call after the model was idle);
- tokens per second;
- does it support tool calling? does it support structured output (json_schema)?
- "needle in a haystack": put a fact at the start of a long prompt and ask about it. If the
  server silently cuts the context (Ollama's default is small) the answer is lost;
- concurrency 1, 2, 4, 8: error count, median and slowest latency, requests per second.
  Build the client with max_retries=0 here so failures are visible.
"""


def main() -> None:
    raise NotImplementedError


if __name__ == "__main__":
    main()
