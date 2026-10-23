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
