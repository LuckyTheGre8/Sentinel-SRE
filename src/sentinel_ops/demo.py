"""Deterministic local judge path. External systems remain explicitly simulated."""

import argparse
import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import uvicorn

from sentinel_ops import cards
from sentinel_ops.acp import text_message
from sentinel_ops.agents.orchestrator import IncidentReport
from sentinel_ops.agents.remediation_executor import BAD_COMMIT, RemediationExecutor
from sentinel_ops.demo_service import create_app, running_service
from sentinel_ops.logging import configure_logging
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


def fresh_database(root: Path = ROOT) -> Path:
    database = root / ".local" / "demo" / str(uuid4()) / "state.sqlite"
    store = StateStore(database)
    try:
        files = json.loads((FIXTURES / "github.json").read_text())["files"]
        SandboxGitHubClient(store).initialize(files)
    finally:
        store.close()
    return database


def open_gateway(database: Path, endpoint: str):
    store = StateStore(database)
    client = SandboxGitHubClient(store)
    health = HttpHealthClient(allowed_urls={endpoint}, local_demo=True)
    orchestrator = make_orchestrator(store, health)
    return store, client, RemediationChatGateway(orchestrator, RemediationExecutor(store, client))


async def conversation(database: Path, endpoint: str, *, approve: bool) -> dict:
    store, client, gateway = open_gateway(database, endpoint)
    session = str(uuid4())
    request = InvestigationRequest(
        repository="demo/checkout",
        branch="main",
        endpoint=endpoint,
        permission="create_pr",
        incident_at=datetime(2026, 10, 24, 4, tzinfo=timezone.utc),
    )
    transcript = []

    async def send(data):
        replies = await gateway.handle("local-demo-user", session, text_message(json.dumps(data)))
        transcript.append(
            {
                "action": data.get("action", "intake"),
                "reply_types": [type(r).__name__ for r in replies],
            }
        )
        return replies

    try:
        intake = await send(request.model_dump(mode="json"))
        start = cards.validate_card(intake[-1])["approve_cta"]["selection"]
        reports = await send(start)
        cards.validate_card(reports[-1])
        report = IncidentReport.model_validate_json(
            store.read("report", str(request.investigation_id))
        )
        if not report.commits.commits or report.commits.commits[0].sha != BAD_COMMIT:
            raise AssertionError("Intended bad change did not rank first")
        if "DEMO-2026-001" not in {f.id for f in report.security.findings}:
            raise AssertionError("Intended fixture vulnerability missing")
        if report.health.state != "failing" or any(p.status != 503 for p in report.health.probes):
            raise AssertionError("Demo must start with independently observed HTTP 503")
        confirmation = await send({"action": "review_revert"})
        payload = cards.validate_card(confirmation[-1])
        selection = payload["approve_cta"]["selection"]
        missing = await send({**selection, "confirmation": ""})
        rejected = RemediationExecutionResponse.model_validate_json(missing[-1].content[0].text)
        if rejected.success or client.count() != 0:
            raise AssertionError("Confirmation gate failed")
        if not approve:
            print(json.dumps(payload["summary_rows"], indent=2))
            if (
                input("Type CONFIRM to create a simulated PR and apply the local demo recovery: ")
                != "CONFIRM"
            ):
                await send({"action": "cancel"})
                return {"result": "cancelled", "simulated": True}
        executed = await send(selection)
        first = RemediationExecutionResponse.model_validate_json(executed[-1].content[0].text)
        if not first.success:
            raise AssertionError(f"Sandbox execution failed: {first.error}")
        # Independent probe proves PR creation did not silently recover/merge anything.
        after_pr = await gateway.orchestrator.telemetry.run(
            VerificationRequest(investigation_id=request.investigation_id, endpoint=endpoint)
        )
        if after_pr.state != "failing":
            raise AssertionError("PR creation unexpectedly changed service state")
        store.close()
        store, client, gateway = open_gateway(database, endpoint)
        repeated = await send(selection)  # New ACP message, same approval, reopened SQLite.
        second = RemediationExecutionResponse.model_validate_json(repeated[-1].content[0].text)
        if second != first or client.count() != 1:
            raise AssertionError("Restart-safe idempotency failed")
        client.apply_local(selection["idempotency_key"])
        final = await gateway.orchestrator.telemetry.run(
            VerificationRequest(investigation_id=request.investigation_id, endpoint=endpoint)
        )
        status = Status.RESOLVED if final.state == "healthy" else Status.PARTIAL
        store.transition(request.investigation_id, status)
        resolution = cards.resolution(first, report.health, final, status.value)
        cards.validate_card(resolution)
        if status != Status.RESOLVED or any(p.status != 200 for p in final.probes):
            raise AssertionError("Independent recovery verification failed")
        result = {
            "mode": "local sandbox; GitHub/OSV/ASI reasoning simulated; HTTP real loopback",
            "investigation_id": str(request.investigation_id),
            "ranked_first": BAD_COMMIT,
            "vulnerability": "DEMO-2026-001 (synthetic)",
            "confirmation_required": not rejected.success,
            "pr_number": first.pr_number,
            "pr_reference": first.pr_url,
            "pr_count": client.count(),
            "restart_replay_identical": second == first,
            "initial_http": report.health.probes[0].status,
            "after_pr_http": after_pr.probes[0].status,
            "final_http": final.probes[0].status,
            "result": status.value,
            "transcript": transcript,
        }
        (database.parent / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result
    finally:
        store.close()


async def smoke(runs: int = 2, root: Path = ROOT) -> list[dict]:
    results = []
    for _ in range(runs):
        database = fresh_database(root)
        with running_service(database) as endpoint:
            results.append(await conversation(database, endpoint, approve=True))
    return results


def main():
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["smoke", "init", "serve", "chat"])
    parser.add_argument("--runs", type=int, choices=range(1, 11), default=2)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    logging.getLogger("httpx").setLevel(logging.WARNING)
    pointer = ROOT / ".local" / "demo-current.json"
    if args.command == "smoke":
        print(json.dumps(asyncio.run(smoke(args.runs)), indent=2))
    elif args.command == "init":
        database = fresh_database()
        pointer.write_text(
            json.dumps({"database": str(database.relative_to(ROOT))}), encoding="utf-8"
        )
        print("Fresh failing sandbox initialized. Previous demo runs are retained.")
    else:
        database = (ROOT / json.loads(pointer.read_text())["database"]).resolve()
        if not database.is_relative_to(ROOT / ".local" / "demo"):
            raise ValueError("Demo database outside permitted directory")
        if args.command == "serve":
            uvicorn.run(create_app(database), host="127.0.0.1", port=args.port, access_log=False)
        else:
            print(
                json.dumps(
                    asyncio.run(
                        conversation(
                            database, f"http://127.0.0.1:{args.port}/health", approve=False
                        )
                    ),
                    indent=2,
                )
            )


if __name__ == "__main__":
    main()
