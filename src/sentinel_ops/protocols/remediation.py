"""Remediation proposal and PR execution protocol."""

from typing import Any

from uagents import Model, Protocol


class RemediationProposalRequest(Model):
    investigation_id: str = ""
    session_id: str = ""
    repository: str = ""
    base_branch: str = "main"
    action: str = "revert_commit"
    commit_sha: str | None = None
    replacements: dict[str, str] = {}
    confidence: str = "medium"
    evidence: list[dict[str, Any]] = []
    report_json: str | None = None


class RemediationProposalResponse(Model):
    simulated: bool = True
    investigation_id: str = ""
    proposal_id: str = ""
    nonce: str = ""
    key: str = ""
    proposal_data: dict[str, Any] = {}
    success: bool = True
    error: dict[str, Any] | None = None


class RemediationExecutionRequest(Model):
    investigation_id: str = ""
    proposal_id: str = ""
    session_id: str = ""
    confirmation: str = ""
    idempotency_key: str = ""


class RemediationExecutionResponse(Model):
    investigation_id: str = ""
    agent_name: str = "Sentinel-Remediation"
    success: bool = True
    pr_number: int | None = None
    pr_url: str | None = None
    validation: str = "not_run"
    simulated: bool = True
    warnings: list[str] = []
    evidence: list[dict[str, Any]] = []
    error: dict[str, Any] | None = None


remediation_protocol = Protocol(name="SentinelRemediation", version="1.0.0")
