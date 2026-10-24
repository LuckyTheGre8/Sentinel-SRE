# Live uAgent and Agentverse Mailbox

The live entry point uses GitHub REST, OSV, ASI:One chat completions and real public
HTTPS probes. It contains no fixture fallback. The deterministic demo remains a
separate command. Current live operation is read-only: real remediation writes are
not implemented. Do not present the live agent as the full incident-to-PR product.

From the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m sentinel_ops.runtime init
.\.venv\Scripts\python.exe -m sentinel_ops.runtime check
.\.venv\Scripts\python.exe -m sentinel_ops.runtime serve
```

Configure the ignored `.env` file (or environment) with `ASI1_API_KEY` and
`ASI1_DATA_SHARING=true`. The sharing flag permits redacted natural-language intent
and candidate IDs/scores plus HTTP statuses to reach `https://api.asi1.ai`; raw
repository source, commit messages and health response bodies are not sent.
`init` creates an ignored persistent agent identity under `.local/runtime/agent.seed`.
Never paste its contents into a chat or commit it.

Optional settings: `ASI1_MODEL` (default `asi1-mini`), `AGENT_PORT` (default 8001),
`AGENT_MAILBOX` (default true). For direct hosting set `AGENT_MAILBOX=false` and
`AGENT_ENDPOINT` to the publicly reachable HTTPS `/submit` endpoint.

Without a GitHub token, only public repositories can be read. Setting `GITHUB_TOKEN`
also requires comma-separated `SENTINEL_REPOSITORIES` and `SENTINEL_SENDERS` to
prevent other users reading private evidence through the agent. Optional
`SENTINEL_HEALTH_URLS` restricts health probes to exact configured URLs. Otherwise,
intake accepts public HTTPS port 443 only; DNS answers are checked and pinned before
connecting, redirects and compressed responses are refused.

After startup, connect the running agent using the SDK's local Inspector URL and
choose Mailbox. This associates it with your Agentverse account. Verify its ACP
manifest and profile, then test a fresh ASI:One conversation. Starting the process
publishes its protocol manifest and agent description. `check` does not contact
providers or register anything.

State, identity, SDK files and public connection details remain under `.local/runtime`.
Keep the PC awake for the demonstration. Stop with Ctrl+C; restart with the same
identity and database to preserve sessions. To roll back, stop the process and
disconnect the agent from Agentverse; keep the state directory for recovery.

Limits: narrow commit heuristics and manifest parsing, bounded GitHub file scope,
single-process workers, buffered final report, and no real PR creation or merge.
Deployment/ASI discovery is not verified merely by passing local tests.
