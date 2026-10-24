# Sentinel-Ops: Multi-Agent Deployment (5 Independent uAgents)

Sentinel-Ops transforms from a single-process orchestrator into **5 standalone uAgents**, communicating asynchronously over native Fetch.ai `uAgents` protocols and connected independently to the Agentverse Mailbox network.

---

## 1. Architecture Overview

```
                      [ Operator / Chat UI (ACP) ]
                                   │
                                   ▼
                    ┌──────────────────────────────┐
                    │    Sentinel-Orchestrator     │
                    │   Port: 8005 | Mailbox: True │
                    │   Seed: ORCHESTRATOR_SEED    │
                    │   ASI:One Reasoning Engine   │
                    └──────────────┬───────────────┘
                                   │ (uAgents Native Protocols)
       ┌───────────────────────────┼───────────────────────────┐
       ▼                           ▼                           ▼
┌──────────────┐           ┌──────────────┐           ┌──────────────┐
│  Telemetry   │           │    Commit    │           │   Security   │
│  Port: 8001  │           │  Port: 8002  │           │  Port: 8003  │
│Health Probes │           │GitHub Commits│           │OSV & SAST    │
└──────┬───────┘           └──────────────┘           └──────────────┘
       │                           │
       │ (Verification)            │ (Revert Target)
       ▼                           ▼
┌─────────────────────────────────────────────────┐
│              Sentinel-Remediation               │
│          Port: 8004 | Mailbox: True             │
│        Revert Proposals & Confirmed PRs         │
└─────────────────────────────────────────────────┘
```

---

## 2. Agent Roles and Protocols

| Agent | Port | Seed Variable | Primary Role | Protocol Spec | ACP Capability |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Telemetry** | `8001` | `TELEMETRY_SEED` | Health probes & latency checks | `SentinelHealth` (v1.0.0) | `investigate, verify` |
| **Commit** | `8002` | `COMMIT_SEED` | GitHub commit ranking & diffs | `SentinelCommit` (v1.0.0) | `analyze_commits` |
| **Security** | `8003` | `SECURITY_SEED` | OSV scanning & narrow SAST | `SentinelSecurity` (v1.0.0) | `scan_dependencies` |
| **Remediation** | `8004` | `REMEDIATION_SEED` | Draft PR creation & revert proposals | `SentinelRemediation` (v1.0.0) | `propose_revert, confirm` |
| **Orchestrator** | `8005` | `ORCHESTRATOR_SEED`| Coordinates intake, aggregation & ASI:One | `SentinelOrchestration` + ACP | Full workflow intake → report |

---

## 3. Quick Start

### Step 1: Initialize Agent Identities
Run the multi-agent identity initialization script:
```powershell
uv run python scripts/init_all_agents.py
```
This script:
1. Generates 5 unique, cryptographically strong seeds (48 URL-safe chars).
2. Derives deterministic uAgents addresses (`agent1q...`) for each agent.
3. Writes seeds and ports to `.env`.
4. Saves static address discovery records to `.local/runtime/*.address.json`.

### Step 2: Configure Environment (.env)
Add your API keys in `.env`:
```env
ASI1_API_KEY=your_asi1_key_here
ASI1_DATA_SHARING=true
GITHUB_TOKEN=your_github_pat_here
SENTINEL_REPOSITORIES=owner/repository
SENTINEL_HEALTH_URLS=https://your-service.example/health
```

### Step 3: Launch All 5 Agents
Launch all agents in parallel terminals with:
```powershell
powershell -File scripts/start_all_agents.ps1
```
Or launch each independently via uv:
```bash
uv run python -m sentinel_ops.agents.telemetry_agent serve
uv run python -m sentinel_ops.agents.commit_agent serve
uv run python -m sentinel_ops.agents.security_agent serve
uv run python -m sentinel_ops.agents.remediation_agent serve
uv run python -m sentinel_ops.agents.orchestrator_agent serve
```

---

## 4. Agentverse Registration & Mailbox Setup

1. When each agent starts with `mailbox=True`, it prints an **Inspector URL** in the terminal:
   ```
   Inspector URL: https://agentverse.ai/inspect/?agent=agent1q...
   ```
2. Open each Inspector URL in your browser and click **Connect -> Mailbox**.
3. In the [Agentverse Dashboard](https://agentverse.ai/), assign friendly handles:
   - `@sentinel-telemetry`
   - `@sentinel-commit`
   - `@sentinel-security`
   - `@sentinel-remediation`
   - `@sentinel-orchestrator`
4. The agents register on the Fetch.ai Almanac, enabling global network discovery.

---

## 5. Resilient Network Dispatch & Fault Tolerance

- **Timeouts & Deadlines**: Orchestrator queries Telemetry and Commit in parallel using `asyncio.gather` with a 45-second deadline.
- **Bounded Retry with Jitter**: 1 retry with exponential jitter per worker call.
- **Circuit Breaker / Cooldown**: Successive worker timeouts place the peer into temporary cooldown.
- **Graceful Degradation**: If a worker is unreachable or degraded, the Orchestrator does not fail: missing evidence is noted in the investigation warnings, and the final report indicates partial evidence.
- **Address Discovery**: Zero hardcoded addresses. Agents read peer locations from `.local/runtime/{peer}.address.json` or environment variables (`TELEMETRY_ADDRESS`, etc.).
