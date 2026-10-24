"""Official ACP models and protocol handlers, with no Agent registration or publication."""

import json
from uuid import UUID

from uagents import Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    MetadataContent,
    StartSessionContent,
    TextContent,
    chat_protocol_spec,
)

from sentinel_ops import cards
from sentinel_ops.schemas import AgentError, InvestigationContext, InvestigationRequest, Status
from sentinel_ops.services.health_client import validate_url


def text_message(text: str) -> ChatMessage:
    return ChatMessage(content=[TextContent(type="text", text=text)])


class ChatGateway:
    simulated = True
    remediation_enabled = True
    patch_enabled = True

    def __init__(self, orchestrator):
        self.orchestrator = orchestrator
        self.store = orchestrator.store

    def validate_intake(self, data):
        pass

    async def handle(self, sender: str, session: str, message: ChatMessage):
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
                    if not data.get("branch"):
                        data["branch"] = await self.orchestrator.commits.client.default_branch(
                            data["repository"]
                        )
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
        if action == "evidence":
            current_id = self.store.read("session", owner)
            report = self.store.read("report", current_id or "")
            return [text_message(report or "No evidence available")]
        raise ValueError("Action not implemented in local read-only phase")


def build_protocol(gateway: ChatGateway) -> Protocol:
    protocol = Protocol(spec=chat_protocol_spec)

    @protocol.on_message(ChatMessage)
    async def message(ctx, sender: str, msg: ChatMessage):
        await ctx.send(sender, ChatAcknowledgement(acknowledged_msg_id=msg.msg_id))
        for response in (await gateway.handle(sender, str(ctx.session), msg))[1:]:
            await ctx.send(sender, response)

    @protocol.on_message(ChatAcknowledgement)
    async def acknowledgement(ctx, sender: str, msg: ChatAcknowledgement):
        return None

    return protocol
