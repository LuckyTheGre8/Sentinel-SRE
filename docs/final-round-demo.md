# Sentinel-SRE: 2 minute 40 second final-round demo

## What this demo proves

The guided scenario runs the actual local investigation, evidence ranking, approval gate, sandbox PR executor, and HTTP health probes. It explicitly uses recorded GitHub/OSV evidence and local deterministic reasoning. It does not prove communication between the five deployed agents or a live ASI:One call. Show deployed agents separately and describe the distinction. A successful Agentverse registration alone does not prove end-to-end operation.

## Prepare before the round

1. Use the updated repository on the machine hosting the orchestrator. Preserve its existing seed so its address stays the same. Updating these local files does not update an independently hosted Agentverse deployment.
   Before using the live network path, deploy the same updated source to all five agents and restart them; the remediation response schema now includes its simulation status.
2. Enable the guided route in the orchestrator's environment with `SENTINEL_DEMO_MODE=true`. This is opt-in; ordinary investigation messages still take the live path. If sender restrictions are configured, use an allowed sender.
3. Restart the orchestrator. For the local mailbox-connected setup shown in the supplied logs, run from the repository root:

   ```powershell
   $env:SENTINEL_DEMO_MODE = 'true'
   uv run python -m sentinel_ops.agents.orchestrator_agent serve
   ```

4. Keep `tests/fixtures/github.json` and `tests/fixtures/osv.json` with the deployed code. The host needs writable `.local` storage and loopback socket support. If using Agentverse hosted code rather than this local mailbox setup, first confirm that its runtime supports this project and these files; this workflow has only been tested locally.
5. Open the orchestrator conversation, the five Agentverse agent listings, and a terminal in advance. Rehearse the four commands below in the SAME chat session. Each `demo start` creates a fresh isolated scenario; no deletion or seed reset is needed. Approve promptly because proposals expire.
6. Run the local checks and fallback once before presenting:

   ```powershell
   uv run pytest tests/test_guided_demo.py tests/test_multi_agent.py tests/test_demo.py -q --basetemp=.local/pytest-rehearsal
   uv run python -m sentinel_ops.demo smoke --runs 1
   ```

7. If showing live remote coordination, rehearse it separately with a repository and HTTPS health endpoint you own. Ensure all workers are running and peer addresses match the deployed identities. Never substitute fixture results for a failed live result. Keep secrets and `.env` off screen.

## Exact presentation script and questions

**0:00–0:20 — Problem and product.**

“When a service fails, engineers have to connect health checks, recent changes and security findings before deciding what to do. Sentinel-SRE organizes that work into five specialist agents, with a human approval gate before remediation.”

Show the five agent listings: Orchestrator, Telemetry, Commit, Security, Remediation. Say “These are the five registered agents.” Only say they are actively communicating if a live run has demonstrated it.

**0:20–0:55 — Demonstrate the outage.**

“For a repeatable demonstration, I’m using the labeled sandbox scenario. Its HTTP probes are real; repository evidence and the PR service are fixtures.”

Send to **Sentinel-Orchestrator**, exactly:

```text
demo start
```

Expected: measured HTTP 503, candidate commit and confidence, a prepared revert proposal, and confirmation that a missing approval was rejected with zero PRs. Do not announce these results until they appear.

**0:55–1:20 — Show evidence.**

```text
demo evidence
```

“The diagnosis cites evidence IDs and a ranked commit, and separates correlation from proof. The security finding here is a synthetic fixture, not a newly discovered CVE.”

Expected: recorded report, HTTP status samples, hypothesis references, and `DEMO-2026-001`. Avoid reading the whole JSON aloud.

**1:20–1:50 — Human approval.**

```text
demo approve
```

“I’m approving a sandbox PR. Approval is bound to a saved proposal; repeating it should not create duplicate PRs. Notice that creating the PR has not recovered the service.”

Expected: `sandbox://...` reference, total PR count 1, and measured health still failing. If time allows, repeat `demo approve` to demonstrate the same PR count.

**1:50–2:15 — Apply and independently verify.**

```text
demo recover
```

“This explicitly applies the local sandbox change. A fresh HTTP probe now checks whether the service recovered; the system only reports resolution after the probe succeeds.”

Expected: measured HTTP 200 and healthy state. This is a local configuration change, not an automated production deployment.

**2:15–2:40 — Close.**

“The useful boundary is evidence, then approval, then verification. The live implementation has separate uAgents and an ASI:One reasoning adapter. The next deployment milestone is a rehearsed end-to-end run over the registered agents against an owned service, including a real draft PR.”

If that milestone has actually been verified before presenting, replace the last sentence with the observed result and show its trace or PR.

## Likely judge questions

- **Why five agents?** Separate responsibilities: orchestration, health measurements, commit correlation, security evidence and remediation. The worker protocols let the orchestrator request typed results.
- **Where is Fetch.ai used?** The five standalone services use uAgents and typed message protocols; the orchestrator exposes AgentChatProtocol. Show the registered identities. The guided sandbox executes worker implementations locally.
- **Where is ASI:One used?** The live adapter classifies natural-language intake and synthesizes a candidate from evidence statistics. Explicit JSON selections bypass model inference. This repeatable sandbox uses deterministic reasoning, clearly labeled.
- **Does it change production?** This demo only changes its local sandbox. The live PR path requires configuration and approval; a PR is not a deployment or proof of recovery.
- **What if an external API fails?** Live paths can produce unavailable/insufficient-evidence results. We do not substitute a successful fixture response and call it live.
- **Is the vulnerable package real?** `DEMO-2026-001` is synthetic. Live OSV integration is a separate adapter.
- **Can you guarantee the live demo?** No networked system is failure-proof. The rehearsed local scenario isolates external dependencies and labels that boundary.

## If chat or Agentverse fails during the round

After roughly 15 seconds without a response, say: “The hosted chat transport is delayed. I’ll show the same sandbox lifecycle directly.” Run:

```powershell
uv run python scripts/hackathon_demo.py --fast
```

This initializes agent objects and runs local workers, not remote agent messages. For a compact result with measured 503 → 503 after PR → 200 after application, use:

```powershell
uv run python -m sentinel_ops.demo smoke --runs 1
```

Keep a rehearsal recording available as a last resort and identify it as recorded. Never claim a success that the current output does not show.
