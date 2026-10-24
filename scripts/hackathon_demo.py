"""Fetchathon 3.0 Showcase Demo: Sentinel-Ops Autonomous Multi-Agent SRE.

Run this script during your hackathon presentation or demo recording:
    uv run python scripts/hackathon_demo.py
    uv run python scripts/hackathon_demo.py --interactive
    uv run python scripts/hackathon_demo.py --fast
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

# Setup UTF-8 encoding for Windows console if possible
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Setup color codes
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
BLUE = "\033[94m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def header(text: str, color=CYAN):
    print(f"\n{color}{BOLD}{'=' * 75}{RESET}")
    print(f"{color}{BOLD}  {text}{RESET}")
    print(f"{color}{BOLD}{'=' * 75}{RESET}\n")


def subheader(step: str, title: str):
    print(f"{BLUE}{BOLD}[Step {step}]{RESET} {BOLD}{title}{RESET}")


def pause(interactive: bool, fast: bool = False, msg: str = "Press Enter to proceed..."):
    if interactive:
        input(f"{DIM}{msg}{RESET}")
    elif not fast:
        time.sleep(0.5)


def banner():
    print(f"""{CYAN}{BOLD}
  =========================================================================
   SENTINEL-SRE : Autonomous Multi-Agent Swarm for Incident Remediation
   Fetchathon 3.0 Hackathon Showcase | Powered by Fetch.ai uAgents & ASI:One
  ========================================================================={RESET}
