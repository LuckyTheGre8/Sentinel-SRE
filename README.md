# Sentinel-Ops

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

Incident evidence, confirmed sandbox remediation, and independent recovery verification.
This build is local-only. External GitHub, ASI:One and Agentverse actions are disabled.
The supplied specification and prompt pack are references; the user's local-only scope
overrides their deployment, publication and per-phase approval instructions.

## Setup (PowerShell)

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
$env:UV_PYTHON_INSTALL_DIR="$PWD\.python"
$env:UV_PYTHON_BIN_DIR="$PWD\.python\bin"
uv python install 3.11.17
uv sync --frozen
uv run --frozen pytest --basetemp=.local/pytest
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen mypy src/sentinel_ops
uv run --frozen python scripts/check_secrets.py
git diff --check
```

No credentials are needed. `.env.example` contains blank names for future integration;
the local build does not load or use external credentials. Payments and automatic
merging are rejected by configuration. State and caches belong in ignored directories.

## Foundation

Typed contracts enforce correlation IDs, UTC timestamps and structured failures.
SQLite persists investigation states and rejects invalid transitions. Redacting log
formatters sanitize messages and tracebacks. Tests cover all state transition pairs.

## Evidence workers

Telemetry bounds response size and time, refuses redirects, and distinguishes HTTP,
DNS, TLS, timeout and connection failure. Real HTTP is permitted only for exact
allowlisted numeric loopback URLs in explicit demo mode; public-host probes require
a recorded transport. This deliberately prevents DNS rebinding in the local build.
Commit ranking uses time, changed service paths and breaking diff signals, never
author identity. Scores describe correlation, not proof.

Security supports exact requirements/PEP 621 pins, npm package-lock versions,
exact package.json versions, simple Go modules and Maven versions. Dockerfiles get
a digest-pin check. Unresolved ranges and unsupported lockfiles produce warnings.
Narrow Python AST checks cover credential literals, interpolated execute calls,
shell=True, verify=False and wildcard CORS. Risk is max(severity weight × confidence),
with critical/high/medium/low/info weights 10/8/5/2/0; it never affects incident ranking.
The fictional demo-vulnerable package is fixture data and is never installed.

Official interface references checked during implementation:
- [GitHub commits](https://docs.github.com/en/rest/commits/commits)
- [OSV batch IDs](https://github.com/google/osv.dev/blob/master/docs/api/post-v1-querybatch.md)
- [OSV full records](https://github.com/google/osv.dev/blob/master/docs/api/get-v1-vulns.md)

Fixtures are synthetic API-shaped records, not captured live success. Missing OSV
coverage returns incomplete analysis. An unknown fixed version stays unknown.
On restricted Windows hosts, asyncio may require permission to open its internal
loopback socket pair even when all service calls are mocked.

## Local ACP conversation

Run `uv run --frozen python -m sentinel_ops.simulator` for a recorded read-only
conversation. Official ACP 0.3.0 models provide acknowledgements and card envelopes;
the local transport serializes every worker message and checks investigation IDs.
The deterministic reasoning adapter implements the same extraction/synthesis boundary
intended for ASI:One, but makes no LLM calls. Worker calls have deadlines, one transient
retry with jitter, and a cooldown. Reports retain partial findings and flag conflicting
health/commit evidence. Duplicate chat messages reuse persisted replies.

Cards use the documented v1 `form`, `detail` and `review` schemas with JSON-stringified
metadata. No protocol is attached to a running network agent or published.
- [ACP reference](https://innovationlab.fetch.ai/resources/docs/agent-communication/agent-chat-protocol)
- [Cards reference](https://innovationlab.fetch.ai/resources/docs/interactive-cards/asi-interactive-cards)

## Safe sandbox remediation

Proposals persist an exact approved file set, baseline hashes, replacements, evidence,
session identity, ten-minute approval expiry and a stable action key. Confirmation
must match all saved fields. Replayed confirmation returns the same durable simulated
PR, including after restarting the process. Superseded or expired proposals fail closed.
Revert uses the known fixture's inverse; patch mode uses bounded full-file replacements,
not arbitrary commands or untrusted unified patches. Traversal, Windows special paths,
case collisions, oversized content, changed baselines and extra files are rejected.

The sandbox stores files and PR records atomically in SQLite. `sandbox://` PR references
are local simulation identifiers, not web URLs. PR creation leaves service state unchanged.
The separate explicit local-demo apply hook changes only the sandbox snapshot. It is
not a Git merge and never writes a real repository branch. Health verification follows
as an independent operation. No backend is provided for live GitHub writes.
