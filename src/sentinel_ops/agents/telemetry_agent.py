"""Standalone Sentinel-Telemetry uAgent."""

import argparse
import json
import os
import secrets
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

from sentinel_ops.agents.telemetry_watchdog import TelemetryWatchdog
from sentinel_ops.discovery import save_agent_address
from sentinel_ops.logging import configure_logging
from sentinel_ops.protocols.health import (
    HealthCheckRequest,
    HealthCheckResponse,
    VerificationRequest,
    VerificationResponse,
    health_protocol,
)
from sentinel_ops.runtime import load_settings
from sentinel_ops.schemas import (
    HealthCheckRequest as SchemaHealthCheckRequest,
)
from sentinel_ops.schemas import (
    VerificationRequest as SchemaVerificationRequest,
)
from sentinel_ops.services.health_client import HttpHealthClient, PublicHealthClient


def build_telemetry_agent(
    root: Path | None = None,
    seed: str | None = None,
    port: int = 8001,
    mailbox: bool = True,
    endpoint: str | None = None,
    health_urls: set[str] | None = None,
    client=None,
) -> Agent:
    root = (root or Path.cwd()).resolve()
    runtime_dir = root / ".local" / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    if not seed:
        seed_file = runtime_dir / "telemetry.seed"
        if seed_file.exists():
            seed = seed_file.read_text(encoding="utf-8").strip()
        else:
            seed = secrets.token_urlsafe(48)
            seed_file.write_text(seed, encoding="utf-8")

    agent = Agent(
        name="Sentinel-Telemetry",
        seed=seed,
        port=port,
        mailbox=mailbox,
        endpoint=endpoint,
        readme_path=str(root / "docs" / "agent-profile-telemetry.md")
        if (root / "docs" / "agent-profile-telemetry.md").exists()
        else None,
        description="Health probes, latency monitoring, and recovery verification.",
    )

    if client is None:
        if health_urls:
            client = PublicHealthClient(health_urls)
        else:
            client = HttpHealthClient(allowed_urls=set(), public_targets=True)

    watchdog = TelemetryWatchdog(client)

    # 1. Internal Health Protocol
    @health_protocol.on_message(HealthCheckRequest)
    async def handle_health_check(ctx: Context, sender: str, msg: HealthCheckRequest):
        req = SchemaHealthCheckRequest(
            investigation_id=msg.investigation_id,
            endpoint=msg.endpoint,
            probes=msg.probes,
            timeout_seconds=msg.timeout if msg.timeout else msg.timeout_seconds,
        )
        res = await watchdog.run(req)
        await ctx.send(
            sender,
            HealthCheckResponse(
                investigation_id=str(res.investigation_id),
                agent_name="Sentinel-Telemetry",
                success=res.success,
                state=res.state,
                probes=[p.model_dump(mode="json") for p in res.probes],
                consecutive_failures=res.consecutive_failures,
                last_success=res.last_success.isoformat() if res.last_success else None,
                evidence=[e.model_dump(mode="json") for e in res.evidence],
                warnings=res.warnings,
                error=res.error.model_dump(mode="json") if res.error else None,
                started_at=res.started_at.isoformat(),
                completed_at=res.completed_at.isoformat(),
            ),
        )

    @health_protocol.on_message(VerificationRequest)
    async def handle_verification(ctx: Context, sender: str, msg: VerificationRequest):
        req = SchemaVerificationRequest(
            investigation_id=msg.investigation_id,
            endpoint=msg.endpoint,
            probes=msg.probes,
            timeout_seconds=msg.timeout if msg.timeout else msg.timeout_seconds,
        )
        res = await watchdog.run(req)
        await ctx.send(
            sender,
            VerificationResponse(
                investigation_id=str(res.investigation_id),
                agent_name="Sentinel-Telemetry",
                success=res.success,
                state=res.state,
                probes=[p.model_dump(mode="json") for p in res.probes],
                consecutive_failures=res.consecutive_failures,
                last_success=res.last_success.isoformat() if res.last_success else None,
                evidence=[e.model_dump(mode="json") for e in res.evidence],
                warnings=res.warnings,
                error=res.error.model_dump(mode="json") if res.error else None,
                started_at=res.started_at.isoformat(),
                completed_at=res.completed_at.isoformat(),
            ),
        )

    agent.include(health_protocol)

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
        endpoint_val = data.get("endpoint") or (
            text if text.startswith("http://") or text.startswith("https://") else ""
        )

        if "verify" in action.lower() or "verify" in text.lower():
            if not endpoint_val:
                reply = "Please specify an endpoint URL to verify: e.g. {'action': 'verify', 'endpoint': 'https://example.com/health'}"
            else:
                req = SchemaVerificationRequest(endpoint=endpoint_val)
                res = await watchdog.run(req)
                reply = f"Verification State: {res.state}. Probes: {len(res.probes)}, Success: {res.success}."
        elif endpoint_val or "probe" in text.lower() or "investigate" in text.lower():
            if not endpoint_val:
                reply = "Please specify an endpoint URL to investigate: e.g. {'action': 'investigate', 'endpoint': 'https://example.com/health'}"
            else:
                req = SchemaHealthCheckRequest(endpoint=endpoint_val)
                res = await watchdog.run(req)
                reply = f"Health State: {res.state}. Consecutive failures: {res.consecutive_failures}, Probes: {len(res.probes)}."
        else:
            reply = (
                "Sentinel-Telemetry Agent: Health probes and verification.\n"
                "Commands:\n"
                "- Send an endpoint URL or {'action': 'investigate', 'endpoint': '<url>'}\n"
                "- Send {'action': 'verify', 'endpoint': '<url>'}"
            )

        await ctx.send(sender, ChatMessage(content=[TextContent(type="text", text=reply)]))

    @chat_proto.on_message(ChatAcknowledgement)
    async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
        pass

    agent.include(chat_proto, publish_manifest=True)
    save_agent_address(runtime_dir, "telemetry", agent.address)
    return agent


def main():
    parser = argparse.ArgumentParser(description="Sentinel-Telemetry Agent")
    parser.add_argument("command", nargs="?", choices=["init", "check", "serve"], default="serve")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    root = args.root.resolve()
    runtime_dir = root / ".local" / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    if args.command == "init":
        seed_path = runtime_dir / "telemetry.seed"
        if not seed_path.exists():
            seed_path.write_text(secrets.token_urlsafe(48), encoding="utf-8")
        print("Telemetry agent identity initialized.")
        return

    settings = load_settings(root)
    if args.command == "check":
        print("Telemetry agent configuration valid.")
        return

    configure_logging()
    os.chdir(runtime_dir)
    seed = (
        settings.telemetry_seed.get_secret_value()
        if settings.telemetry_seed
        else (runtime_dir / "telemetry.seed").read_text().strip()
        if (runtime_dir / "telemetry.seed").exists()
        else secrets.token_urlsafe(48)
    )

    agent = build_telemetry_agent(
        root=root,
        seed=seed,
        port=settings.telemetry_port,
        mailbox=settings.mailbox,
        endpoint=settings.endpoint,
        health_urls=settings.health_urls,
    )
    agent.run()


if __name__ == "__main__":
    main()
