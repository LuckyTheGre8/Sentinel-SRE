"""Security vulnerability and code scan protocol."""

from typing import Any

from uagents import Model, Protocol


class SecurityScanRequest(Model):
    investigation_id: str = ""
    files: dict[str, str] = {}
    incident_files: list[str] = []
    repository: str = ""


class SecurityScanResponse(Model):
    investigation_id: str = ""
    agent_name: str = "Sentinel-Security"
    success: bool = True
    findings: list[dict[str, Any]] = []
    risk_score: float = 0.0
    evidence: list[dict[str, Any]] = []
    warnings: list[str] = []
    error: dict[str, Any] | None = None
    started_at: str = ""
    completed_at: str = ""


security_protocol = Protocol(name="SentinelSecurity", version="1.0.0")
