"""Local typed worker dispatch with deadlines, one retry, and evidence validation."""

import asyncio
import random
import time
from collections.abc import Callable

from sentinel_ops.schemas import (
    AgentError,
    CommitAnalysisRequest,
    CommitAnalysisResponse,
    HealthCheckRequest,
    HealthCheckResponse,
    IncidentHypothesis,
    InvestigationContext,
    Model,
    SecurityScanRequest,
    SecurityScanResponse,
    Status,
)
from sentinel_ops.services.reasoning import ReasoningClient
from sentinel_ops.state import StateStore


class IncidentReport(Model):
    health: HealthCheckResponse
    commits: CommitAnalysisResponse
    security: SecurityScanResponse
    hypothesis: IncidentHypothesis
    warnings: list[str]


class LocalWorkerTransport:
    """Serialization boundary shared by the local agent simulator and tests."""

    def __init__(self, timeout: float = 10):
        self.timeout = timeout
        self.cooldowns: dict[str, float] = {}

    async def dispatch(self, name: str, handler: Callable, request, response_type):
        if self.cooldowns.get(name, 0) > time.monotonic():
            return response_type(
                investigation_id=request.investigation_id,
                success=False,
                error=AgentError(code="cooldown", message="Worker temporarily unavailable"),
            )
        for attempt in range(2):
            try:
                wire_request = type(request).model_validate_json(request.model_dump_json())
                result = await asyncio.wait_for(handler(wire_request), timeout=self.timeout)
                response = response_type.model_validate_json(result.model_dump_json())
                if response.investigation_id != request.investigation_id:
                    raise ValueError("Worker correlation mismatch")
                if not response.success and response.error.retryable and attempt == 0:
                    await asyncio.sleep(0.01 + random.random() * 0.01)
                    continue
                return response
            except (TimeoutError, OSError):
                if attempt == 0:
                    await asyncio.sleep(0.01 + random.random() * 0.01)
                    continue
                self.cooldowns[name] = time.monotonic() + 1
                return response_type(
                    investigation_id=request.investigation_id,
                    success=False,
                    error=AgentError(
                        code="worker_timeout",
                        message="Worker unavailable after bounded retry",
                        retryable=True,
                    ),
                )
            except Exception:
                return response_type(
                    investigation_id=request.investigation_id,
                    success=False,
                    error=AgentError(
                        code="invalid_worker_response",
                        message="Worker failed contract/correlation checks",
                    ),
                )


class SentinelOrchestrator:
    def __init__(
        self,
        store: StateStore,
        telemetry,
        commits,
        security,
        reasoning: ReasoningClient,
        transport: LocalWorkerTransport | None = None,
    ):
        self.store = store
        self.telemetry = telemetry
        self.commits = commits
        self.security = security
        self.reasoning = reasoning
        self.transport = transport or LocalWorkerTransport()

    async def investigate(self, context: InvestigationContext) -> IncidentReport:
        self.store.transition(context.investigation_id, Status.COLLECTING)
        health, commits = await asyncio.gather(
            self.transport.dispatch(
                "health",
                self.telemetry.run,
                HealthCheckRequest(
                    investigation_id=context.investigation_id, endpoint=context.endpoint
                ),
                HealthCheckResponse,
            ),
            self.transport.dispatch(
                "commits",
                self.commits.run,
                CommitAnalysisRequest(
                    investigation_id=context.investigation_id,
                    repository=context.repository,
                    branch=context.branch,
                    incident_at=context.incident_at,
                    lookback_hours=context.lookback_hours,
                ),
                CommitAnalysisResponse,
            ),
        )
        if commits.success and commits.commits:
            try:
                files = await asyncio.wait_for(
                    self.commits.client.files(context.repository, commits.commits[0].sha), 3
                )
                security = await self.transport.dispatch(
                    "security",
                    self.security.run,
                    SecurityScanRequest(
                        investigation_id=context.investigation_id,
                        files=files,
                        incident_files=list(commits.commits[0].files),
                    ),
                    SecurityScanResponse,
                )
            except (TimeoutError, ValueError, OSError):
                security = SecurityScanResponse(
                    investigation_id=context.investigation_id,
                    success=False,
                    error=AgentError(
                        code="files_unavailable", message="Security input unavailable"
                    ),
                )
        else:
            security = SecurityScanResponse(
                investigation_id=context.investigation_id,
                success=False,
                error=AgentError(
                    code="no_commit_evidence", message="Security scan lacks relevant revision"
                ),
            )
        hypothesis = await asyncio.wait_for(self.reasoning.synthesize(health, commits), 3)
        allowed = {e.id for r in (health, commits, security) for e in r.evidence}
        if not set(hypothesis.evidence_ids) <= allowed:
            hypothesis = IncidentHypothesis(
                summary="Reasoning output rejected: unsupported evidence references",
                confidence="insufficient_evidence",
                evidence_ids=[],
            )
        warnings = [w for r in (health, commits, security) for w in r.warnings]
        warnings.extend(r.error.message for r in (health, commits, security) if r.error)
        if health.state == "healthy" and commits.commits and commits.commits[0].score > 0.5:
            warnings.append(
                "Conflicting evidence: endpoint healthy despite suspicious recorded commit"
            )
        if health.state == "unknown":
            warnings.append("Live health unavailable; diagnosis cannot establish an outage")
        report = IncidentReport(
            health=health,
            commits=commits,
            security=security,
            hypothesis=hypothesis,
            warnings=warnings,
        )
        self.store.put("report", str(context.investigation_id), report.model_dump_json())
        self.store.transition(context.investigation_id, Status.AWAITING)
        return report
