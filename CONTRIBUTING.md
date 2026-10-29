# Contributing

Three people, one repo. This is how we avoid stepping on each other.

## Who owns what

| Area | Files | Owner |
|---|---|---|
| Agents, tool gateway | `agents/`, `mcp_client/`, `mcp_server/server.py` | Riccardo |
| Services and LLM client | `mcp_server/services/`, `llm/openai_client.py`, `scripts/bench_llm.py` | B |
| API, queue, deploy | `api/`, `jobs/manager.py`, Docker, `loadtest/`, `docs/api-contract.md`, frontend glue | C |
| Shared contracts | `schemas/`, `config.py`, `storage.py`, `llm/base.py` | everyone, by agreement |

If you need to change a file you do not own, say so in the PR. For the shared contracts,
get a yes from the other two first: a wrong contract costs more than any bug.

## What is left to do (B and C)

The skeletons are in place: classes, signatures and a docstring that says what to do.
The tests already exist and are skipped. The workflow is:

1. Open the skipped test file for your area and delete the `pytestmark = pytest.mark.skip(...)` line.
2. Run it, see it fail, write the code until it passes.
3. `uv run ruff check` and `uv run ruff format` must be clean.

| Who | Skeletons | Tests to enable |
|---|---|---|
| B | `mcp_server/services/{cv,verify,scoring}_service.py`, `llm/openai_client.py`, `scripts/bench_llm.py` | `test_services_*.py`, `test_openai_client.py` |
| C | `jobs/manager.py`, `api/app.py` | `test_jobs.py`, `test_api.py` |

When everything is in, `test_e2e_real.py` and `test_system.py` run a whole job through the
real stack (with a scripted model instead of a real one). Enable `test_system.py` last.
`pypdf` and `python-docx` are not in `pyproject.toml` yet: B adds them (`uv add pypdf python-docx`).

## Dependency rule

```
api -> jobs -> agents -> mcp_client -> (HTTP) -> mcp_server -> services
```

`services/` never imports from `agents`, `api`, `jobs` or `llm`. Agents never import a
service directly: they go through the gateway. Only `llm/openai_client.py` imports `openai`.

## Branches

Never commit to `main` or `dev`. One branch per piece of work, merged into `dev` with a pull
request that somebody else looks at. `main` only gets merges from `dev`.

```
<type>/<area>-<short-description>
feat/services-cv-parsing
feat/llm-openai-client
feat/api-jobs
fix/jobs-queue-timeout
docs/api-contract
```

Lowercase, words separated by hyphens, no names or dates.

## Commits

```
<type>(<scope>): <what>
```

- type: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `style`
- scope: the area, for example `services`, `llm`, `api`, `jobs`, `agents`, `mcp-server`
- what: English, imperative, lowercase, no final dot, 72 characters at most

`feat(jobs): add queue with k consumers`, `fix(services): handle hyphens at line end`.

## Naming

- Modules and functions `snake_case`, classes `PascalCase`, constants `UPPER_SNAKE_CASE`.
- Services are named `<thing>_service.py` and expose plain functions.
- Tests live in `backend/tests/` and are named `test_<what>.py`.
- Prompts are `.md` files in `agents/prompts/`, never strings in the code.
- Code, comments, docs and commits in English.

## Privacy

A CV is personal data. Logs carry ids, step names and counters, never CV or job description
text. Uploaded files are deleted when the job ends.

## Running things

```
cd backend
uv sync
uv run ruff check && uv run ruff format --check
uv run pytest
uv run python -m cvscore.mcp_server      # the tool gateway
```
