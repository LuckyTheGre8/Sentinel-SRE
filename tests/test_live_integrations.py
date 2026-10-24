import base64
import gzip
import json
import socket
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from sentinel_ops.acp import ChatGateway, text_message
from sentinel_ops.agents.remediation_executor import RemediationExecutor, action_key
from sentinel_ops.logging import redact
from sentinel_ops.runtime import RuntimeSettings, make_gateway
from sentinel_ops.schemas import (
    CommitAnalysisResponse,
    Dependency,
    HealthCheckResponse,
    InvestigationContext,
    RemediationExecutionRequest,
    RemediationProposal,
    Status,
)
from sentinel_ops.services.asi1_client import ASI1ReasoningClient
from sentinel_ops.services.github_client import LiveGitHubClient
from sentinel_ops.services.github_remediation import GitHubRemediationClient
from sentinel_ops.services.health_client import HttpHealthClient
from sentinel_ops.services.http_api import APIError, request_json
from sentinel_ops.services.osv_client import LiveOSVClient
from sentinel_ops.services.public_transport import PublicHTTPStransport
from sentinel_ops.services.sandbox_github import digest
from sentinel_ops.simulator import make_orchestrator
from sentinel_ops.state import StateStore


@pytest.mark.parametrize("value", ["one two three", "one, two } three", 'one\\" two', "one\ntwo"])
def test_whole_quoted_secret_redacted(value):
    result = redact('password="' + value + '"')
    assert "two" not in result and "one" not in result


async def test_credentials_rejected_before_intake_storage(tmp_path):
    store = StateStore(tmp_path / "state.sqlite")
    gateway = ChatGateway(make_orchestrator(store))
    secret = "synthetic-private-value"
    reply = await gateway.handle(
        "u",
        "s",
        text_message(
            json.dumps(
                {
                    "repository": "demo/checkout",
                    "endpoint": "https://checkout.example/health?token=" + secret,
                }
            )
        ),
    )
    assert secret not in reply[-1].model_dump_json()
    assert store.read("intake_draft", json.dumps(["u", "s"])) is None
    assert not any(secret in row[0] for row in store.db.execute("SELECT data FROM documents"))
    store.close()


async def test_compressed_health_rejected_before_iteration():
    class Body(httpx.AsyncByteStream):
        async def __aiter__(self):
            pytest.fail("Compressed body must not be iterated or decoded")
            yield b""

    def handler(request):
        assert request.headers["accept-encoding"] == "identity"
        return httpx.Response(200, headers={"content-encoding": "gzip"}, stream=Body())

    client = HttpHealthClient(
        allowed_urls={"https://service.example/health"}, transport=httpx.MockTransport(handler)
    )
    assert (await client.probe("https://service.example/health", 1)).failure == "connection"


@pytest.mark.parametrize("kind", ["compressed", "oversized", "redirect", "rate_limit", "malformed"])
async def test_provider_limits_and_safe_errors(kind):
    def handler(request):
        if kind == "compressed":
            return httpx.Response(
                200, content=gzip.compress(b"x" * 2000000), headers={"content-encoding": "gzip"}
            )
        if kind == "oversized":
            return httpx.Response(200, content=b"x" * 10000)
        if kind == "redirect":
            return httpx.Response(302, headers={"location": "http://127.0.0.1/"})
        if kind == "rate_limit":
            return httpx.Response(429, text="synthetic-private-value")
        return httpx.Response(200, text="synthetic-private-value")

    with pytest.raises(APIError) as error:
        await request_json(
            "GET", "https://api.github.com/", transport=httpx.MockTransport(handler), max_bytes=100
        )
    assert "synthetic-private-value" not in str(error.value)


