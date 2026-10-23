"""Transport-neutral typed contracts. ACP envelopes are adapted separately."""

from datetime import datetime, timezone
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utc(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("Timezone-aware timestamp required")
    return value.astimezone(timezone.utc)


UTC = Annotated[datetime, BeforeValidator(utc)]
Repository = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")]


def safe_path(path: str) -> str:
    parts = PurePosixPath(path).parts
    if (
        not path
        or "\\" in path
        or ":" in path
        or path.startswith("/")
        or any(p in {"..", ".git", ".env"} for p in parts)
        or any(p.endswith((".", " ")) for p in parts)
        or path != str(PurePosixPath(path))
    ):
        raise ValueError("Unsafe repository path")
    return path


SafePath = Annotated[str, BeforeValidator(safe_path)]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Status(StrEnum):
    CREATED = "created"
    COLLECTING = "collecting_evidence"
    AWAITING = "awaiting_confirmation"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    RESOLVED = "resolved"
    PARTIAL = "partially_resolved"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentError(Model):
    code: str
    message: str
    retryable: bool = False


class Message(Model):
    investigation_id: UUID = Field(default_factory=uuid4)


class InvestigationRequest(Message):
    repository: Repository
    branch: str = Field(min_length=1, max_length=200)
    endpoint: str = Field(min_length=1, max_length=2048)
    lookback_hours: int = Field(default=24, ge=1, le=168)
    permission: Literal["read_only", "create_pr"] = "read_only"
    incident_at: UTC = Field(default_factory=utcnow)


class InvestigationContext(InvestigationRequest):
    status: Status = Status.CREATED
    session_id: str = Field(min_length=1)


class Evidence(Model):
    id: str
    source: str
    summary: str
    simulated: bool = True


class Response(Message):
    agent_name: str
    success: bool = True
    started_at: UTC = Field(default_factory=utcnow)
    completed_at: UTC = Field(default_factory=utcnow)
    evidence: list[Evidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: AgentError | None = None

    @model_validator(mode="after")
    def consistent(self):
        if self.completed_at < self.started_at:
            raise ValueError("Completion precedes start")
        if self.success == (self.error is not None):
            raise ValueError("Failed responses require an error; success forbids one")
        return self


class HealthCheckRequest(Message):
    endpoint: str
    probes: int = Field(default=2, ge=1, le=5)
    timeout_seconds: float = Field(default=3, gt=0, le=10)


class Probe(Model):
    timestamp: UTC = Field(default_factory=utcnow)
    status: int | None = None
    latency_ms: float = Field(default=0, ge=0)
    failure: (
        Literal["http", "timeout", "dns", "tls", "connection", "unsafe_url", "redirect"] | None
    ) = None
    excerpt: str = ""


class HealthCheckResponse(Response):
    agent_name: str = "Telemetry-Watchdog"
    state: Literal["healthy", "degraded", "failing", "unknown"] = "unknown"
    probes: list[Probe] = Field(default_factory=list)
    consecutive_failures: int = 0
    last_success: UTC | None = None


class CommitAnalysisRequest(Message):
    repository: Repository
    branch: str
    incident_at: UTC = Field(default_factory=utcnow)
    lookback_hours: int = Field(default=24, ge=1, le=168)
    max_commits: int = Field(default=20, ge=1, le=50)
    max_diff_bytes: int = Field(default=8192, ge=128, le=32768)
    service_hint: str = "health"


class Commit(Model):
    sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    timestamp: UTC
    message: str
    files: dict[SafePath, str]
    url: str
    score: float = Field(default=0, ge=0, le=1)
    explanation: str = "Unranked"


class CommitAnalysisResponse(Response):
    agent_name: str = "Commit-Detective"
    commits: list[Commit] = Field(default_factory=list)


class SecurityScanRequest(Message):
    files: dict[SafePath, str]
    incident_files: list[SafePath] = Field(default_factory=list)


class Dependency(Model):
    ecosystem: str
    name: str
    version: str
    file: str


class Finding(Model):
    id: str
    kind: Literal["dependency", "code"]
    severity: Literal["critical", "high", "medium", "low", "info"]
    confidence: float = Field(ge=0, le=1)
    file: str
    line: int = Field(default=1, ge=1)
    evidence: str
    remediation: str
    fixed_versions: list[str] = Field(default_factory=list)
    related_to_incident: bool = False
    aliases: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)


class SecurityScanResponse(Response):
    agent_name: str = "Security-Investigator"
    findings: list[Finding] = Field(default_factory=list)
    risk_score: float = Field(default=0, ge=0, le=10)


class IncidentHypothesis(Model):
    summary: str
    confidence: Literal["high", "medium", "low", "insufficient_evidence"]
    evidence_ids: list[str]
    commit_sha: str | None = None


class RemediationProposal(Message):
    proposal_id: UUID = Field(default_factory=uuid4)
    repository: Repository
    base_branch: str
    action: Literal["revert_commit", "apply_patch"]
    commit_sha: str | None = None
    expected_files: list[SafePath] = Field(min_length=1, max_length=20)
    replacements: dict[SafePath, str] = Field(default_factory=dict)
    expected_hashes: dict[SafePath, str] = Field(default_factory=dict)
    evidence: list[Evidence]
    confidence: str
    tests: list[str] = Field(default_factory=lambda: ["local health probe"])
    risks: list[str] = Field(default_factory=lambda: ["Sandbox simulation only"])


class RemediationExecutionRequest(Message):
    proposal_id: UUID
    session_id: str
    confirmation: str
    idempotency_key: str


class RemediationExecutionResponse(Response):
    agent_name: str = "Remediation-Executor"
    pr_number: int | None = None
    pr_url: str | None = None
    validation: str = "not_run"
    simulated: Literal[True] = True


class VerificationRequest(HealthCheckRequest):
    pass


class VerificationResponse(HealthCheckResponse):
    agent_name: str = "Recovery-Verifier"
