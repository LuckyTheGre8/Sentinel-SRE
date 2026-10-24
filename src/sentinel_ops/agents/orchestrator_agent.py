"""Standalone Sentinel-Orchestrator uAgent coordinating 4 peer agents over native uAgents protocols."""

import argparse
import asyncio
import json
import logging
import os
import secrets
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError
from pydantic.v1 import ValidationError as V1ValidationError
from uagents import Agent, Context
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    MetadataContent,
    StartSessionContent,
    TextContent,
)

from sentinel_ops import cards
from sentinel_ops.acp import ChatGateway, build_protocol, text_message
from sentinel_ops.agents.orchestrator import (
    IncidentReport,
    NetworkWorkerTransport,
    SentinelOrchestrator,
)
from sentinel_ops.discovery import discover_peer_addresses, save_agent_address
from sentinel_ops.logging import configure_logging
from sentinel_ops.protocols.commit import (
    CommitAnalysisResponse,
    commit_protocol,
)
from sentinel_ops.protocols.health import (
    HealthCheckResponse,
    VerificationResponse,
    health_protocol,
)
from sentinel_ops.protocols.remediation import (
    RemediationExecutionRequest as ProtoRemedExecReq,
)
from sentinel_ops.protocols.remediation import (
    RemediationExecutionResponse,
    RemediationProposalResponse,
    remediation_protocol,
)
from sentinel_ops.protocols.remediation import (
    RemediationProposalRequest as ProtoRemedPropReq,
)
from sentinel_ops.protocols.security import (
    SecurityScanResponse,
    security_protocol,
)
from sentinel_ops.runtime import RuntimeSettings, environment, load_settings
from sentinel_ops.schemas import (
    AgentError,
    InvestigationContext,
    InvestigationRequest,
    RemediationExecutionRequest,
    RemediationProposal,
    Status,
    VerificationRequest,
)
from sentinel_ops.services.asi1_client import ASI1ReasoningClient
from sentinel_ops.services.health_client import validate_url
from sentinel_ops.services.reasoning import LocalReasoningClient
from sentinel_ops.state import StateStore


