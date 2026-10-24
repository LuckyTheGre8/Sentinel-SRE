"""Opt-in rehearsal commands. Measured local HTTP, explicit external-system fixtures."""

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from uagents_core.contrib.protocols.chat import TextContent

from sentinel_ops import cards
from sentinel_ops.acp import text_message
from sentinel_ops.agents.orchestrator import IncidentReport
from sentinel_ops.demo import fresh_database, open_gateway
from sentinel_ops.demo_service import running_service
from sentinel_ops.schemas import (
    InvestigationRequest,
    RemediationExecutionResponse,
    Status,
    VerificationRequest,
)

LABEL = "DEMO SANDBOX | real loopback HTTP; recorded commits/OSV; local reasoning; simulated PR. No remote worker calls."
HELP = (
    LABEL + "\nSend these exact commands in this chat:\n"
    "demo start — investigate a fresh checkout outage\n"
    "demo evidence — explain the recorded evidence\n"
    "demo approve — explicitly approve a sandbox PR (no deployment)\n"
    "demo recover — apply the sandbox change and independently probe recovery\n"
    "demo start resets the scenario. Live investigations use the normal intake flow."
)


class GuidedDemo:
    def __init__(self, root: Path, store):
        self.root = root.resolve()
        self.store = store

    async def handle(self, sender, session, message):
        command = (
            "\n".join(c.text for c in message.content if isinstance(c, TextContent)).strip().lower()
        )
        if not command.startswith("demo"):
            return None
        owner = json.dumps([sender, session])
        cache_key = json.dumps([sender, session, str(message.msg_id)])
        cached = self.store.read("guided_demo_reply", cache_key)
        if cached:
            return cached
        try:
            reply = await self.run(owner, command)
        except (ValueError, KeyError, OSError, RuntimeError, AssertionError):
            reply = (
                LABEL
                + "\nDemo step failed; no success claimed. Send demo start to reset, or use the terminal fallback."
            )
        self.store.put("guided_demo_reply", cache_key, reply)
        return reply

    async def run(self, owner, command):
        if command not in {"demo start", "demo evidence", "demo approve", "demo recover"}:
            return HELP
        if command == "demo start":
            state = {"database": str(fresh_database(self.root)), "session": str(uuid4())}
        else:
            raw = self.store.read("guided_demo", owner)
            if not raw:
                return LABEL + "\nSend demo start first in this same chat."
            state = json.loads(raw)
        database = Path(state["database"]).resolve()
        if not database.is_relative_to(self.root / ".local" / "demo"):
            raise ValueError("Invalid demo database")
        with running_service(database) as endpoint:
            store, client, gateway = open_gateway(database, endpoint)

            async def send(data):
                return await gateway.handle(
                    "guided-demo", state["session"], text_message(json.dumps(data))
                )

            try:
                if command == "demo start":
                    request = InvestigationRequest(
                        repository="demo/checkout",
                        branch="main",
                        endpoint=endpoint,
                        permission="create_pr",
                        incident_at=datetime(2026, 10, 24, 4, tzinfo=timezone.utc),
                    )
                    intake = await send(request.model_dump(mode="json"))
                    await send(cards.validate_card(intake[-1])["approve_cta"]["selection"])
                    state["investigation_id"] = str(request.investigation_id)
                    report = IncidentReport.model_validate_json(
                        store.read("report", state["investigation_id"])
                    )
                    if not report.health.success or report.health.state != "failing":
                        raise ValueError("No measured outage")
                    proposal = await send({"action": "review_revert"})
                    state["selection"] = cards.validate_card(proposal[-1])["approve_cta"][
                        "selection"
                    ]
                    rejected = await send({**state["selection"], "confirmation": ""})
                    rejection = RemediationExecutionResponse.model_validate_json(
                        rejected[-1].content[0].text
                    )
                    if rejection.success or client.count() != 0:
                        raise AssertionError("Confirmation gate failed")
                    self.store.put("guided_demo", owner, json.dumps(state))
                    return LABEL + (
                        f"\nCheckout: HTTP {report.health.probes[0].status}; {report.health.state}."
                        f"\nCandidate: {report.hypothesis.commit_sha}; confidence {report.hypothesis.confidence}."
                        "\nCorrelation is not proof of causation. A revert proposal is ready."
                        "\nMissing approval was tested and blocked; zero PRs created."
                        "\nNext: demo evidence or demo approve."
                    )
                if command == "demo evidence":
                    report = IncidentReport.model_validate_json(
                        store.read("report", state["investigation_id"])
                    )
                    return (
                        LABEL
                        + "\n"
                        + json.dumps(
                            {
                                "observed_http": [p.status for p in report.health.probes],
                                "hypothesis": report.hypothesis.model_dump(mode="json"),
                                "security_findings": [f.id for f in report.security.findings],
                                "warnings": report.warnings,
                                "next": "demo approve",
                            },
                            indent=2,
                        )
                    )
                inv_id = UUID(state["investigation_id"])
                if command == "demo approve":
                    response = await send(state["selection"])
                    result = RemediationExecutionResponse.model_validate_json(
                        response[-1].content[0].text
                    )
                    if not result.success:
                        return (
                            LABEL
                            + "\nApproval was not executed. Send demo start for a fresh proposal."
                        )
                    probe = await gateway.orchestrator.telemetry.run(
                        VerificationRequest(investigation_id=inv_id, endpoint=endpoint)
                    )
                    return LABEL + (
                        f"\nSandbox PR #{result.pr_number}: {result.pr_url}. Total PRs: {client.count()}."
                        f"\nCurrent measured health: {probe.state}; PR creation does not deploy a change."
                        "\nNext: demo recover explicitly applies the sandbox change and verifies it."
                    )
                if client.count() == 0:
                    return LABEL + "\nNo approved PR. Send demo approve before demo recover."
                client.apply_local(state["selection"]["idempotency_key"])
                probe = await gateway.orchestrator.telemetry.run(
                    VerificationRequest(investigation_id=inv_id, endpoint=endpoint)
                )
                if not probe.success or probe.state != "healthy":
                    return LABEL + "\nRecovery not verified; investigation remains unresolved."
                if store.get(inv_id).status == Status.VERIFYING:
                    store.transition(inv_id, Status.RESOLVED)
                return LABEL + (
                    f"\nIndependent probe: HTTP {probe.probes[0].status}; {probe.state}."
                    "\nIncident resolved in the sandbox. Human approval → sandbox PR → explicit local application → measured recovery."
                    "\nSend demo start to rehearse again."
                )
            finally:
                store.close()
