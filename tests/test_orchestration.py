import asyncio
import json
from uuid import uuid4

import httpx
from uagents_core.contrib.protocols.chat import ChatAcknowledgement, ChatMessage, EndSessionContent

from sentinel_ops.acp import ChatGateway, build_protocol, text_message
from sentinel_ops.agents.orchestrator import LocalWorkerTransport
from sentinel_ops.cards import validate_card
from sentinel_ops.schemas import HealthCheckResponse, InvestigationContext, Status
from sentinel_ops.services.health_client import HttpHealthClient
from sentinel_ops.simulator import make_orchestrator
from sentinel_ops.state import StateStore


async def test_conversation_ack_intake_and_report(tmp_path, request_data):
    store = StateStore(tmp_path / "state.db")
    gateway = ChatGateway(make_orchestrator(store))
    assert build_protocol(gateway).name == "AgentChatProtocol"
    message = text_message("Investigate an outage")
    replies = await gateway.handle("user", "session", message)
    assert isinstance(replies[0], ChatAcknowledgement)
    assert replies[0].acknowledged_msg_id == message.msg_id
    assert {f["name"] for f in validate_card(replies[-1])["fields"]} == {"repository", "endpoint"}
    intake = await gateway.handle("user", "session", text_message(request_data.model_dump_json()))
    selection = validate_card(intake[-1])["approve_cta"]["selection"]
    message = text_message(json.dumps(selection))
    replies = await gateway.handle("user", "session", message)
    assert "bbbbbbbb" in str(validate_card(replies[-1]))
    replay = await gateway.handle("user", "session", message)
    assert replay[-1] == replies[-1]
    assert store.get(request_data.investigation_id).status == Status.AWAITING
    store.close()


async def test_unsupported_input(tmp_path):
    store = StateStore(tmp_path / "state.db")
    gateway = ChatGateway(make_orchestrator(store))
    replies = await gateway.handle(
        "u", "s", ChatMessage(content=[EndSessionContent(type="end-session")])
    )
    assert "unsupported_input" in replies[-1].content[0].text
    store.close()


async def test_partial_failure_and_correlation(tmp_path, request_data):
    store = StateStore(tmp_path / "state.db")
    orchestrator = make_orchestrator(store)

    async def wrong(request):
        return HealthCheckResponse(investigation_id=uuid4())

    orchestrator.telemetry.run = wrong
    ctx = InvestigationContext(**request_data.model_dump(), session_id="u")
    store.create(ctx)
    report = await orchestrator.investigate(ctx)
    assert not report.health.success and report.commits.success
    assert report.health.error.code == "invalid_worker_response"
    assert report.hypothesis.confidence == "insufficient_evidence"
    assert report.security.findings
    store.close()


async def test_contradictory_evidence(tmp_path, request_data):
    store = StateStore(tmp_path / "state.db")
    health = HttpHealthClient(
        allowed_urls={request_data.endpoint},
        transport=httpx.MockTransport(lambda r: httpx.Response(200)),
    )
    orchestrator = make_orchestrator(store, health)
    ctx = InvestigationContext(**request_data.model_dump(), session_id="u")
    store.create(ctx)
    report = await orchestrator.investigate(ctx)
    assert any("Conflicting" in w for w in report.warnings)
    store.close()


async def test_bounded_retry_and_cooldown(request_data):
    calls = 0

    async def slow(req):
        nonlocal calls
        calls += 1
        await asyncio.sleep(10)

    transport = LocalWorkerTransport(timeout=0.01)
    result = await transport.dispatch("health", slow, request_data, HealthCheckResponse)
    assert calls == 2 and result.error.code == "worker_timeout"
    result = await transport.dispatch("health", slow, request_data, HealthCheckResponse)
    assert calls == 2 and result.error.code == "cooldown"


async def test_missing_intake_fields_merge_in_same_session(tmp_path):
    store = StateStore(tmp_path / "state.db")
    gateway = ChatGateway(make_orchestrator(store))
    first = await gateway.handle("u", "s", text_message('{"repository":"demo/checkout"}'))
    assert [f["name"] for f in validate_card(first[-1])["fields"]] == ["endpoint"]
    second = await gateway.handle(
        "u", "s", text_message('{"endpoint":"https://checkout.example/health"}')
    )
    assert validate_card(second[-1])["approve_cta"]["selection"]["action"] == "start"
    store.close()


async def test_reasoning_cannot_invent_facts(tmp_path, request_data):
    from sentinel_ops.schemas import IncidentHypothesis

    store = StateStore(tmp_path / "state.db")
    orchestrator = make_orchestrator(store)

    async def fabricated(health, commits):
        return IncidentHypothesis(
            summary="Database destroyed and credentials stolen",
            confidence="high",
            evidence_ids=["health:0"],
            commit_sha=commits.commits[0].sha,
        )

    orchestrator.reasoning.synthesize = fabricated
    context = InvestigationContext(**request_data.model_dump(), session_id="u")
    store.create(context)
    result = await orchestrator.investigate(context)
    assert "stolen" not in result.hypothesis.summary and result.hypothesis.confidence == "medium"
    store.close()


async def test_reasoning_failure_preserves_report(tmp_path, request_data):
    store = StateStore(tmp_path / "state.db")
    orchestrator = make_orchestrator(store)

    async def failed(*args):
        raise TimeoutError()

    orchestrator.reasoning.synthesize = failed
    context = InvestigationContext(**request_data.model_dump(), session_id="u")
    store.create(context)
    result = await orchestrator.investigate(context)
    assert result.commits.commits and result.security.findings
    assert any("Reasoning unavailable" in w for w in result.warnings)
    store.close()
