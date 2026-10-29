# Architecture

```
api -> jobs -> agents -> mcp_client -> (HTTP) -> mcp_server -> services
```

## Parts

| Part | Kind | What it does |
|---|---|---|
| Orchestrator | LLM agent | Goal, plan, act, observe. Tools: `delegate`, `finish`. Step limit. |
| Registry | catalog | Sub-agents with their allowed tools (`agents/registry.py`). |
| Memory | per-job state | Requirements, matches, verification, score. Dies with the job. |
| JD Analyst | LLM, no tools | Job description (untrusted) -> list of requirements. |
| CV Matcher | LLM + tools | Looks for evidence in the CV with `search_cv` / `get_section`. |
| Evaluator | code + LLM | Verifies quotes and computes the score through the gateway (code); the LLM only writes the suggestions. |
| Tool Gateway | MCP server | Single door to the services: `parse_cv`, `get_section`, `search_cv`, `verify_evidence`, `compute_score`. |
| Services | deterministic | CV parsing and search, quote verification, scoring formula. |

## One job

1. JD Analyst turns the job description into requirements (`must` / `nice`).
2. CV Matcher answers each requirement with `yes` / `partial` / `no` plus a quote from the CV.
3. Evaluator checks every quote against the CV. A quote that is not there does not count.
4. If some checks failed, the Orchestrator sends only those requirements back to the Matcher
   (at most `MAX_MATCH_ATTEMPTS` times per requirement, enforced in code).
5. Evaluator computes the score (code) and writes suggestions (LLM).
6. Orchestrator calls `finish`.

## Decisions worth knowing

- The score is computed by code: `must` weight 3, `nice` weight 1; `yes` 1, `partial` 0.5,
  `no` 0; an unverified claim counts 0.
- The agent loop is written by hand: the agent's memory is the growing message list, and
  there is a hard step limit. On the last step the tools are taken away.
- Files travel by `cv_id`. CV text never goes through the Orchestrator.
- The job description and the CV are untrusted input: they appear only as delimited data in
  the user message, never in a system prompt, and the JD Analyst has no tools.
- Verdicts are `yes` / `partial` / `no` (English), not the Italian draft in the handoff.

## Known limits

- The gateway has no authentication.
- Fuzzy verification (threshold 0.85) can accept a quote where only a number changed.
- The queue is in-process: jobs are lost on restart, one process only.
- Only tested with a scripted model so far; real models, especially small ones, may need the
  "JSON action" fallback for tool calling.
