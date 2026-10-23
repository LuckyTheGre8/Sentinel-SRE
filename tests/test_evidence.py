import json
import socket
import ssl
from pathlib import Path

import httpx
import pytest

from sentinel_ops.agents.commit_detective import CommitDetective
from sentinel_ops.agents.security_investigator import SecurityInvestigator
from sentinel_ops.agents.telemetry_watchdog import TelemetryWatchdog
from sentinel_ops.schemas import CommitAnalysisRequest, HealthCheckRequest, SecurityScanRequest
from sentinel_ops.services.github_client import RecordedGitHubClient
from sentinel_ops.services.health_client import HttpHealthClient, classify_exception, validate_url
from sentinel_ops.services.osv_client import RecordedOSVClient
from sentinel_ops.services.security import code_findings, dependencies

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://169.254.169.254/",
        "http://10.0.0.1/",
        "http://[::1]/",
        "http://localhost/",
        "https://" + "user" + ":" + "pass" + "@example.com/",
        "http://metadata.google.internal/",
        "http://127.0.0.1/",
        "http://2130706433/",
    ],
)
def test_unsafe_urls(url):
    with pytest.raises(ValueError):
        validate_url(url)


def test_no_external_connection_even_in_demo():
    with pytest.raises(ValueError):
        HttpHealthClient(allowed_urls={"https://8.8.8.8/"}, local_demo=True)


@pytest.mark.parametrize(
    "exc,expected",
    [
        (socket.gaierror(), "dns"),
        (ssl.SSLError(), "tls"),
        (httpx.ReadTimeout("x"), "timeout"),
        (ConnectionRefusedError(), "connection"),
    ],
)
def test_transport_failure_classes(exc, expected):
    wrapper = httpx.ConnectError("sanitized")
    wrapper.__cause__ = exc
    assert classify_exception(wrapper) == expected


@pytest.mark.parametrize(
    "codes,state",
    [
        ([200, 200], "healthy"),
        ([200, 503], "degraded"),
        ([503, 503], "failing"),
        ([302, 302], "failing"),
    ],
)
async def test_health_states_bounds_and_no_redirect(codes, state):
    calls = []

    def handler(req):
        calls.append(str(req.url))
        return httpx.Response(
            codes[len(calls) - 1],
            headers={"location": "http://169.254.169.254/"},
            text="token=synthetic-value " + "x" * 10000,
        )

    client = HttpHealthClient(
        allowed_urls={"https://demo.example/health"}, transport=httpx.MockTransport(handler)
    )
    response = await TelemetryWatchdog(client).run(
        HealthCheckRequest(endpoint="https://demo.example/health")
    )
    assert response.state == state
    assert len(calls) == 2
    assert all(len(p.excerpt) <= 4096 for p in response.probes)
    assert all("synthetic-value" not in p.excerpt for p in response.probes)


async def test_timeout_is_unknown():
    def handler(req):
        raise httpx.ReadTimeout("secret must not escape")

    client = HttpHealthClient(
        allowed_urls={"https://demo.example/health"}, transport=httpx.MockTransport(handler)
    )
    result = await TelemetryWatchdog(client).run(
        HealthCheckRequest(endpoint="https://demo.example/health")
    )
    assert result.state == "unknown" and result.error.code == "timeout"


async def test_commit_ranking_and_truncation(request_data):
    github = RecordedGitHubClient(FIXTURES / "github.json")
    req = CommitAnalysisRequest(
        repository=request_data.repository,
        branch="main",
        incident_at=request_data.incident_at,
        max_diff_bytes=128,
    )
    result = await CommitDetective(github).run(req)
    assert result.commits[0].sha == "b" * 40
    assert "not proof" in result.commits[0].explanation
    github.data["commits"][0]["files"][0]["patch"] = "x" * 10000
    result = await CommitDetective(github).run(req)
    assert any("truncated" in w for w in result.warnings)
    assert all(sum(len(d.encode()) for d in c.files.values()) <= 128 for c in result.commits)
    github.data["commits"] = []
    assert (await CommitDetective(github).run(req)).commits == []


async def test_security_and_unknown_fix():
    data = json.loads((FIXTURES / "github.json").read_text())
    osv = RecordedOSVClient(FIXTURES / "osv.json")
    agent = SecurityInvestigator(osv)
    result = await agent.run(SecurityScanRequest(files=data["files"]))
    assert {f.id for f in result.findings} >= {"DEMO-2026-001", "tls-disabled:unsafe_sample.py:2"}
    assert result.risk_score == 8
    osv.data["details"]["DEMO-2026-001"]["affected"][0]["ranges"] = []
    result = await agent.run(SecurityScanRequest(files=data["files"]))
    assert "unknown" in next(f for f in result.findings if f.kind == "dependency").remediation


async def test_osv_failure_retains_code():
    class Broken:
        async def query_batch(self, deps):
            raise TimeoutError()

    result = await SecurityInvestigator(Broken()).run(
        SecurityScanRequest(files={"x.py": "run(command, shell=True)"})
    )
    assert not result.success and result.findings and result.error.code == "osv_unavailable"


def test_supported_manifest_parsers_and_lock_precedence():
    files = {
        "requirements.txt": "requests==2.32.0",
        "pyproject.toml": '[project]\ndependencies=["httpx==0.28.1"]',
        "package.json": '{"dependencies":{"demo":"^1.0.0"}}',
        "package-lock.json": '{"packages":{"node_modules/demo":{"version":"1.0.2"}}}',
        "go.mod": "require example.org/module v1.2.3",
        "pom.xml": "<project><dependencies><dependency><groupId>x</groupId><artifactId>y</artifactId><version>1.0</version></dependency></dependencies></project>",
    }
    deps, warnings = dependencies(files)
    assert len(deps) == 5 and not warnings
    assert next(d.version for d in deps if d.name == "demo") == "1.0.2"


def test_narrow_sast_redacts():
    value = "synthetic-" + "private-value"
    findings = code_findings(
        {
            "x.py": f"password='{value}'\ncursor.execute(f'SELECT {{user}}')\nrun(user, shell=True)\nget(url, verify=False)\nCORS(allow_origins=['*'])",
            "Dockerfile": "FROM python:latest",
        },
        [],
    )
    assert len(findings) == 6
    assert value not in str(findings)
