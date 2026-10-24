"""Standalone Sentinel-Security uAgent."""

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

from sentinel_ops.agents.security_investigator import SecurityInvestigator
from sentinel_ops.discovery import save_agent_address
from sentinel_ops.logging import configure_logging
from sentinel_ops.protocols.security import (
    SecurityScanRequest,
    SecurityScanResponse,
    security_protocol,
)
from sentinel_ops.runtime import load_settings
from sentinel_ops.schemas import (
    SecurityScanRequest as SchemaSecurityScanRequest,
)
from sentinel_ops.services.osv_client import LiveOSVClient


def build_security_agent(
    root: Path | None = None,
    seed: str | None = None,
    port: int = 8003,
    mailbox: bool = True,
    endpoint: str | None = None,
    client=None,
) -> Agent:
    root = (root or Path.cwd()).resolve()
    runtime_dir = root / ".local" / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    if not seed:
        seed_file = runtime_dir / "security.seed"
        if seed_file.exists():
            seed = seed_file.read_text(encoding="utf-8").strip()
        else:
            seed = secrets.token_urlsafe(48)
            seed_file.write_text(seed, encoding="utf-8")

    agent = Agent(
        name="Sentinel-Security",
        seed=seed,
        port=port,
        mailbox=mailbox,
        endpoint=endpoint,
        readme_path=str(root / "docs" / "agent-profile-security.md")
        if (root / "docs" / "agent-profile-security.md").exists()
        else None,
        description="OSV vulnerability scanning, manifest dependency analysis, and SAST.",
    )

    if client is None:
        client = LiveOSVClient()

    investigator = SecurityInvestigator(client=client, timeout=30)

    # 1. Internal Security Protocol
    @security_protocol.on_message(SecurityScanRequest)
    async def handle_security_scan(ctx: Context, sender: str, msg: SecurityScanRequest):
        req = SchemaSecurityScanRequest(
            investigation_id=msg.investigation_id,
            files=msg.files,
            incident_files=msg.incident_files,
        )
        res = await investigator.run(req)

        await ctx.send(
            sender,
            SecurityScanResponse(
                investigation_id=str(res.investigation_id),
                agent_name="Sentinel-Security",
                success=res.success,
                findings=[f.model_dump(mode="json") for f in res.findings],
                risk_score=res.risk_score,
                evidence=[e.model_dump(mode="json") for e in res.evidence],
                warnings=res.warnings,
                error=res.error.model_dump(mode="json") if res.error else None,
                started_at=res.started_at.isoformat(),
                completed_at=res.completed_at.isoformat(),
            ),
        )

    agent.include(security_protocol)

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
        files = data.get("files", {})

        if "scan" in action.lower() or "vulnerabilit" in text.lower() or files:
            if not files:
                reply = "Please specify files/manifests to scan: e.g. {'action': 'scan_dependencies', 'files': {'requirements.txt': 'demo-pkg==1.0.0'}}"
            else:
                try:
                    req = SchemaSecurityScanRequest(files=files)
                    res = await investigator.run(req)
                    findings_summary = (
                        f"Found {len(res.findings)} issue(s). Risk score: {res.risk_score}."
                    )
                    if res.findings:
                        top = res.findings[0]
                        findings_summary += f"\nTop finding: {top.id} ({top.severity.upper()}) in {top.file}: {top.remediation}"
                    reply = findings_summary
                except Exception as err:
                    reply = f"Security scan failed: {err}"
        else:
            reply = (
                "Sentinel-Security Agent: OSV vulnerability scanning and SAST.\n"
                "Commands:\n"
                "- Send {'action': 'scan_dependencies', 'files': {'requirements.txt': 'pkg==version'}}\n"
                "- Include manifest files to scan for CVEs and advisories."
            )

        await ctx.send(sender, ChatMessage(content=[TextContent(type="text", text=reply)]))

    @chat_proto.on_message(ChatAcknowledgement)
    async def handle_ack(ctx: Context, sender: str, msg: ChatAcknowledgement):
        pass

    agent.include(chat_proto, publish_manifest=True)
    save_agent_address(runtime_dir, "security", agent.address)
    return agent


def main():
    parser = argparse.ArgumentParser(description="Sentinel-Security Agent")
    parser.add_argument("command", nargs="?", choices=["init", "check", "serve"], default="serve")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    root = args.root.resolve()
    runtime_dir = root / ".local" / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    if args.command == "init":
        seed_path = runtime_dir / "security.seed"
        if not seed_path.exists():
            seed_path.write_text(secrets.token_urlsafe(48), encoding="utf-8")
        print("Security agent identity initialized.")
        return

    settings = load_settings(root)
    if args.command == "check":
        print("Security agent configuration valid.")
        return

    configure_logging()
    os.chdir(runtime_dir)
    seed = (
        settings.security_seed.get_secret_value()
        if settings.security_seed
        else (runtime_dir / "security.seed").read_text().strip()
        if (runtime_dir / "security.seed").exists()
        else secrets.token_urlsafe(48)
    )

    agent = build_security_agent(
        root=root,
        seed=seed,
        port=settings.security_port,
        mailbox=settings.mailbox,
        endpoint=settings.endpoint,
    )
    agent.run()


if __name__ == "__main__":
    main()