""")


async def run_showcase(interactive: bool = False, fast: bool = False):
    import logging
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.WARNING)

    from sentinel_ops import cards
    from sentinel_ops.acp import text_message
    from sentinel_ops.agents.commit_agent import build_commit_agent
    from sentinel_ops.agents.orchestrator import IncidentReport
    from sentinel_ops.agents.orchestrator_agent import build_orchestrator_agent
    from sentinel_ops.agents.remediation_agent import build_remediation_agent
    from sentinel_ops.agents.remediation_executor import BAD_COMMIT, RemediationExecutor
    from sentinel_ops.agents.security_agent import build_security_agent
    from sentinel_ops.agents.telemetry_agent import build_telemetry_agent
    from sentinel_ops.demo_service import running_service
    from sentinel_ops.remediation_chat import RemediationChatGateway
    from sentinel_ops.schemas import (
        InvestigationRequest,
        RemediationExecutionResponse,
        Status,
        VerificationRequest,
    )
    from sentinel_ops.services.health_client import HttpHealthClient
    from sentinel_ops.services.sandbox_github import SandboxGitHubClient
    from sentinel_ops.simulator import FIXTURES, ROOT, make_orchestrator
    from sentinel_ops.state import StateStore

    banner()
    print("SANDBOX REHEARSAL: real loopback HTTP; recorded GitHub/OSV; local reasoning; simulated PR.")
    print("Agent objects below demonstrate topology; this script does not contact Agentverse peers or ASI:One.")

    # -------------------------------------------------------------
    # Stage 1: Swarm Topology
    # -------------------------------------------------------------
    header("1. MULTI-AGENT SWARM TOPOLOGY (Fetch.ai uAgents)", CYAN)
    runtime_dir = ROOT / ".local" / "demo-hackathon" / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (ROOT / ".local" / "demo-hackathon" / "docs").mkdir(parents=True, exist_ok=True)

    print("  Initializing 5 specialized Fetch.ai autonomous agents:")
    telemetry = build_telemetry_agent(root=ROOT / ".local" / "demo-hackathon", port=8001, mailbox=False)
    commit = build_commit_agent(root=ROOT / ".local" / "demo-hackathon", port=8002, mailbox=False)
    security = build_security_agent(root=ROOT / ".local" / "demo-hackathon", port=8003, mailbox=False)
    remediation = build_remediation_agent(root=ROOT / ".local" / "demo-hackathon", port=8004, mailbox=False)
    orchestrator, _, _ = build_orchestrator_agent(root=ROOT / ".local" / "demo-hackathon", port=8005, mailbox=False)

    agents = [
        ("Sentinel-Telemetry", telemetry.address, "8001", "SentinelHealth", "Monitors probes & verifies recovery"),
        ("Sentinel-Commit", commit.address, "8002", "SentinelCommit", "Ranks suspicious git commits/diffs"),
        ("Sentinel-Security", security.address, "8003", "SentinelSecurity", "Scans dependencies (OSV) & SAST"),
        ("Sentinel-Remediation", remediation.address, "8004", "SentinelRemediation", "Generates safe revert PRs"),
        ("Sentinel-Orchestrator", orchestrator.address, "8005", "AgentChatProtocol", "Coordinates swarm & interacts with SRE"),
    ]

    for name, addr, port, proto, desc in agents:
        print(f"  {GREEN}[✓]{RESET} {BOLD}{name:<23}{RESET} Port: {port:<4} Protocol: {YELLOW}{proto:<18}{RESET}")
        print(f"      {DIM}Address: {addr}{RESET}")
        print(f"      {DIM}Role:    {desc}{RESET}")

    pause(interactive, fast)

    # -------------------------------------------------------------
    # Stage 2: Incident Injection & Detection
    # -------------------------------------------------------------
    header("2. INCIDENT INJECTION & LIVE TELEMETRY PROBES", RED)
    db_path = ROOT / ".local" / "demo-hackathon" / f"state-{uuid4().hex[:8]}.sqlite"
    store = StateStore(db_path)
    client = SandboxGitHubClient(store)
    files = json.loads((FIXTURES / "github.json").read_text())["files"]
    client.initialize(files)

    with running_service(db_path) as live_endpoint:
        print(f"  Target Service: {BOLD}{live_endpoint}{RESET}")
        print(f"  Simulating live production outage on {BOLD}demo/checkout{RESET}...\n")

        health_client = HttpHealthClient(allowed_urls={live_endpoint}, local_demo=True)
        probe_res = await health_client.probe(live_endpoint, 1)
        print(f"  Initial Telemetry Probe: {RED}{BOLD}HTTP {probe_res.status} (OUTAGE OBSERVED){RESET}")
        print(f"  Latency: {probe_res.latency_ms:.1f}ms | Failure Mode: {probe_res.failure or 'None'}")

        pause(interactive, fast)

        # -------------------------------------------------------------
        # Stage 3: Operator Chat Interaction via ACP
        # -------------------------------------------------------------
        header("3. AGENT CHAT PROTOCOL (ACP) - INTAKE & CORRELATION", YELLOW)
        orchestrator_engine = make_orchestrator(store, health_client)
        executor = RemediationExecutor(store, client)
        gateway = RemediationChatGateway(orchestrator_engine, executor)

        session_id = str(uuid4())
        req = InvestigationRequest(
            repository="demo/checkout",
            branch="main",
            endpoint=live_endpoint,
            permission="create_pr",
            incident_at=datetime.now(timezone.utc),
        )

        subheader("3.1", "Operator triggers incident investigation via AgentChatProtocol:")
        print(f"  > User: \"Outage on checkout service at {live_endpoint}\"")
        intake_replies = await gateway.handle("sre-operator", session_id, text_message(req.model_dump_json()))
        print(f"  {GREEN}[<]{RESET} Orchestrator responded with: {CYAN}ACP Intake Review Card{RESET}")
        start_selection = cards.validate_card(intake_replies[-1])["approve_cta"]["selection"]

        pause(interactive, fast)

        # -------------------------------------------------------------
        # Stage 4: Multi-Agent Deep Investigation & Synthesis
        # -------------------------------------------------------------
        header("4. MULTI-AGENT SWARM INVESTIGATION & SYNTHESIS", MAGENTA)
        print("  Running local worker implementations; remote Agentverse peers are not used in this rehearsal.")
        report_replies = await gateway.handle("sre-operator", session_id, text_message(json.dumps(start_selection)))
        cards.validate_card(report_replies[-1])
        report = IncidentReport.model_validate_json(store.read("report", str(req.investigation_id)))

        print(f"\n  {GREEN}[1]{RESET} {BOLD}Telemetry-Watchdog:{RESET}")
        print(f"      Status: {RED}{report.health.state.upper()}{RESET} (HTTP {report.health.probes[0].status})")
        print(f"      Evidence ID: {report.health.evidence[0].id}")

        print(f"\n  {GREEN}[2]{RESET} {BOLD}Commit-Detective:{RESET}")
        top = report.commits.commits[0]
        print(f"      Top Suspect SHA: {YELLOW}{top.sha[:16]}...{RESET} (Rank Score: {top.score:.3f})")
        print(f"      Message: \"{top.message}\"")
        print(f"      Changed Files: {', '.join(top.files.keys())}")

        print(f"\n  {GREEN}[3]{RESET} {BOLD}Security-Investigator:{RESET}")
        for finding in report.security.findings:
            print(f"      Advisory: {RED}{finding.id}{RESET} [{finding.severity.upper()}] in {finding.file}:{finding.line}")

        print(f"\n  {GREEN}[4]{RESET} {BOLD}Local deterministic reasoning (ASI:One simulated):{RESET}")
        print(f"      Summary: {CYAN}{report.hypothesis.summary}{RESET}")
        print(f"      Confidence: {YELLOW}{report.hypothesis.confidence.upper()}{RESET}")
        print(f"      Evidence References: {', '.join(report.hypothesis.evidence_ids)}")

        pause(interactive, fast)

        # -------------------------------------------------------------
        # Stage 5: Confirmation-Bound Safety Boundary
        # -------------------------------------------------------------
        header("5. CONFIRMATION-BOUND SAFETY GATE", RED)
        print("  Sentinel-SRE enforces strict HUMAN-IN-THE-LOOP safety boundaries.")
        print("  No autonomous changes are allowed without explicit cryptographic confirmation.\n")

        confirm_card = await gateway.handle("sre-operator", session_id, text_message(json.dumps({"action": "review_revert"})))
        proposal = cards.validate_card(confirm_card[-1])
        selection = proposal["approve_cta"]["selection"]

        print(f"  Proposed Remediation: {BOLD}Revert commit {top.sha[:8]} on branch main{RESET}")
        print(f"  Confirmation Token:   {DIM}{selection['confirmation']}{RESET}")
        print(f"  Idempotency Key:      {DIM}{selection['idempotency_key'][:24]}...{RESET}\n")

        # Prove unauthorized bypass fails
        print("  [Security Test] Attempting execution WITHOUT human approval:")
        unauthorized = await gateway.handle("sre-operator", session_id, text_message(json.dumps({**selection, "confirmation": ""})))
        unauth_resp = RemediationExecutionResponse.model_validate_json(unauthorized[-1].content[0].text)
        if unauth_resp.success or client.count() != 0:
            raise AssertionError("Confirmation gate failed")
        print(f"  Result: {GREEN}BLOCKED BY POLICY{RESET} (Zero unauthorized mutations created)\n")

        if interactive:
            user_input = input(f"{YELLOW}{BOLD}Type 'CONFIRM' to authorize remediation PR: {RESET}").strip()
            if user_input != "CONFIRM":
                print(f"{RED}Operation cancelled by user.{RESET}")
                return
        else:
            print(f"  [Automated rehearsal]: {BOLD}Script explicitly approves this sandbox PR{RESET}")

        pause(interactive, fast)

        # -------------------------------------------------------------
        # Stage 6: Remediation PR Creation & Recovery
        # -------------------------------------------------------------
        header("6. REMEDIATION EXECUTION & VERIFICATION", GREEN)
        executed = await gateway.handle("sre-operator", session_id, text_message(json.dumps(selection)))
        remed_resp = RemediationExecutionResponse.model_validate_json(executed[-1].content[0].text)
        if not remed_resp.success:
            raise AssertionError("Sandbox PR creation failed")

        print(f"  {GREEN}[✓]{RESET} Pull Request Created: {BOLD}PR #{remed_resp.pr_number}{RESET}")
        print(f"      Reference: {CYAN}{remed_resp.pr_url}{RESET}")
        print(f"      Branch:    revert-{top.sha[:8]}")

        print("\n  Deploying fix & triggering independent recovery verification probe...")
        client.apply_local(selection["idempotency_key"])
        
        final_probe = await gateway.orchestrator.telemetry.run(
            VerificationRequest(investigation_id=req.investigation_id, endpoint=live_endpoint)
        )
        if not final_probe.success or final_probe.state != "healthy":
            raise AssertionError("Recovery not verified")

        print(f"  Independent Verification Probe: {GREEN}{BOLD}HTTP {final_probe.probes[0].status} OK{RESET}")
        print(f"  Service State: {GREEN}{BOLD}{final_probe.state.upper()}{RESET}")
        print(f"  Latency: {final_probe.probes[0].latency_ms:.1f}ms\n")

        store.transition(req.investigation_id, Status.RESOLVED)

    # -------------------------------------------------------------
    # Stage 7: Fetchathon Scorecard
    # -------------------------------------------------------------
    header("7. FETCHATHON 3.0 SCORECARD & COMPLIANCE", CYAN)
    print(f"""
  {GREEN}✓{RESET} {BOLD}Fetch.ai uAgents Framework:{RESET} 5 agent objects initialized; transport not exercised here
  {GREEN}✓{RESET} {BOLD}AgentChatProtocol (ACP):{RESET}    Standardized conversational cards & human-agent interaction
  {GREEN}✓{RESET} {BOLD}Local Reasoning:{RESET}            Deterministic hypothesis from recorded evidence
  {GREEN}✓{RESET} {BOLD}Sandbox Approval:{RESET}          Missing confirmation rejected before sandbox mutation
  {GREEN}✓{RESET} {BOLD}Deterministic Recovery:{RESET}     Full loop from HTTP 503 outage to independently verified HTTP 200
    """)
    header("INCIDENT STATUS: FULLY RESOLVED (HTTP 503 -> 200 OK)", GREEN)


def main():
    parser = argparse.ArgumentParser(description="Fetchathon 3.0 Sentinel-SRE Live Showcase")
    parser.add_argument("--interactive", action="store_true", help="Step through interactively with prompts")
    parser.add_argument("--fast", action="store_true", help="Run without delays for quick testing")
    args = parser.parse_args()

    asyncio.run(run_showcase(interactive=args.interactive, fast=args.fast))


if __name__ == "__main__":
    main()
