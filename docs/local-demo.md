# Run and reset the local demo

Run from the repository root in PowerShell. No accounts or credentials are needed.

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
$env:UV_PYTHON_INSTALL_DIR="$PWD\.python"
$env:UV_PYTHON_BIN_DIR="$PWD\.python\bin"
uv python install 3.11.17
uv sync --frozen
uv run --frozen python -m sentinel_ops.demo smoke --runs 2
```

Alternatively `uv run --frozen python scripts/smoke_test.py` runs the same two-run
workflow. Each run creates `.local/demo/<run-id>/state.sqlite`, starts real HTTP on a
random numeric loopback port, and stops it on completion or failure. `result.json`
records health codes, investigation ID, ranking, finding, confirmation rejection,
PR count and replay result. The smoke harness explicitly simulates user approval.

Each run asserts:

1. Initial HTTP 503.
2. Synthetic bad change `bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb` ranked first.
3. Synthetic advisory `DEMO-2026-001` detected.
4. Missing confirmation rejected without creating a PR.
5. One confirmed simulated PR created, with health still 503.
6. Reopened SQLite and repeated approval return the same PR.
7. Explicit local snapshot application restores HTTP 200.
8. Independent probes permit a resolved result.

## Interactive approval

Initialize and serve in one terminal:

```powershell
uv run --frozen python -m sentinel_ops.demo init
uv run --frozen python -m sentinel_ops.demo serve --port 8765
```

In a second terminal, configure the same cache variables and run:

```powershell
uv run --frozen python -m sentinel_ops.demo chat --port 8765
```

Type `CONFIRM` at the summary to create the simulated PR and apply the local recovery.
Any other answer cancels. Stop the service with Ctrl+C. To reset, stop the service,
run `init` again and restart `serve`. Reset creates a fresh snapshot and updates
`.local/demo-current.json`; prior runs are retained. No user work is deleted.

The standalone `python -m sentinel_ops.simulator` command demonstrates read-only ACP
conversation using recorded HTTP instead of a real local service.

## Checks

```powershell
uv run --frozen pytest -q --basetemp=.local/pytest
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen mypy src/sentinel_ops
uv run --frozen python scripts/check_secrets.py
git diff --check
```

Pytest creates `.local` before allocating temporary files. Restricted Windows runners
may require loopback permission for asyncio's own internal socket pair, even with
recorded transports. No test needs an external API connection. The pattern-based
secret scan complements manual diff inspection; it is not a comprehensive audit.

## Known limitations

- GitHub, OSV, ASI:One reasoning and PR results are local/synthetic. Live APIs,
  registration, discovery, publication and actual card rendering remain unverified.
- `sandbox://` references identify local records, not browser links.
- Revert is the known inverse of the synthetic scenario, not a general Git revert.
  Patch mode uses exact full-file replacements, not arbitrary patch programs.
- Only exact allowlisted numeric loopback targets receive real HTTP. Public/private
  remote targets and redirects are disabled, preventing DNS rebinding in this build.
- SAST covers narrow Python AST/Dockerfile patterns. Manifest parsing covers bounded
  subsets; unsupported ranges/locks and malformed input warn. CVSS vectors are not
  converted into calibrated severity scores. This is not a complete security scanner.
- Correlation is not proof. A healthy endpoint does not establish repository security.
- Progress is buffered, and agent messages are serialized in-process. No live LLM or
  cross-process agent communication is tested. Interrupted read-only collection should
  be restarted as a new investigation; confirmed actions persist across restarts.
- Payments, automatic merging, deployment and external writes are unavailable.
