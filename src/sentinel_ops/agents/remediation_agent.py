"""Standalone Sentinel-Remediation uAgent."""

import argparse
import json
import os
import secrets
from pathlib import Path
from uuid import UUID

from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    MetadataContent,
    ResourceContent,
    TextContent,
    chat_protocol_spec,
)

from sentinel_ops.agents.remediation_executor import RemediationExecutor
from sentinel_ops.discovery import save_agent_address
from sentinel_ops.logging import configure_logging
from sentinel_ops.protocols.remediation import (
    RemediationExecutionRequest,
    RemediationExecutionResponse,
    RemediationProposalRequest,
    RemediationProposalResponse,
    remediation_protocol,
)
from sentinel_ops.runtime import load_settings
from sentinel_ops.schemas import (
    Evidence,
    InvestigationContext,
    Status,
)
from sentinel_ops.schemas import (
    RemediationExecutionRequest as SchemaRemediationExecutionRequest,
)
from sentinel_ops.services.github_remediation import (
    GitHubRemediationClient,
    LiveRemediationExecutor,
)
from sentinel_ops.services.sandbox_github import SandboxGitHubClient
from sentinel_ops.state import StateStore


def build_remediation_agent(
    root: Path | None = None,
    seed: str | None = None,
    port: int = 8004,
    mailbox: bool = True,
    endpoint: str | None = None,
    github_token: str | None = None,
    repositories: set[str] | None = None,
    pr_writes: bool = False,
    store: StateStore | None = None,
    executor=None,
) -> Agent:
    root = (root or Path.cwd()).resolve()
    runtime_dir = root / ".local" / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    if not seed:
        seed_file = runtime_dir / "remediation.seed"
        if seed_file.exists():
            seed = seed_file.read_text(encoding="utf-8").strip()
        else:
            seed = secrets.token_urlsafe(48)
            seed_file.write_text(seed, encoding="utf-8")

    agent = Agent(
        name="Sentinel-Remediation",
        seed=seed,
        port=port,
        mailbox=mailbox,
        endpoint=endpoint,
        readme_path=str(root / "docs" / "agent-profile-remediation.md")
        if (root / "docs" / "agent-profile-remediation.md").exists()
        else None,
        description="Draft PR creation, revert proposals, and confirmation verification.",
    )

    if store is None:
        store = StateStore(runtime_dir / "remediation.sqlite")

    if executor is None:
        if pr_writes and github_token and repositories:
            remediation_client = GitHubRemediationClient(github_token, repositories)
            executor = LiveRemediationExecutor(store, remediation_client)
        else:
            sandbox_client = SandboxGitHubClient(store)
            # Preload default sandbox files if not present
            try:
                sandbox_client.initialize({
                    "config.json": '{"healthy": false}\n',
                    "requirements.txt": "demo-vulnerable==1.0.0\n",
                })
            except Exception:
                pass
            executor = RemediationExecutor(store, sandbox_client)

    # 1. Internal Remediation Protocol
    @remediation_protocol.on_message(RemediationProposalRequest)
    async def handle_proposal_request(ctx: Context, sender: str, msg: RemediationProposalRequest):
        inv_id = UUID(msg.investigation_id)
        # Ensure investigation state exists locally
        try:
            store.get(inv_id)
        except KeyError:
            store.create(
                InvestigationContext(
                    investigation_id=inv_id,
                    repository=msg.repository or "demo/checkout",
                    branch=msg.base_branch or "main",
                    endpoint="https://checkout.example/health",
                    permission="create_pr",
                    status=Status.AWAITING,
                    session_id=msg.session_id or sender,
                )
            )

        try:
            if hasattr(executor, "propose_revert") and msg.report_json:
                from sentinel_ops.agents.orchestrator import IncidentReport
                report = IncidentReport.model_validate_json(msg.report_json)
                proposal, nonce, key = await executor.propose_revert(inv_id, msg.session_id or sender, report)
            else:
                evidence_objs = [
                    Evidence.model_validate(e) for e in msg.evidence
                ]
                proposal, nonce, key = executor.propose(
                    investigation_id=inv_id,
                    session=msg.session_id or sender,
                    action=msg.action,
                    evidence=evidence_objs,
                    confidence=msg.confidence,
                    commit_sha=msg.commit_sha,
                    replacements=msg.replacements or None,
                )
            await ctx.send(
                sender,
                RemediationProposalResponse(
                    investigation_id=str(inv_id),
                    proposal_id=str(proposal.proposal_id),
                    nonce=nonce,
                    key=key,
                    proposal_data=proposal.model_dump(mode="json"),
                    simulated=isinstance(executor, RemediationExecutor),
                    success=True,
                ),
            )
        except Exception as err:
            await ctx.send(
                sender,
                RemediationProposalResponse(
                    investigation_id=str(inv_id),
                    success=False,
                    error={"code": "proposal_failed", "message": str(err)},
                ),
            )

    @remediation_protocol.on_message(RemediationExecutionRequest)
    async def handle_execution_request(ctx: Context, sender: str, msg: RemediationExecutionRequest):
        try:
            req = SchemaRemediationExecutionRequest(
                investigation_id=UUID(msg.investigation_id),
                proposal_id=UUID(msg.proposal_id),
                session_id=msg.session_id,
                confirmation=msg.confirmation,
                idempotency_key=msg.idempotency_key,
            )
            res = await executor.execute(req)
            await ctx.send(
                sender,
                RemediationExecutionResponse(
                    investigation_id=str(res.investigation_id),
                    agent_name="Sentinel-Remediation",
                    success=res.success,
                    pr_number=res.pr_number,
                    pr_url=res.pr_url,
                    validation=res.validation,
                    simulated=res.simulated,
                    warnings=res.warnings,
                    evidence=[e.model_dump(mode="json") for e in res.evidence],
                    error=res.error.model_dump(mode="json") if res.error else None,
                ),
            )
        except Exception as err:
            await ctx.send(
                sender,
                RemediationExecutionResponse(
                    investigation_id=msg.investigation_id,
                    success=False,
                    error={"code": "execution_failed", "message": str(err)},
                ),
            )

    agent.include(remediation_protocol)

    # 2. External Chat Protocol (ACP)
    chat_proto = Protocol(spec=chat_protocol_spec)

    @chat_proto.on_message(ChatMessage)
    async def handle_chat(ctx: Context, sender: str, msg: ChatMessage):
        await ctx.send(sender, ChatAcknowledgement(acknowledged_msg_id=msg.msg_id))
        
        # Check for unsupported content types
        unsupported = [c for c in msg.content if not isinstance(c, (TextContent, MetadataContent))]
        if unsupported:
            reply = "This agent only supports text input. Images, files, and other media cannot be processed. Please describe what you need in text."
            await ctx.send(sender, ChatMessage(content=[TextContent(type="text", text=reply)]))
            return
        
        text = "\n".join(
            c.text for c in msg.content if isinstance(c, TextContent)
        ).strip()
        data = {}
        if text.startswith("{") and text.endswith("}"):
            try:
                data = json.loads(text)
            except Exception:
                pass

        action = data.get("action", "")

        if "propose" in action.lower() or "revert" in action.lower():
            reply = (
                "No proposal created by this chat command. Use Sentinel-Orchestrator to investigate "
                "and request a confirmation-bound proposal through the remediation protocol."
            )
        elif "confirm" in action.lower():
            reply = (
                "No PR created by this chat command. Submit the generated confirmation through "
                "Sentinel-Orchestrator; execution must validate the saved proposal and approval."
            )
        else:
            reply = (
                "Sentinel-Remediation Agent: Safe sandbox & GitHub PR generation.\n"
                "Commands:\n"
                "- Send {'action': 'propose_revert', 'investigation_id': '...'}\n"
                "- Send {'action': 'confirm', 'proposal_id': '...', 'confirmation': '...', 'idempotency_key': '...'}"
            )

        await ctx.send(sender, ChatMessage(content=[TextContent(type="text", text=reply)]))

    @chat_proto.on_message(ChatAcknowledgement)
    async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
        pass

    agent.include(chat_proto, publish_manifest=True)
    save_agent_address(runtime_dir, "remediation", agent.address)
    return agent