async def test_github_real_response_shapes():
    sha = "a" * 40

    def handler(request):
        path = request.url.path
        if path == "/repos/demo/service":
            data = {"default_branch": "main"}
        elif path.endswith("/commits"):
            data = [
                {
                    "sha": sha,
                    "commit": {
                        "committer": {"date": "2026-10-24T00:00:00Z"},
                        "message": "Change health",
                    },
                    "html_url": "https://github.com/demo/service/commit/" + sha,
                }
            ]
        elif "/commits/" in path:
            data = {"files": [{"filename": "health.py", "patch": "+raise ValueError()"}]}
        elif "/git/trees/" in path:
            data = {
                "truncated": False,
                "tree": [
                    {"type": "blob", "path": "requirements.txt", "size": 20, "mode": "100644"}
                ],
            }
        elif "/contents/" in path:
            data = {
                "encoding": "base64",
                "content": base64.b64encode(b"requests==2.0.0\n").decode(),
            }
        else:
            pytest.fail(path)
        return httpx.Response(200, json=data)

    client = LiveGitHubClient(transport=httpx.MockTransport(handler))
    assert await client.default_branch("demo/service") == "main"
    assert (await client.commits("demo/service", "main", 1))[0].files["health.py"]
    assert (await client.files("demo/service", sha))["requirements.txt"] == "requests==2.0.0\n"


async def test_osv_pagination_keeps_dependency_order_and_hydrates():
    calls = []

    def handler(request):
        if request.method == "POST":
            queries = json.loads(request.content)["queries"]
            calls.append(queries)
            data = (
                {"results": [{"vulns": [{"id": "A"}], "next_page_token": "next"}, {}]}
                if len(calls) == 1
                else {"results": [{"vulns": [{"id": "B"}]}]}
            )
        else:
            data = {"id": request.url.path.rsplit("/", 1)[-1], "affected": []}
        return httpx.Response(200, json=data)

    client = LiveOSVClient(transport=httpx.MockTransport(handler))
    result = await client.query_batch(
        [
            Dependency(ecosystem="PyPI", name="one", version="1", file="requirements.txt"),
            Dependency(ecosystem="PyPI", name="two", version="1", file="requirements.txt"),
        ]
    )
    assert [[v["id"] for v in group] for group in result] == [["A", "B"], []]
    assert len(calls[1]) == 1 and calls[1][0]["page_token"] == "next"


async def test_asi_cannot_infer_confirmation_or_receive_raw_evidence():
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        value = (
            {"action": "confirm"}
            if len(requests) == 1
            else {
                "summary": "No evidence",
                "confidence": "insufficient_evidence",
                "evidence_ids": [],
                "commit_sha": None,
            }
        )
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(value)}}]
            },
        )

    client = ASI1ReasoningClient(
        "synthetic", data_sharing=True, transport=httpx.MockTransport(handler)
    )
    with pytest.raises(ValueError):
        await client.extract("Please do it now")
    await client.synthesize(HealthCheckResponse(), CommitAnalysisResponse())
    payload = json.loads(requests[1]["messages"][1]["content"])
    assert set(payload) == {"health_state", "http_statuses", "candidates", "evidence_ids"}
    await client.extract('{"action":"cancel"}')
    assert len(requests) == 2


@pytest.mark.parametrize(
    "ip,allowed", [("127.0.0.1", False), ("169.254.169.254", False), ("93.184.216.34", True)]
)
async def test_public_transport_pins_dns_and_tls_hostname(monkeypatch, ip, allowed):
    import asyncio

    transport = PublicHTTPStransport()
    captured = []

    async def resolve(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]

    async def send(request):
        captured.append(request)
        return httpx.Response(200)

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolve)
    monkeypatch.setattr(transport.inner, "handle_async_request", send)
    request = httpx.Request("GET", "https://service.example/health")
    try:
        if allowed:
            await transport.handle_async_request(request)
            assert captured[0].url.host == ip
            assert captured[0].headers["host"] == "service.example"
            assert captured[0].extensions["sni_hostname"] == "service.example"
        else:
            with pytest.raises(httpx.ConnectError):
                await transport.handle_async_request(request)
            assert not captured
    finally:
        await transport.aclose()


