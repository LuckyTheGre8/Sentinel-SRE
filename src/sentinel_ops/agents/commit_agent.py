"""Standalone Sentinel-Commit uAgent."""

import argparse
import asyncio
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from uagents import Agent, Context, Protocol
from uagents_core.contrib.protocols.chat import (
    ChatAcknowledgement,
    ChatMessage,
    MetadataContent,
    ResourceContent,
    TextContent,
    chat_protocol_spec,
)

from sentinel_ops.agents.commit_detective import CommitDetective
from sentinel_ops.discovery import save_agent_address
from sentinel_ops.logging import configure_logging
from sentinel_ops.protocols.commit import (
    CommitAnalysisRequest,
    CommitAnalysisResponse,
    commit_protocol,
)
from sentinel_ops.runtime import load_settings
from sentinel_ops.schemas import (
    CommitAnalysisRequest as SchemaCommitAnalysisRequest,
)
from sentinel_ops.services.github_client import (
    LiveGitHubClient,
)


def build_commit_agent(
    root: Path | None = None,
    seed: str | None = None,
    port: int = 8002,
    mailbox: bool = True,
    endpoint: str | None = None,
    github_token: str | None = None,
    client=None,
) -> Agent:
    root = (root or Path.cwd()).resolve()
    runtime_dir = root / ".local" / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    if not seed:
        seed_file = runtime_dir / "commit.seed"
        if seed_file.exists():
            seed = seed_file.read_text(encoding="utf-8").strip()
        else:
            seed = secrets.token_urlsafe(48)
            seed_file.write_text(seed, encoding="utf-8")

    agent = Agent(
        name="Sentinel-Commit",
        seed=seed,
        port=port,
        mailbox=mailbox,
        endpoint=endpoint,
        readme_path=str(root / "docs" / "agent-profile-commit.md")
        if (root / "docs" / "agent-profile-commit.md").exists()
        else None,
        description="GitHub commit analysis, diff inspection, and blame correlation.",
    )

    if client is None:
        client = LiveGitHubClient(token=github_token)

    detective = CommitDetective(client=client, timeout=30)

    # 1. Internal Commit Protocol
    @commit_protocol.on_message(CommitAnalysisRequest)
    async def handle_commit_analysis(ctx: Context, sender: str, msg: CommitAnalysisRequest):
        incident_time = (
            datetime.fromisoformat(msg.incident_at.replace("Z", "+00:00"))
            if msg.incident_at
            else datetime.now(timezone.utc)
        )
        req = SchemaCommitAnalysisRequest(
            investigation_id=msg.investigation_id,
            repository=msg.repository,
            branch=msg.branch or "main",
            incident_at=incident_time,
            lookback_hours=msg.lookback_hours,
            max_commits=msg.max_commits,
            max_diff_bytes=msg.max_diff_bytes,
            service_hint=msg.service_hint,
        )
        res = await detective.run(req)

        files_data: dict[str, str] = {}
        if res.success and res.commits:
            try:
                top_sha = res.commits[0].sha
                files_data = await asyncio.wait_for(
                    client.files(msg.repository, top_sha), timeout=10.0
                )
            except Exception:
                files_data = {}

        await ctx.send(
            sender,
            CommitAnalysisResponse(
                investigation_id=str(res.investigation_id),
                agent_name="Sentinel-Commit",
                success=res.success,
                commits=[c.model_dump(mode="json") for c in res.commits],
                files=files_data,
                evidence=[e.model_dump(mode="json") for e in res.evidence],
                warnings=res.warnings,
                error=res.error.model_dump(mode="json") if res.error else None,
                started_at=res.started_at.isoformat(),
                completed_at=res.completed_at.isoformat(),
            ),
        )

    agent.include(commit_protocol)

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
        repo = data.get("repository") or (
            text if "/" in text and not text.startswith("http") else ""
        )
        branch = data.get("branch", "main")

        if "analyze" in action.lower() or "commit" in action.lower() or repo:
            if not repo:
                reply = "Please specify a repository: e.g. {'action': 'analyze_commits', 'repository': 'owner/repo', 'branch': 'main'}"
            else:
                try:
                    req = SchemaCommitAnalysisRequest(
                        repository=repo,
                        branch=branch,
                        incident_at=datetime.now(timezone.utc),
                    )
                    res = await detective.run(req)
                    if res.commits:
                        top = res.commits[0]
                        reply = (
                            f"Analyzed {len(res.commits)} commits for {repo}@{branch}.\n"
                            f"Top candidate: {top.sha[:8]} (Score: {top.score:.3f})\n"
                            f"Explanation: {top.explanation}\n"
                            f"Message: {top.message[:100]}"
                        )
                    else:
                        reply = f"No recent commits found for {repo}@{branch}."
                except Exception as err:
                    reply = f"Commit analysis failed: {err}"
        else:
            reply = (
                "Sentinel-Commit Agent: GitHub commit analysis.\n"
                "Commands:\n"
                "- Send {'action': 'analyze_commits', 'repository': 'owner/repo', 'branch': 'main'}\n"
                "- Send 'owner/repo' to inspect recent commits."
            )

        await ctx.send(sender, ChatMessage(content=[TextContent(type="text", text=reply)]))

    @chat_proto.on_message(ChatAcknowledgement)
    async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
        pass

    agent.include(chat_proto, publish_manifest=True)
    save_agent_address(runtime_dir, "commit", agent.address)
    return agent


def main():
    parser = argparse.ArgumentParser(description="Sentinel-Commit Agent")
    parser.add_argument("command", nargs="?", choices=["init", "check", "serve"], default="serve")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    root = args.root.resolve()
    runtime_dir = root / ".local" / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    if args.command == "init":
        seed_path = runtime_dir / "commit.seed"
        if not seed_path.exists():
            seed_path.write_text(secrets.token_urlsafe(48), encoding="utf-8")
        print("Commit agent identity initialized.")
        return

    settings = load_settings(root)
    if args.command == "check":
        print("Commit agent configuration valid.")
        return

    configure_logging()
    os.chdir(runtime_dir)
    seed = (
        settings.commit_seed.get_secret_value()
        if settings.commit_seed
        else (runtime_dir / "commit.seed").read_text().strip()
        if (runtime_dir / "commit.seed").exists()
        else secrets.token_urlsafe(48)
    )

    agent = build_commit_agent(
        root=root,
        seed=seed,
        port=settings.commit_port,
        mailbox=settings.mailbox,
        endpoint=settings.endpoint,
        github_token=settings.github_token.get_secret_value() if settings.github_token else None,
    )
    agent.run()


if __name__ == "__main__":
    main()
