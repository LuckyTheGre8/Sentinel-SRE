"""High-level orchestration protocol for multi-agent workflows."""

from typing import Any

from uagents import Model, Protocol


class InvestigationRequest(Model):
    investigation_id: str = ""
    repository: str
    branch: str = "main"
    endpoint: str = ""
    lookback_hours: int = 24
    permission: str = "read_only"
    incident_at: str = ""


class IncidentReport(Model):
    investigation_id: str = ""
    health: dict[str, Any] = {}
    commits: dict[str, Any] = {}
    security: dict[str, Any] = {}
    hypothesis: dict[str, Any] = {}
    warnings: list[str] = []


orchestration_protocol = Protocol(name="SentinelOrchestration", version="1.0.0")