class NetworkLiveGateway(ChatGateway):
    simulated = False
    remediation_enabled = True
    patch_enabled = True

    def __init__(
        self,
        orchestrator: SentinelOrchestrator,
        settings: RuntimeSettings,
        transport: NetworkWorkerTransport,
    ):
        super().__init__(orchestrator)
        self.settings = settings
        self.transport = transport
        self.lock = asyncio.Lock()
        self.demo = None
        self.remediation_enabled = settings.pr_writes
        self.patch_enabled = False

    def validate_intake(self, data):
        if (
            "repository" in data
            and self.settings.repositories
            and data["repository"] not in self.settings.repositories
        ):
            raise ValueError("Repository outside configured scope")
        if (
            "endpoint" in data
            and self.settings.health_urls
            and data["endpoint"] not in self.settings.health_urls
        ):
            raise ValueError("Endpoint outside configured scope")

    async def handle(self, sender: str, session: str, message: ChatMessage):
        if self.settings.allowed_senders and sender not in self.settings.allowed_senders:
            return [
                ChatAcknowledgement(acknowledged_msg_id=message.msg_id),
                text_message("Sender not authorized"),
            ]
        if self.demo is not None:
            async with self.lock:
                reply = await self.demo.handle(sender, session, message)
            if reply is not None:
                return [
                    ChatAcknowledgement(acknowledged_msg_id=message.msg_id),
                    text_message(reply),
                ]
        # Handle intake directly to avoid needing commits.client.default_branch
        # which is not available in network mode (commits worker is remote)
        return await self._handle_with_intake_override(sender, session, message)

    async def _handle_with_intake_override(self, sender: str, session: str, message: ChatMessage):
        """Override of handle that doesn't require local commits client."""
        ack = ChatAcknowledgement(acknowledged_msg_id=message.msg_id)
        owner = json.dumps([sender, session])
        dedup = json.dumps([sender, session, str(message.msg_id)])
        cached = self.store.read("chat", dedup)
        if cached:
            return [ack, *[ChatMessage.model_validate(x) for x in json.loads(cached)]]
        try:
            content = [c for c in message.content if not isinstance(c, StartSessionContent)]
            if not content:
                raise ValueError("Empty message")

            # Check for unsupported content types (images, resources, etc.)
            unsupported = [c for c in content if not isinstance(c, (TextContent, MetadataContent))]
            if unsupported:
                raise ValueError(
                    "This agent only supports text input. Images, files, and other media "
                    "cannot be processed. Please describe what you need in text."
                )

            text = "\n".join(c.text for c in content if isinstance(c, TextContent))
            if len(text.encode()) > 8192:
                raise ValueError("Input exceeds local limit")
            data = await self.orchestrator.reasoning.extract(text)
            if not isinstance(data, dict):
                raise ValueError("Expected structured input")
            action = data.pop("action", "intake")
            if not isinstance(action, str):
                raise ValueError("Invalid action")
            if action == "start":
                raw = self.store.read("intake", owner)
                if raw is None:
                    raise ValueError("No pending intake")
                request = InvestigationRequest.model_validate_json(raw)
                if data.get("investigation_id") != str(request.investigation_id):
                    raise ValueError("Intake correlation mismatch")
                context = InvestigationContext(**request.model_dump(), session_id=owner)
                try:
                    current = self.store.get(request.investigation_id)
                except KeyError:
                    self.store.create(context)
                else:
                    if current.status != Status.CREATED or current.session_id != owner:
                        raise ValueError("Investigation already started")
                report = await self.orchestrator.investigate(context)
                self.store.put("session", owner, str(context.investigation_id))
                replies = [
                    cards.incident_report(
                        report,
                        simulated=self.simulated,
                        remediation_enabled=self.remediation_enabled
                        and context.permission == "create_pr",
                        patch_enabled=self.patch_enabled,
                    )
                ]
            elif action == "cancel":
                current_id = self.store.read("session", owner)
                if current_id:
                    self.store.transition(UUID(current_id), Status.CANCELLED)
                self.store.put("intake", owner, "")
                replies = [text_message("Cancelled local interaction.")]
            elif action == "intake":
                draft = self.store.read("intake_draft", owner)
                data = {**(json.loads(draft) if draft else {}), **data}
                allowed = set(InvestigationRequest.model_fields)
                if not set(data) <= allowed:
                    raise ValueError("Unsupported intake fields")
                self.validate_intake(data)
                if "endpoint" in data:
                    if not isinstance(data["endpoint"], str):
                        raise ValueError("Invalid endpoint")
                    validate_url(data["endpoint"], local_demo=True)
                self.store.put("intake_draft", owner, json.dumps(data))
                missing = [k for k in ("repository", "endpoint") if not data.get(k)]
                if missing:
                    replies = [cards.intake(missing, simulated=self.simulated)]
                else:
                    # In network mode, default to "main" branch since we can't query GitHub
                    if not data.get("branch"):
                        data["branch"] = "main"
                    request = InvestigationRequest.model_validate(data)
                    self.store.put("intake", owner, request.model_dump_json())
                    replies = [cards.review_intake(request, simulated=self.simulated)]
            else:
                replies = await self.action(owner, action, data)
        except (ValueError, KeyError, TimeoutError, OSError):
            error = AgentError(
                code="unsupported_input",
                message="Input/action invalid, incomplete, expired, or outside local fixture coverage",
            )
            replies = [text_message(error.model_dump_json())]
        self.store.put(
            "chat", dedup, json.dumps([json.loads(r.model_dump_json()) for r in replies])
        )
        return [ack, *replies]

    async def action(self, owner: str, action: str, data: dict):
        current = self.store.read("session", owner)
        if not current:
            return await super().action(owner, action, data)

        inv_id = UUID(current)
        context = self.store.get(inv_id)

        if action == "review_revert":
            if not self.remediation_enabled or context.permission != "create_pr":
                raise ValueError("PR creation is not enabled for this investigation")
            report_raw = self.store.read("report", current)
            report = IncidentReport.model_validate_json(report_raw) if report_raw else None
            top_sha = report.hypothesis.commit_sha if report else None

            # Dispatch proposal request to remediation agent
            prop_req = ProtoRemedPropReq(
                investigation_id=current,
                session_id=owner,
                repository=context.repository,
                base_branch=context.branch,
                action="revert_commit",
                commit_sha=top_sha,
                confidence=report.hypothesis.confidence if report else "medium",
                report_json=report_raw,
            )
            prop_resp = await self.transport.dispatch(
                "remediation",
                None,
                prop_req,
                RemediationProposalResponse,
            )
            if not prop_resp.success:
                raise ValueError(
                    prop_resp.error.get("message")
                    if prop_resp.error
                    else "Proposal failed at remediation agent"
                )

            proposal = RemediationProposal.model_validate(prop_resp.proposal_data)
            return [
                cards.confirmation(
                    proposal, prop_resp.nonce, prop_resp.key, simulated=prop_resp.simulated
                )
            ]

        if action == "confirm":
            if not self.remediation_enabled or context.permission != "create_pr":
                raise ValueError("PR creation is not enabled for this investigation")
            exec_req = RemediationExecutionRequest.model_validate({**data, "session_id": owner})
            if str(exec_req.investigation_id) != current:
                raise ValueError("Session investigation mismatch")

            proto_exec_req = ProtoRemedExecReq(
                investigation_id=str(exec_req.investigation_id),
                proposal_id=str(exec_req.proposal_id),
                session_id=exec_req.session_id,
                confirmation=exec_req.confirmation,
                idempotency_key=exec_req.idempotency_key,
            )
            exec_resp = await self.transport.dispatch(
                "remediation",
                None,
                proto_exec_req,
                RemediationExecutionResponse,
            )
            if not exec_resp.success:
                err_msg = exec_resp.error.get("message") if exec_resp.error else "Execution failed"
                raise ValueError(err_msg)

            if context.status == Status.AWAITING:
                self.store.transition(inv_id, Status.EXECUTING)
                self.store.transition(inv_id, Status.VERIFYING)
            return [
                text_message(
                    f"{'Sandbox' if exec_resp.simulated else 'GitHub'} PR created: #{exec_resp.pr_number} ({exec_resp.pr_url})\n"
                    'After manually merging/deploying, send {"action":"verify"} to check recovery.'
                )
            ]

        if action == "verify":
            if context.status != Status.VERIFYING:
                raise ValueError("No confirmed remediation awaiting verification")

            v_req = VerificationRequest(
                investigation_id=context.investigation_id, endpoint=context.endpoint
            )
            result = await self.transport.dispatch(
                "health",
                None,
                v_req,
                HealthCheckResponse,
            )
            if result.success and result.state == "healthy":
                self.store.transition(context.investigation_id, Status.RESOLVED)
            return [text_message(result.model_dump_json())]

        return await super().action(owner, action, data)


