"""Tests for 5 independent uAgents architecture, typed protocols, and network dispatch."""

import asyncio
from uuid import uuid4

from sentinel_ops.agents.commit_agent import build_commit_agent
from sentinel_ops.agents.orchestrator import NetworkWorkerTransport
from sentinel_ops.agents.orchestrator_agent import build_orchestrator_agent
from sentinel_ops.agents.remediation_agent import build_remediation_agent
from sentinel_ops.agents.security_agent import build_security_agent
from sentinel_ops.agents.telemetry_agent import build_telemetry_agent
from sentinel_ops.discovery import discover_peer_addresses, load_agent_address, save_agent_address
from sentinel_ops.protocols.commit import (
    CommitAnalysisRequest,
    CommitAnalysisResponse,
    commit_protocol,
)
from sentinel_ops.protocols.health import (
    HealthCheckRequest,
    HealthCheckResponse,
    health_protocol,
)
from sentinel_ops.protocols.orchestration import (
    orchestration_protocol,
)
from sentinel_ops.protocols.remediation import (
    RemediationExecutionRequest,
    RemediationExecutionResponse,
    RemediationProposalRequest,
    RemediationProposalResponse,
    remediation_protocol,
)
from sentinel_ops.protocols.security import (
    SecurityScanRequest,
    SecurityScanResponse,
    security_protocol,
)
from sentinel_ops.schemas import (
    HealthCheckResponse as SchemaHealthCheckResponse,
)


def test_protocol_registrations():
    assert health_protocol.name == "SentinelHealth"
    assert commit_protocol.name == "SentinelCommit"
    assert security_protocol.name == "SentinelSecurity"
    assert remediation_protocol.name == "SentinelRemediation"
    assert orchestration_protocol.name == "SentinelOrchestration"


def test_protocol_message_models():
    inv_id = str(uuid4())

    # Health
    h_req = HealthCheckRequest(investigation_id=inv_id, endpoint="https://service.example/health")
    assert h_req.endpoint == "https://service.example/health"
    h_resp = HealthCheckResponse(investigation_id=inv_id, state="healthy", success=True)
    assert h_resp.state == "healthy"

    # Commit
    c_req = CommitAnalysisRequest(investigation_id=inv_id, repository="demo/checkout")
    assert c_req.repository == "demo/checkout"
    c_resp = CommitAnalysisResponse(investigation_id=inv_id, commits=[{"sha": "a" * 40}])
    assert len(c_resp.commits) == 1

    # Security
    s_req = SecurityScanRequest(investigation_id=inv_id, files={"req.txt": "foo==1.0"})
    assert "req.txt" in s_req.files
    s_resp = SecurityScanResponse(investigation_id=inv_id, findings=[{"id": "CVE-1"}])
    assert len(s_resp.findings) == 1

    # Remediation
    r_prop_req = RemediationProposalRequest(investigation_id=inv_id, action="revert_commit")
    assert r_prop_req.action == "revert_commit"
    r_prop_resp = RemediationProposalResponse(investigation_id=inv_id, nonce="nonce-1", key="key-1")
    assert r_prop_resp.nonce == "nonce-1"

    r_exec_req = RemediationExecutionRequest(
        investigation_id=inv_id,
        proposal_id=str(uuid4()),
        session_id="s1",
        confirmation="c1",
        idempotency_key="k1",
    )
    assert r_exec_req.confirmation == "c1"
    r_exec_resp = RemediationExecutionResponse(investigation_id=inv_id, pr_number=42)
    assert r_exec_resp.pr_number == 42


def test_discovery_save_and_load(tmp_path):
    runtime_dir = tmp_path / "runtime"
    save_agent_address(runtime_dir, "telemetry", "agent1telemetry123")
    save_agent_address(runtime_dir, "commit", "agent1commit456")

    assert load_agent_address(runtime_dir, "telemetry") == "agent1telemetry123"
    assert load_agent_address(runtime_dir, "commit") == "agent1commit456"
    assert load_agent_address(runtime_dir, "security") is None

    peers = discover_peer_addresses(runtime_dir, env={})
    assert peers["telemetry"] == "agent1telemetry123"
    assert peers["commit"] == "agent1commit456"

    # Env override takes precedence
    env_peers = discover_peer_addresses(
        runtime_dir, env={"TELEMETRY_ADDRESS": "agent1telemetryoverride"}
    )
    assert env_peers["telemetry"] == "agent1telemetryoverride"