def main():
    parser = argparse.ArgumentParser(description="Sentinel-Remediation Agent")
    parser.add_argument("command", nargs="?", choices=["init", "check", "serve"], default="serve")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    root = args.root.resolve()
    runtime_dir = root / ".local" / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    if args.command == "init":
        seed_path = runtime_dir / "remediation.seed"
        if not seed_path.exists():
            seed_path.write_text(secrets.token_urlsafe(48), encoding="utf-8")
        print("Remediation agent identity initialized.")
        return

    settings = load_settings(root)
    if args.command == "check":
        print("Remediation agent configuration valid.")
        return

    configure_logging()
    os.chdir(runtime_dir)
    seed = (
        settings.remediation_seed.get_secret_value()
        if settings.remediation_seed
        else (runtime_dir / "remediation.seed").read_text().strip()
        if (runtime_dir / "remediation.seed").exists()
        else secrets.token_urlsafe(48)
    )

    agent = build_remediation_agent(
        root=root,
        seed=seed,
        port=settings.remediation_port,
        mailbox=settings.mailbox,
        endpoint=settings.endpoint,
        github_token=settings.github_token.get_secret_value() if settings.github_token else None,
        repositories=settings.repositories,
        pr_writes=settings.pr_writes,
    )
    agent.run()


if __name__ == "__main__":
    main()
