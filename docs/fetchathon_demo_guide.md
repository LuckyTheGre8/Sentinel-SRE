# Fetchathon 3.0 Demo & Presentation Guide

> Use [the verified final-round runbook](final-round-demo.md) for the presentation.
> This older outline contains unverified claims. In particular, the terminal showcase
> runs local workers and recorded fixtures; it does not prove remote collaboration,
> live ASI:One reasoning, production safety, or a guaranteed test pass.

## Sentinel-SRE: Autonomous Multi-Agent Site Reliability Engineering Swarm

> **Tagline:** Incident diagnosis, evidence synthesis, confirmation-bound remediation, and independent recovery verification powered by Fetch.ai uAgents and ASI:One.

---

## 🚀 Quick Demo Commands for Judges & Hackathon Presentation

### 1. Automated Judge Verification (100% Pass in ~6s)
Run the dedicated hackathon pytest suite with live stdout enabled:
```powershell
uv run pytest tests/test_hackathon_demo.py -v -s
```
* **Stage 1:** Verifies the 5 Fetch.ai uAgents swarm topology, address derivation (`agent1q...`), and custom protocols.
* **Stage 2:** Runs an automated end-to-end incident lifecycle from real loopback HTTP 503 outage to independently verified HTTP 200 OK.

---

### 2. Live Visual Showcase (for Screen Recording & Video Pitch)
Run the rich terminal presentation script:
```powershell
# Automated showcase (ideal for timed recordings and quick demos)
uv run python scripts/hackathon_demo.py

# Interactive showcase (pauses at each stage so you can explain to judges)
uv run python scripts/hackathon_demo.py --interactive
```

---

## 🏛️ Swarm Architecture (5 Standalone Fetch.ai uAgents)

```
                       [ Human SRE / Chat UI ]
                                  │
                                  │ AgentChatProtocol (ACP)
                                  ▼
                   ┌──────────────────────────────┐
                   │    Sentinel-Orchestrator     │
                   │   Port: 8005 | Mailbox: True │
                   │   ASI:One Reasoning Engine   │
                   └──────────────┬───────────────┘
                                  │ (Native uAgents Protocols)
       ┌──────────────────────────┼──────────────────────────┐
       ▼                          ▼                          ▼
┌──────────────┐          ┌──────────────┐           ┌──────────────┐
│  Telemetry   │          │    Commit    │           │   Security   │
│  Port: 8001  │          │  Port: 8002  │           │  Port: 8003  │
│SentinelHealth│          │SentinelCommit│           │SentinelSecur │
└──────┬───────┘          └──────────────┘           └──────────────┘
       │                          │
       │ (Verification Probe)     │ (Revert Target)
       ▼                          ▼
┌────────────────────────────────────────────────┐
│              Sentinel-Remediation              │
│          Port: 8004 | Mailbox: True            │
│       Protocol: SentinelRemediation            │
└────────────────────────────────────────────────┘
```

| Agent | Port | Native Protocol | Role |
| :--- | :--- | :--- | :--- |
| **Sentinel-Telemetry** | `8001` | `SentinelHealth` | High-frequency probes, latency tracking, failure mode detection, recovery verification. |
| **Sentinel-Commit** | `8002` | `SentinelCommit` | Git commit ranking, diff parsing, path-to-service correlation scoring. |
| **Sentinel-Security** | `8003` | `SentinelSecurity` | OSV vulnerability database querying & static AST checks (unpinned deps, disabled TLS, etc.). |
| **Sentinel-Remediation** | `8004` | `SentinelRemediation` | Draft PR creation, patch/revert proposals, idempotency key enforcement. |
| **Sentinel-Orchestrator** | `8005` | `SentinelOrchestration` + `AgentChatProtocol` | Swarm coordination, parallel worker dispatch, ASI:One synthesis, and human-in-the-loop chat. |

---

## 🎯 2-Minute Pitch Script for Fetchathon 3.0 Judges

1. **The Problem:**
   > *"When a critical service goes down at 3 AM, human SREs spend 30-45 minutes triaging telemetry, sifting through hundreds of git diffs, cross-referencing CVE databases, and manually proposing fixes. Meanwhile, every second of downtime costs businesses thousands of dollars."*

2. **The Solution (Sentinel-SRE):**
   > *"Sentinel-SRE replaces fragmented manual triage with an autonomous multi-agent swarm built on Fetch.ai uAgents. When an outage occurs, Sentinel deploys 5 specialized agents that collaborate asynchronously over native Fetch.ai protocols to triage, diagnose, and remediate the incident in seconds."*

3. **Key Differentiator 1 — Fetch.ai Native Swarm Collaboration:**
   > *"Telemetry-Watchdog probes the live endpoint and flags a 503 outage. Commit-Detective concurrently ranks recent git diffs and identifies the exact breaking commit. Security-Investigator flags an associated vulnerability via OSV. Orchestrator unifies this evidence using ASI:One reasoning."*

4. **Key Differentiator 2 — Confirmation-Bound Remediation (Safety First):**
   > *"Autonomous SRE cannot be reckless. Sentinel-SRE implements Confirmation-Bound Remediation. The agent generates a cryptographically signed revert proposal with an idempotency key. It will NEVER mutate production or merge PRs without human approval."*

5. **Key Differentiator 3 — Independent Post-Remediation Verification:**
   > *"Unlike naive AI assistants that hallucinate success, Sentinel-SRE independently re-probes the endpoint using Telemetry-Watchdog. It confirms the service transitioned from HTTP 503 back to HTTP 200 before marking the incident as resolved."*

---

## 🏆 Fetchathon 3.0 Judging Criteria Alignment

| Hackathon Criterion | Sentinel-SRE Implementation |
| :--- | :--- |
| **Multi-Agent Architecture** | 5 independent uAgents communicating over typed `uAgents` protocols with address discovery. |
| **AgentChatProtocol (ACP)** | Structured conversational cards (Intake, Investigation Report, Confirmation, Resolution) following ACP v0.3.0 specs. |
| **ASI:One Integration** | Privacy-preserving reasoning client with explicit data-sharing boundaries (never leaks credentials or raw source). |
| **Decentralized Readiness** | Almanac address registration, Agentverse Mailbox client support, and peer address discovery. |
| **Safety & Production Readiness** | SQLite transaction state machine, circuit-breaker cooldowns, bounded retries with jitter, and confirmation gates. |
