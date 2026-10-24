"""Local ASI:One-style read-only conversation using real ACP envelopes."""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

from sentinel_ops.acp import ChatGateway, text_message
from sentinel_ops.agents.commit_detective import CommitDetective
from sentinel_ops.agents.orchestrator import SentinelOrchestrator
from sentinel_ops.agents.security_investigator import SecurityInvestigator
from sentinel_ops.agents.telemetry_watchdog import TelemetryWatchdog
from sentinel_ops.cards import validate_card
from sentinel_ops.schemas import InvestigationRequest
from sentinel_ops.services.github_client import RecordedGitHubClient
from sentinel_ops.services.health_client import HttpHealthClient
from sentinel_ops.services.osv_client import RecordedOSVClient
from sentinel_ops.services.reasoning import LocalReasoningClient
from sentinel_ops.state import StateStore

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"


def make_orchestrator(
    store,
    health_client=None,
    *,
    github_client=None,
    osv_client=None,
    reasoning_client=None,
):
    health_client = health_client or HttpHealthClient(
        allowed_urls={"https://checkout.example/health"},
        transport=httpx.MockTransport(lambda request: httpx.Response(503, text="synthetic outage")),
    )
    return SentinelOrchestrator(
        store,
        TelemetryWatchdog(health_client),
        CommitDetective(github_client or RecordedGitHubClient(FIXTURES / "github.json")),
        SecurityInvestigator(osv_client or RecordedOSVClient(FIXTURES / "osv.json")),
        reasoning_client or LocalReasoningClient(),
    )


def make_live_evidence_clients(github_token: str | None = None):
    """Construct live, read-only GitHub and OSV adapters for explicit runtime wiring."""
    from sentinel_ops.services.github_client import LiveGitHubClient
    from sentinel_ops.services.osv_client import LiveOSVClient

    return LiveGitHubClient(token=github_token), LiveOSVClient()


async def simulate():
    store = StateStore(ROOT / ".local" / "conversation.sqlite")
    try:
        gateway = ChatGateway(make_orchestrator(store))
        request = InvestigationRequest(
            repository="demo/checkout",
            branch="main",
            endpoint="https://checkout.example/health",
            incident_at=datetime(2026, 10, 24, 4, tzinfo=timezone.utc),
        )
        intake = await gateway.handle(
            "local-user", str(request.investigation_id), text_message(request.model_dump_json())
        )
        selection = validate_card(intake[-1])["approve_cta"]["selection"]
        replies = await gateway.handle(
            "local-user", str(request.investigation_id), text_message(json.dumps(selection))
        )
        print("LOCAL SIMULATION; no ASI:One model or external agent contacted")
        print(json.dumps(validate_card(replies[-1]), indent=2))
    finally:
        store.close()


if __name__ == "__main__":
    asyncio.run(simulate())
