"""Live uAgent entry point. Import/check never registers or starts an agent."""

import argparse
import asyncio
import json
import os
import secrets
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from sentinel_ops.acp import ChatGateway, build_protocol, text_message
from sentinel_ops.agents.commit_detective import CommitDetective
from sentinel_ops.agents.orchestrator import LocalWorkerTransport, SentinelOrchestrator
from sentinel_ops.agents.security_investigator import SecurityInvestigator
from sentinel_ops.agents.telemetry_watchdog import TelemetryWatchdog
from sentinel_ops.logging import configure_logging
from sentinel_ops.services.asi1_client import ASI1ReasoningClient
from sentinel_ops.services.github_client import LiveGitHubClient
from sentinel_ops.services.health_client import PublicHealthClient, validate_url
from sentinel_ops.services.osv_client import LiveOSVClient
from sentinel_ops.state import StateStore


class RuntimeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asi1_api_key: SecretStr = Field(min_length=1)
    agent_seed: SecretStr = Field(min_length=32)
    data_sharing: bool = False
    github_token: SecretStr | None = None
    repositories: set[str] = Field(default_factory=set)
    allowed_senders: set[str] = Field(default_factory=set)
    health_urls: set[str] = Field(default_factory=set)
    model: str = "asi1-mini"
    mailbox: bool = True
    endpoint: str | None = None
    port: int = Field(default=8001, ge=1024, le=65535)
    pr_writes: bool = False

    @model_validator(mode="after")
    def validate_scope(self):
        if not self.data_sharing:
            raise ValueError(
                "Set ASI1_DATA_SHARING=true to permit redacted intent and evidence statistics"
            )
        if self.github_token and (not self.repositories or not self.allowed_senders):
            raise ValueError("Authenticated GitHub requires repository and sender allowlists")
        if self.pr_writes and not self.github_token:
            raise ValueError("GITHUB_PR_WRITES requires a scoped GitHub token")
        if self.model not in {"asi1", "asi1-mini", "asi1-ultra"}:
            raise ValueError("Unsupported ASI model")
        for repository in self.repositories:
            LiveGitHubClient._repository(repository)
        for url in self.health_urls:
            validate_url(url)
            if not url.startswith("https://"):
                raise ValueError("Live health targets require HTTPS")
        if not self.mailbox:
            if not self.endpoint:
                raise ValueError("An HTTPS endpoint is required without mailbox")
            validate_url(self.endpoint)
            if not self.endpoint.startswith("https://"):
                raise ValueError("Agent endpoint requires HTTPS")
        return self


def environment(root: Path) -> dict[str, str]:
    values = {}
    path = root / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            key, separator, value = line.partition("=")
            if not separator or not key.strip().replace("_", "").isalnum():
                raise ValueError("Invalid .env entry")
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            values[key.strip()] = value
    return {**values, **os.environ}


def load_settings(root: Path) -> RuntimeSettings:
    env = environment(root)
    seed_path = root / ".local" / "runtime" / "agent.seed"
    seed = env.get("ORCHESTRATOR_SEED") or (
        seed_path.read_text().strip() if seed_path.exists() else ""
    )
    return RuntimeSettings(
        asi1_api_key=SecretStr(env.get("ASI1_API_KEY") or env.get("ASI_ONE_API_KEY", "")),
        agent_seed=SecretStr(seed),
        github_token=SecretStr(env["GITHUB_TOKEN"]) if env.get("GITHUB_TOKEN") else None,
        data_sharing=env.get("ASI1_DATA_SHARING", "").lower() == "true",
        repositories=set(
            filter(None, (v.strip() for v in env.get("SENTINEL_REPOSITORIES", "").split(",")))
        ),
        allowed_senders=set(
            filter(None, (v.strip() for v in env.get("SENTINEL_SENDERS", "").split(",")))
        ),
        health_urls=set(
            filter(None, (v.strip() for v in env.get("SENTINEL_HEALTH_URLS", "").split(",")))
        ),
        model=env.get("ASI1_MODEL") or "asi1-mini",
        mailbox=env.get("AGENT_MAILBOX", "true").lower() == "true",
        endpoint=env.get("AGENT_ENDPOINT") or None,
        port=int(env.get("AGENT_PORT") or "8001"),
        pr_writes=env.get("GITHUB_PR_WRITES", "").lower() == "true",
    )