def build_orchestrator_agent(
    root: Path | None = None,
    seed: str | None = None,
    port: int = 8005,
    mailbox: bool = True,
    endpoint: str | None = None,
    settings: RuntimeSettings | None = None,
    store: StateStore | None = None,
) -> tuple[Agent, SentinelOrchestrator, NetworkWorkerTransport]:
    root = (root or Path.cwd()).resolve()
    runtime_dir = root / ".local" / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    if not seed:
        seed_file = runtime_dir / "orchestrator.seed"
        agent_seed_file = runtime_dir / "agent.seed"
        if seed_file.exists():
            seed = seed_file.read_text(encoding="utf-8").strip()
        elif agent_seed_file.exists():
            seed = agent_seed_file.read_text(encoding="utf-8").strip()
        else:
            seed = secrets.token_urlsafe(48)
            seed_file.write_text(seed, encoding="utf-8")

    agent = Agent(
        name="Sentinel-Orchestrator",
        seed=seed,
        port=port,
        mailbox=mailbox,
        endpoint=endpoint,
        handle_messages_concurrently=True,
        readme_path=str(root / "docs" / "agent-profile-orchestrator.md")
        if (root / "docs" / "agent-profile-orchestrator.md").exists()
        else str(root / "docs" / "agent-profile.md")
        if (root / "docs" / "agent-profile.md").exists()
        else None,
        description="Coordinates incident investigation and confirmation-bound remediation across Sentinel agents.",
    )

    if store is None:
        store = StateStore(runtime_dir / "investigations.sqlite")

    peers = discover_peer_addresses(runtime_dir, environment(root))
    transport = NetworkWorkerTransport(peer_addresses=peers, timeout=45.0)

    # Wire protocol response listeners on the orchestrator agent
    @health_protocol.on_message(HealthCheckResponse)
    async def on_health_response(ctx: Context, sender: str, msg: HealthCheckResponse):
        transport.handle_response("health", msg.investigation_id, msg)

    @health_protocol.on_message(VerificationResponse)
    async def on_verification_response(ctx: Context, sender: str, msg: VerificationResponse):
        transport.handle_response("health", msg.investigation_id, msg)

    @commit_protocol.on_message(CommitAnalysisResponse)
    async def on_commit_response(ctx: Context, sender: str, msg: CommitAnalysisResponse):
        transport.handle_response("commits", msg.investigation_id, msg)

    @security_protocol.on_message(SecurityScanResponse)
    async def on_security_response(ctx: Context, sender: str, msg: SecurityScanResponse):
        transport.handle_response("security", msg.investigation_id, msg)

    @remediation_protocol.on_message(RemediationProposalResponse)
    async def on_remediation_proposal_response(
        ctx: Context, sender: str, msg: RemediationProposalResponse
    ):
        transport.handle_response("remediation", msg.investigation_id, msg)

    @remediation_protocol.on_message(RemediationExecutionResponse)
    async def on_remediation_exec_response(
        ctx: Context, sender: str, msg: RemediationExecutionResponse
    ):
        transport.handle_response("remediation", msg.investigation_id, msg)

    agent.include(health_protocol)
    agent.include(commit_protocol)
    agent.include(security_protocol)
    agent.include(remediation_protocol)

    # Wire ASI1 reasoning client or fallback
    reasoning_client = None
    if settings and settings.asi1_api_key and settings.asi1_api_key.get_secret_value():
        reasoning_client = ASI1ReasoningClient(
            settings.asi1_api_key.get_secret_value(),
            data_sharing=settings.data_sharing,
            model=settings.model,
        )
    else:
        reasoning_client = LocalReasoningClient()

    # Telemetry, Commits, and Security are accessed via transport network dispatch
    orchestrator = SentinelOrchestrator(
        store=store,
        telemetry=None,
        commits=None,
        security=None,
        reasoning=reasoning_client,
        transport=transport,
        provider_timeout=45.0,
    )

    if settings is None:
        try:
            settings = load_settings(root)
        except Exception:
            settings = RuntimeSettings(
                asi1_api_key="synthetic",
                agent_seed=seed,
                data_sharing=True,
                port=port,
            )

    gateway = NetworkLiveGateway(orchestrator, settings, transport)
    if environment(root).get("SENTINEL_DEMO_MODE", "").lower() == "true":
        from sentinel_ops.guided_demo import GuidedDemo

        gateway.demo = GuidedDemo(root, store)
    agent_chat_proto = build_protocol(gateway)

    # Wrap chat message handler to set transport sender function dynamically
    # Get the original handler from signed_message_handlers
    chat_digest = ChatMessage.build_schema_digest(ChatMessage)
    original_handler = agent_chat_proto.signed_message_handlers.get(chat_digest)
    chat_dispatch_lock = asyncio.Lock()

    @agent_chat_proto.on_message(ChatMessage)
    async def on_user_chat(ctx: Context, sender: str, msg: ChatMessage):
        if original_handler:
            try:
                # Worker replies must run concurrently while one chat owns the
                # transport's send context and investigation state transitions.
                async with chat_dispatch_lock:
                    transport.set_sender(ctx.send)
                    transport.set_peer_addresses(
                        discover_peer_addresses(runtime_dir, environment(root))
                    )
                    await original_handler(ctx, sender, msg)
            except (V1ValidationError, ValidationError) as exc:
                # Malformed or stale messages from the Agentverse mailbox can
                # trigger pydantic validation errors when constructing response
                # ChatMessage objects.  Log the error and acknowledge the message
                # so the mailbox stops retrying delivery.
                logger = logging.getLogger("Sentinel-Orchestrator")
                logger.warning("Dropping malformed mailbox message from %s: %s", sender, exc)
                try:
                    await ctx.send(
                        sender,
                        ChatAcknowledgement(acknowledged_msg_id=msg.msg_id),
                    )
                except Exception:
                    pass

    agent.include(agent_chat_proto, publish_manifest=True)

    save_agent_address(runtime_dir, "orchestrator", agent.address)
    (runtime_dir / "public-agent.json").write_text(
        json.dumps({"name": agent.name, "address": agent.address}, indent=2),
        encoding="utf-8",
    )

    return agent, orchestrator, transport


def main():
    parser = argparse.ArgumentParser(description="Sentinel-Orchestrator Agent")
    parser.add_argument("command", nargs="?", choices=["init", "check", "serve"], default="serve")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    root = args.root.resolve()
    runtime_dir = root / ".local" / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    if args.command == "init":
        seed_path = runtime_dir / "orchestrator.seed"
        if not seed_path.exists():
            seed_path.write_text(secrets.token_urlsafe(48), encoding="utf-8")
        print("Orchestrator agent identity initialized.")
        return

    settings = load_settings(root)
    if args.command == "check":
        print("Orchestrator agent configuration valid.")
        return

    configure_logging()
    os.chdir(runtime_dir)
    seed = (
        settings.orchestrator_seed.get_secret_value()
        if settings.orchestrator_seed
        else settings.agent_seed.get_secret_value()
    )

    agent, orchestrator, transport = build_orchestrator_agent(
        root=root,
        seed=seed,
        port=settings.orchestrator_port,
        mailbox=settings.mailbox,
        endpoint=settings.endpoint,
        settings=settings,
    )
    agent.run()


if __name__ == "__main__":
    main()
