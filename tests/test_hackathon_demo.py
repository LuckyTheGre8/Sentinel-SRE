"""Fetchathon 3.0 Hackathon Demonstration Test for Sentinel-Ops Multi-Agent SRE.

Runs a complete, self-contained, automated end-to-end multi-agent incident
investigation, confirmation-gated remediation, and independent recovery verification.
Designed for judges to verify in Fetchathon 3.0:
    uv run pytest tests/test_hackathon_demo.py -v -s
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

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
from sentinel_ops.discovery import discover_peer_addresses
from sentinel_ops.protocols.commit import commit_protocol
from sentinel_ops.protocols.health import health_protocol
from sentinel_ops.protocols.orchestration import orchestration_protocol
from sentinel_ops.protocols.remediation import remediation_protocol
from sentinel_ops.protocols.security import security_protocol
from sentinel_ops.remediation_chat import RemediationChatGateway
from sentinel_ops.schemas import (
    InvestigationRequest,
    RemediationExecutionResponse,
    Status,
    VerificationRequest,
)
from sentinel_ops.services.health_client import HttpHealthClient
from sentinel_ops.services.sandbox_github import SandboxGitHubClient
from sentinel_ops.simulator import FIXTURES, make_orchestrator
from sentinel_ops.state import StateStore


def test_hackathon_agent_swarm_topology(tmp_path):
    """Test 1: Verify the 5 Fetch.ai uAgents swarm topology and protocol registration."""
    print("\n" + "=" * 70)
    print("FETCHATHON 3.0: STAGE 1 - MULTI-AGENT SWARM TOPOLOGY")
    print("=" * 70)

    # Protocols
    protocols = [
        health_protocol,
        commit_protocol,
        security_protocol,
        remediation_protocol,
        orchestration_protocol,
    ]
    for p in protocols:
        print(f"  [+] Protocol verified: {p.name:<25} Version: {p.version}")
        assert p.name.startswith("Sentinel")

    # Build all 5 standalone Fetch.ai uAgents
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True)
    (tmp_path / "docs").mkdir(parents=True)

    telemetry = build_telemetry_agent(root=tmp_path, port=8001, mailbox=False)
    commit = build_commit_agent(root=tmp_path, port=8002, mailbox=False)
    security = build_security_agent(root=tmp_path, port=8003, mailbox=False)
    remediation = build_remediation_agent(root=tmp_path, port=8004, mailbox=False)
    orchestrator, _, _ = build_orchestrator_agent(root=tmp_path, port=8005, mailbox=False)

    agents = [
        ("Sentinel-Telemetry", telemetry.address, 8001, "Health probes & recovery verification"),
        ("Sentinel-Commit", commit.address, 8002, "GitHub diff analysis & ranking"),
        ("Sentinel-Security", security.address, 8003, "OSV vulnerability & SAST scanning"),
        ("Sentinel-Remediation", remediation.address, 8004, "Revert proposals & sandbox PRs"),
        ("Sentinel-Orchestrator", orchestrator.address, 8005, "Swarm coordination & ACP chat"),
    ]

    print("\n  Swarm Agent Registry (Fetch.ai uAgents Addresses):")
    for name, addr, port, role in agents:
        print(f"   * {name:<22} Port: {port} | Addr: {addr[:16]}... | Role: {role}")
        assert addr.startswith("agent1")

    peers = discover_peer_addresses(tmp_path / ".local" / "runtime")
    assert len(peers) >= 5
    print("\n  [PASS] All 5 Fetch.ai uAgents initialized and mutually discoverable.")


@pytest.mark.asyncio
async def test_hackathon_full_incident_lifecycle(tmp_path):
    """Test 2: Complete Autonomous SRE Incident Lifecycle with Real Loopback HTTP & Sandbox PR."""
    print("\n" + "=" * 70)
    print("FETCHATHON 3.0: STAGE 2 - AUTONOMOUS SRE INCIDENT RESOLUTION")
    print("=" * 70)

    # 1. Initialize SQLite State Machine & GitHub Sandbox
    db_path = tmp_path / "investigations.sqlite"
    store = StateStore(db_path)
    client = SandboxGitHubClient(store)
    files = json.loads((FIXTURES / "github.json").read_text())["files"]
    client.initialize(files)

    with running_service(db_path) as live_endpoint:
        print(f"  [1] Live Service Target: {live_endpoint} (Starts in FAILING state)")

        health_client = HttpHealthClient(allowed_urls={live_endpoint}, local_demo=True)
        orchestrator = make_orchestrator(store, health_client)
        executor = RemediationExecutor(store, client)
        gateway = RemediationChatGateway(orchestrator, executor)

        session = str(uuid4())
        req = InvestigationRequest(
            repository="demo/checkout",
            branch="main",
            endpoint=live_endpoint,
            permission="create_pr",
            incident_at=datetime(2026, 10, 24, 4, tzinfo=timezone.utc),
        )

        # Step 1: ACP Intake
        print("\n  [2] Operator Initiates ACP Investigation:")
        intake_replies = await gateway.handle("fetchathon-judge", session, text_message(req.model_dump_json()))
        assert len(intake_replies) == 2
        start_selection = cards.validate_card(intake_replies[-1])["approve_cta"]["selection"]
        print("      * AgentChatProtocol Intake Card validated.")

        # Step 2: Multi-Agent Swarm Investigation
        print("\n  [3] Multi-Agent Swarm Deep Analysis:")
        report_replies = await gateway.handle("fetchathon-judge", session, text_message(json.dumps(start_selection)))
        cards.validate_card(report_replies[-1])
        report = IncidentReport.model_validate_json(store.read("report", str(req.investigation_id)))

        # Telemetry verification
        print(f"      * [Sentinel-Telemetry]: Probes observed HTTP status {report.health.probes[0].status} (State: {report.health.state})")
        assert report.health.state == "failing"
        assert report.health.probes[0].status == 503

        # Commit detective verification
        top_commit = report.commits.commits[0]
        print(f"      * [Sentinel-Commit]: Top candidate commit: {top_commit.sha[:12]}... (Score: {top_commit.score})")
        assert top_commit.sha == BAD_COMMIT

        # Security investigator verification
        finding_ids = {f.id for f in report.security.findings}
        print(f"      * [Sentinel-Security]: Findings identified: {len(finding_ids)} (including synthetic advisory DEMO-2026-001)")
        assert "DEMO-2026-001" in finding_ids

        # Reasoning synthesis
        print(f"      * [ASI:One Reasoning]: Hypothesis summary: '{report.hypothesis.summary[:60]}...'")
        print(f"      * [State Machine]: Transitioned to {store.get(req.investigation_id).status}")
        assert store.get(req.investigation_id).status == Status.AWAITING

        # Step 3: Safety & Confirmation Boundary
        print("\n  [4] Safety Boundary Verification (Confirmation-Bound Remediation):")
        confirm_card = await gateway.handle("fetchathon-judge", session, text_message(json.dumps({"action": "review_revert"})))
        proposal_payload = cards.validate_card(confirm_card[-1])
        selection = proposal_payload["approve_cta"]["selection"]

        # Attempt execution WITHOUT human confirmation: MUST BE REJECTED
        unconfirmed = await gateway.handle("fetchathon-judge", session, text_message(json.dumps({**selection, "confirmation": ""})))
        rejected_resp = RemediationExecutionResponse.model_validate_json(unconfirmed[-1].content[0].text)
        print("      * Unconfirmed remediation attempt blocked by policy: SUCCESS (Safety Gate Passed)")
        assert not rejected_resp.success
        assert client.count() == 0

        # Step 4: Confirmed Remediation
        print("\n  [5] Operator Authorizes Revert (CONFIRM):")
        executed = await gateway.handle("fetchathon-judge", session, text_message(json.dumps(selection)))
        remed_resp = RemediationExecutionResponse.model_validate_json(executed[-1].content[0].text)
        print(f"      * [Sentinel-Remediation]: Generated Sandbox PR #{remed_resp.pr_number} ({remed_resp.pr_url})")
        assert remed_resp.success
        assert remed_resp.pr_number == 1

        # Service still failing before merge/deploy
        mid_probe = await gateway.orchestrator.telemetry.run(
            VerificationRequest(investigation_id=req.investigation_id, endpoint=live_endpoint)
        )
        assert mid_probe.state == "failing"
        print("      * Live service confirmed still 503 (PR creation did not magically mutate runtime)")

        # Step 5: Merge PR / Deploy Fix & Verify Recovery
        print("\n  [6] Deploy Fix & Independent Verification Probe:")
        client.apply_local(selection["idempotency_key"])
        final_probe = await gateway.orchestrator.telemetry.run(
            VerificationRequest(investigation_id=req.investigation_id, endpoint=live_endpoint)
        )
        print(f"      * Verification Probe: HTTP Status {final_probe.probes[0].status} (State: {final_probe.state})")
        assert final_probe.state == "healthy"
        assert final_probe.probes[0].status == 200

        # Resolution Card
        store.transition(req.investigation_id, Status.RESOLVED)
        res_card = cards.resolution(remed_resp, report.health, final_probe, Status.RESOLVED.value)
        cards.validate_card(res_card)

        print("\n" + "=" * 70)
        print("FETCHATHON 3.0 DEMO RESULT: INCIDENT FULLY RESOLVED (HTTP 503 -> 200 OK)")
        print("=" * 70)
