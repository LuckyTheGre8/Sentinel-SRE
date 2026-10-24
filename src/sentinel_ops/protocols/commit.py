"""Commit analysis protocol."""

from typing import Any

from uagents import Model, Protocol


class CommitAnalysisRequest(Model):
    investigation_id: str = ""
    repository: str
    branch: str = "main"
    incident_at: str = ""
    lookback_hours: int = 24
    max_commits: int = 20
    max_diff_bytes: int = 8192
    service_hint: str = "health"


class CommitAnalysisResponse(Model):
    investigation_id: str = ""
    agent_name: str = "Sentinel-Commit"
    success: bool = True
    commits: list[dict[str, Any]] = []
    files: dict[str, str] = {}
    evidence: list[dict[str, Any]] = []
    warnings: list[str] = []
    error: dict[str, Any] | None = None
    started_at: str = ""
    completed_at: str = ""


commit_protocol = Protocol(name="SentinelCommit", version="1.0.0")