class LiveGateway(ChatGateway):
    simulated = False
    remediation_enabled = False
    patch_enabled = False

    def __init__(self, orchestrator, settings):
        super().__init__(orchestrator)
        self.settings = settings
        self.lock = asyncio.Lock()
        self.executor = None
        if settings.pr_writes:
            from sentinel_ops.services.github_remediation import (
                GitHubRemediationClient,
                LiveRemediationExecutor,
            )

            self.executor = LiveRemediationExecutor(
                self.store,
                GitHubRemediationClient(
                    settings.github_token.get_secret_value(), settings.repositories
                ),
            )
            self.remediation_enabled = True

    def validate_intake(self, data):
        if data.get("permission", "read_only") != "read_only" and not self.remediation_enabled:
            raise ValueError(
                "Live repository writes require a separately configured remediation backend"
            )
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
        if "endpoint" in data:
            validate_url(data["endpoint"])
            from urllib.parse import urlsplit

            parsed = urlsplit(data["endpoint"])
            if parsed.scheme != "https" or parsed.port not in {None, 443}:
                raise ValueError("Live endpoint must use standard HTTPS")

    async def handle(self, sender, session, message):
        from uagents_core.contrib.protocols.chat import ChatAcknowledgement

        if self.settings.allowed_senders and sender not in self.settings.allowed_senders:
            return [
                ChatAcknowledgement(acknowledged_msg_id=message.msg_id),
                text_message("Sender not authorized"),
            ]
        async with self.lock:
            return await super().handle(sender, session, message)

    async def action(self, owner, action, data):
        from uuid import UUID

        from sentinel_ops import cards
        from sentinel_ops.agents.orchestrator import IncidentReport
        from sentinel_ops.schemas import RemediationExecutionRequest, Status, VerificationRequest

        current = self.store.read("session", owner)
        if action == "review_revert" and current and self.executor:
            report = IncidentReport.model_validate_json(self.store.read("report", current))
            proposal, nonce, key = await self.executor.propose_revert(UUID(current), owner, report)
            return [cards.confirmation(proposal, nonce, key, simulated=False)]
        if action == "confirm" and current and self.executor:
            request = RemediationExecutionRequest.model_validate({**data, "session_id": owner})
            if str(request.investigation_id) != current:
                raise ValueError("Session investigation mismatch")
            result = await self.executor.execute(request)
            return [
                text_message(
                    result.model_dump_json()
                    + '\nAfter manually merging/deploying, send {"action":"verify"} to check recovery.'
                )
            ]
        if action == "verify" and current:
            context = self.store.get(UUID(current))
            if context.status != Status.VERIFYING:
                raise ValueError("No confirmed remediation awaiting verification")
            result = await self.orchestrator.telemetry.run(
                VerificationRequest(
                    investigation_id=context.investigation_id, endpoint=context.endpoint
                )
            )
            if result.state == "healthy":
                self.store.transition(context.investigation_id, Status.RESOLVED)
            return [text_message(result.model_dump_json())]
        return await super().action(owner, action, data)


def make_gateway(store: StateStore, settings: RuntimeSettings) -> LiveGateway:
    orchestrator = SentinelOrchestrator(
        store,
        TelemetryWatchdog(PublicHealthClient(settings.health_urls)),
        CommitDetective(
            LiveGitHubClient(
                token=settings.github_token.get_secret_value() if settings.github_token else None
            ),
            timeout=30,
        ),
        SecurityInvestigator(LiveOSVClient(), timeout=30),
        ASI1ReasoningClient(
            settings.asi1_api_key.get_secret_value(),
            data_sharing=settings.data_sharing,
            model=settings.model,
        ),
        transport=LocalWorkerTransport(timeout=45),
        provider_timeout=30,
    )
    return LiveGateway(orchestrator, settings)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["init", "check", "serve"])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.root.resolve()
    runtime_dir = root / ".local" / "runtime"
    if args.command == "init":
        runtime_dir.mkdir(parents=True, exist_ok=True)
        seed_path = runtime_dir / "agent.seed"
        if not seed_path.exists():
            with seed_path.open("x", encoding="utf-8") as stream:
                stream.write(secrets.token_urlsafe(48))
        print("Local agent identity initialized; secret value not displayed.")
        return
    try:
        settings = load_settings(root)
    except (ValueError, OSError):
        raise SystemExit(
            "Configuration incomplete or invalid. See docs/live-deployment.md; no values displayed."
        ) from None
    if args.command == "check":
        print("Live configuration valid; no services contacted.")
        return
    # Keep SDK-generated state inside the ignored runtime directory.
    runtime_dir.mkdir(parents=True, exist_ok=True)
    os.chdir(runtime_dir)
    configure_logging()
    from uagents import Agent

    store = StateStore(runtime_dir / "investigations.sqlite")
    gateway = make_gateway(store, settings)
    agent = Agent(
        name="Sentinel-Orchestrator",
        seed=settings.agent_seed.get_secret_value(),
        port=settings.port,
        mailbox=settings.mailbox,
        endpoint=settings.endpoint,
        readme_path=str(root / "docs" / "agent-profile.md"),
        description="Investigate endpoint failures with live GitHub and vulnerability evidence.",
        store_message_history=False,
    )
    agent.include(build_protocol(gateway), publish_manifest=True)
    (runtime_dir / "public-agent.json").write_text(
        json.dumps({"name": agent.name, "address": agent.address})
    )
    try:
        agent.run()
    finally:
        store.close()


if __name__ == "__main__":
    main()
