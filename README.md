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