def test_live_factory_has_no_fixture_fallback_and_requires_private_scope(tmp_path):
    values = {"asi1_api_key": "synthetic", "agent_seed": "synthetic" * 8, "data_sharing": True}
    with pytest.raises(ValidationError):
        RuntimeSettings(**values, github_token="synthetic")
    store = StateStore(tmp_path / "state.sqlite")
    gateway = make_gateway(store, RuntimeSettings(**values))
    assert isinstance(gateway.orchestrator.commits.client, LiveGitHubClient)
    assert isinstance(gateway.orchestrator.security.client, LiveOSVClient)
    assert isinstance(gateway.orchestrator.reasoning, ASI1ReasoningClient)
    assert not gateway.simulated and not gateway.remediation_enabled
    store.close()


async def test_live_pr_requires_confirmation_and_recovers_ambiguous_success(tmp_path, request_data):
    store = StateStore(tmp_path / "state.sqlite")
    context = InvestigationContext(
        **{**request_data.model_dump(), "permission": "create_pr"},
        session_id="owner",
        status=Status.AWAITING,
    )
    store.create(context)
    base, commit = "a" * 40, "c" * 40
    proposal = RemediationProposal(
        investigation_id=context.investigation_id,
        repository=context.repository,
        base_branch="main",
        action="revert_commit",
        commit_sha=base,
        base_sha=base,
        expected_files=["health.py"],
        replacements={"health.py": "healthy"},
        expected_hashes={"health.py": digest("failing")},
        file_modes={"health.py": "100644"},
        evidence=[],
        confidence="medium",
    )
    key = action_key(proposal)
    state = {"branch": False, "pr": None, "writes": 0}

    def handler(request):
        path = request.url.path
        if request.method == "POST":
            state["writes"] += 1
            if path.endswith("/git/trees"):
                data = {"sha": "tree"}
            elif path.endswith("/git/commits"):
                data = {"sha": commit}
            elif path.endswith("/git/refs"):
                state["branch"] = True
                data = {}
            elif path.endswith("/pulls"):
                state["pr"] = {
                    "number": 7,
                    "html_url": "https://github.com/demo/checkout/pull/7",
                    "body": json.loads(request.content)["body"],
                }
                raise httpx.ReadTimeout("synthetic timeout after creation")
            else:
                pytest.fail(path)
        elif path.endswith("/pulls"):
            data = [state["pr"]] if state["pr"] else []
        elif "/git/ref/heads/" in path:
            if path.endswith("/main"):
                data = {"object": {"sha": base}}
            elif state["branch"]:
                data = {"object": {"sha": commit}}
            else:
                return httpx.Response(404)
        elif "/contents/" in path:
            value = "failing" if request.url.params["ref"] == base else "healthy"
            data = {
                "type": "file",
                "encoding": "base64",
                "content": base64.b64encode(value.encode()).decode(),
            }
        elif path.endswith("/git/commits/" + base):
            data = {"tree": {"sha": "old-tree"}}
        elif path.endswith("/git/commits/" + commit):
            data = {"message": "sentinel-action:" + key, "parents": [{"sha": base}]}
        elif "/compare/" in path:
            data = {"files": [{"filename": "health.py"}]}
        else:
            pytest.fail(path)
        return httpx.Response(200, json=data)

    client = GitHubRemediationClient(
        "synthetic", {context.repository}, transport=httpx.MockTransport(handler)
    )
    executor = RemediationExecutor(store, client)
    proposal, nonce, key = executor.save_proposal(proposal, "owner")
    request = RemediationExecutionRequest(
        investigation_id=context.investigation_id,
        proposal_id=proposal.proposal_id,
        session_id="owner",
        confirmation=str(uuid4()),
        idempotency_key=key,
    )
    assert not (await executor.execute(request)).success and state["writes"] == 0
    request.confirmation = nonce
    assert (await executor.execute(request)).error.code == "remote_action_pending"
    assert store.get(context.investigation_id).status == Status.EXECUTING
    result = await executor.execute(request)
    assert result.success and not result.simulated and result.pr_number == 7
    writes = state["writes"]
    assert (await executor.execute(request)) == result and state["writes"] == writes
    assert store.get(context.investigation_id).status == Status.VERIFYING
    store.close()
