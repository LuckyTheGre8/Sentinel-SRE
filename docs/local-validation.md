# Observed local validation — 2026-10-24

Scope: Prompts 1–5 only. No remote is configured. No deployment, registration,
manifest publication, real PR, push, tag, payment or merge was performed.

## Milestones

- Foundation: 92 tests passed; commit `7f6c92e`.
- Evidence agents: 116 tests passed; commit `656c10c`.
- ACP orchestration: 121 tests passed and recorded conversation succeeded; commit `08824dd`.
- Safe remediation: 144 tests passed; commit `0c4092e`.
- Complete local demo: 150 tests passed in 4.91 seconds, including two real HTTP
  end-to-end runs. Final commit message: `test: add deterministic incident to recovery demo`.

## Commands and observed results

Commands ran from the repository root, with `UV_CACHE_DIR` pointing to `.uv-cache`
and `UV_PYTHON_INSTALL_DIR` pointing to `.python`.

```powershell
uv sync --frozen --offline
uv run --frozen pytest -q --basetemp=.local/pytest-final --tb=short
uv run --frozen python -m sentinel_ops.demo smoke --runs 2
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen mypy src/sentinel_ops
uv run --frozen python scripts/check_secrets.py
uv build --offline
.\.venv\Scripts\python.exe scripts/verify_artifacts.py
git diff --check
```

- Frozen offline dependency synchronization succeeded: 64 resolved packages.
- Pytest: **150 passed**.
- Ruff lint: **all checks passed**.
- Ruff format: **34 files already formatted**.
- Mypy: **no issues in 24 source files**.
- Pattern-based tracked-content secret scan: passed; staged-content scan also required
  before each milestone commit. This is not a guarantee of absence of every secret form.
- Wheel and source distribution built successfully. Artifact inspection found no
  local caches, environments, SQLite files, private-key paths or logs in either archive.
- Git whitespace checks passed.

## Two fresh standalone demo runs

First investigation: `bf67e20d-076f-4263-aa6a-cb296f521474`.
Second investigation: `b8580d9f-ba3b-449c-b6db-a1d93bdfeaa0`.

Both independently observed:

- Initial HTTP: **503**.
- First-ranked synthetic commit: `bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb`.
- Detected synthetic advisory: `DEMO-2026-001`.
- Missing confirmation: rejected, zero PRs created.
- Confirmed simulated PR: number **1**, exactly **one** record.
- HTTP after PR creation: **503**, demonstrating no implicit recovery/merge.
- Reopening SQLite and repeating approval: identical saved result, no duplicate PR.
- HTTP after explicit local sandbox application: **200**.
- Independently verified investigation status: **resolved**.

Run records are retained under ignored `.local/demo/*/result.json`. The HTTP service
is real loopback; GitHub, OSV, ASI reasoning and PR results are simulated. No result is
evidence of live provider readiness. See `local-demo.md` for reproduction and limitations.

## Repairs made during validation

- Repository-local cache/runtime avoided the inaccessible global uv cache.
- Pytest now creates `.local` before allocating its temporary directory.
- Windows restricted execution blocked asyncio's internal loopback socket pair;
  authorized local socket execution resolved the test-runner stall.
- Official uAgents models use a compatibility serialization wrapper; ACP persistence
  now uses the installed SDK's JSON methods instead of unsupported keyword arguments.
- Missing intake values persist across messages, unsupported reasoning claims are
  discarded, malformed manifests warn, and withdrawn advisories are omitted.
- A later automatic approval review could not execute due to a usage-limit error.
  After the session permissions changed, final validation resumed and passed.
