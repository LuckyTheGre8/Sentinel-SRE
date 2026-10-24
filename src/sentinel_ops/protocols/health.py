"""Health probe and verification protocols."""

from typing import Any

from uagents import Model, Protocol


class HealthCheckRequest(Model):
    investigation_id: str = ""
    endpoint: str
    probes: int = 2
    timeout: float = 3.0
    timeout_seconds: float = 3.0


class VerificationRequest(Model):
    investigation_id: str = ""
    endpoint: str
    probes: int = 2
    timeout: float = 3.0
    timeout_seconds: float = 3.0


class HealthCheckResponse(Model):
    investigation_id: str = ""
    agent_name: str = "Sentinel-Telemetry"
    success: bool = True
    state: str = "unknown"
    probes: list[dict[str, Any]] = []
    consecutive_failures: int = 0
    last_success: str | None = None
    evidence: list[dict[str, Any]] = []
    warnings: list[str] = []
    error: dict[str, Any] | None = None
    started_at: str = ""
    completed_at: str = ""


class VerificationResponse(HealthCheckResponse):
    agent_name: str = "Sentinel-Telemetry"


health_protocol = Protocol(name="SentinelHealth", version="1.0.0")