async def test_network_worker_transport_dispatch_and_cooldown():
    transport = NetworkWorkerTransport(timeout=0.02)

    calls = 0

    async def slow_handler(req):
        nonlocal calls
        calls += 1
        await asyncio.sleep(1)

    inv_id = uuid4()
    req = HealthCheckRequest(investigation_id=str(inv_id), endpoint="https://example.com/health")

    res = await transport.dispatch("health", slow_handler, req, SchemaHealthCheckResponse)
    assert calls == 2
    assert res.error.code == "worker_timeout"

    # In cooldown now
    res_cooldown = await transport.dispatch("health", slow_handler, req, SchemaHealthCheckResponse)
    assert res_cooldown.error.code == "cooldown"


async def test_network_worker_transport_simulated_network_send():
    transport = NetworkWorkerTransport(
        peer_addresses={"health": "agent1targethealth"},
        timeout=1.0,
    )

    async def mock_send(target, msg):
        assert target == "agent1targethealth"
        # Simulate asynchronous worker reply back to transport
        await asyncio.sleep(0.01)
        transport.handle_response(
            "health",
            msg.investigation_id,
            HealthCheckResponse(
                investigation_id=msg.investigation_id,
                state="healthy",
                success=True,
                agent_name="Sentinel-Telemetry",
            ),
        )

    transport.set_sender(mock_send)

    inv_id = uuid4()
    req = HealthCheckRequest(
        investigation_id=str(inv_id), endpoint="https://service.example/health"
    )
    res = await transport.dispatch("health", None, req, SchemaHealthCheckResponse)
    assert res.success is True
    assert res.state == "healthy"
    assert res.investigation_id == inv_id


def test_agent_builders_initialization(tmp_path):
    root = tmp_path
    (root / "docs").mkdir(parents=True)

    telemetry = build_telemetry_agent(root=root, port=8001, mailbox=False)
    assert telemetry.name == "Sentinel-Telemetry"
    assert telemetry.address.startswith("agent1")

    commit = build_commit_agent(root=root, port=8002, mailbox=False)
    assert commit.name == "Sentinel-Commit"
    assert commit.address.startswith("agent1")

    security = build_security_agent(root=root, port=8003, mailbox=False)
    assert security.name == "Sentinel-Security"
    assert security.address.startswith("agent1")

    remediation = build_remediation_agent(root=root, port=8004, mailbox=False)
    assert remediation.name == "Sentinel-Remediation"
    assert remediation.address.startswith("agent1")

    orchestrator, orch_service, _ = build_orchestrator_agent(root=root, port=8005, mailbox=False)
    assert orchestrator.name == "Sentinel-Orchestrator"
    assert orchestrator.address.startswith("agent1")

    peers = discover_peer_addresses(root / ".local" / "runtime")
    assert "telemetry" in peers
    assert "commit" in peers
    assert "security" in peers
    assert "remediation" in peers
    assert "orchestrator" in peers


async def test_network_orchestrator_without_local_workers(tmp_path):
    from sentinel_ops.agents.orchestrator import SentinelOrchestrator
    from sentinel_ops.schemas import InvestigationContext
    from sentinel_ops.services.reasoning import LocalReasoningClient
    from sentinel_ops.state import StateStore

    transport = NetworkWorkerTransport(
        peer_addresses={"telemetry": "health-peer", "commit": "commit-peer"}
    )

    async def send(target, message):
        if target == "health-peer":
            response = HealthCheckResponse(
                investigation_id=message.investigation_id, state="healthy"
            )
            transport.handle_response("health", message.investigation_id, response)
        else:
            response = CommitAnalysisResponse(investigation_id=message.investigation_id)
            transport.handle_response("commits", message.investigation_id, response)

    transport.set_sender(send)
    store = StateStore(tmp_path / "network.sqlite")
    try:
        context = InvestigationContext(
            repository="demo/checkout",
            branch="main",
            session_id="judge",
            endpoint="https://example.com/health",
        )
        store.create(context)
        orchestrator = SentinelOrchestrator(
            store, None, None, None, LocalReasoningClient(), transport
        )
        report = await orchestrator.investigate(context)
        assert report.health.success
        assert report.health.state == "healthy"
        assert report.commits.success
    finally:
        store.close()
