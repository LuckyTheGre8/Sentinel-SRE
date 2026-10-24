"""Local typed worker dispatch with deadlines, one retry, and evidence validation."""

import asyncio
import random
import time
from collections.abc import Callable
from typing import Any

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


class NetworkWorkerTransport:
    """Network transport dispatching requests to uAgents over native protocols."""

    def __init__(
        self,
        peer_addresses: dict[str, str] | None = None,
        send_fn: Callable[[str, Any], Any] | None = None,
        timeout: float = 45.0,
    ):
        self.peer_addresses = {}
        self.set_peer_addresses(peer_addresses or {})
        self.send_fn = send_fn
        self.timeout = timeout
        self.cooldowns: dict[str, float] = {}
        self.pending: dict[tuple[str, str], asyncio.Future] = {}
        self.last_commit_files: dict[str, dict[str, str]] = {}

    def set_sender(self, send_fn: Callable[[str, Any], Any]):
        self.send_fn = send_fn

    def set_peer_addresses(self, peer_addresses: dict[str, str]):
        self.peer_addresses.update(peer_addresses)
        for source, channel in (("telemetry", "health"), ("commit", "commits")):
            if source in peer_addresses:
                self.peer_addresses[channel] = peer_addresses[source]

    def handle_response(self, channel: str, investigation_id: str, msg: Any) -> bool:
        key = (channel, str(investigation_id))
        future = self.pending.get(key)
        if future and not future.done():
            future.set_result(msg)
            return True
        return False

    def _to_proto_message(self, name: str, request: Any) -> Any:
        from sentinel_ops.protocols.commit import CommitAnalysisRequest as ProtoCommitReq
        from sentinel_ops.protocols.health import HealthCheckRequest as ProtoHealthReq
        from sentinel_ops.protocols.health import VerificationRequest as ProtoVerifyReq
        from sentinel_ops.protocols.remediation import (
            RemediationExecutionRequest as ProtoRemedExecReq,
        )
        from sentinel_ops.protocols.remediation import (
            RemediationProposalRequest as ProtoRemedPropReq,
        )
        from sentinel_ops.protocols.security import SecurityScanRequest as ProtoSecReq
        from sentinel_ops.schemas import VerificationRequest

        if name == "health":
            model = ProtoVerifyReq if isinstance(request, VerificationRequest) else ProtoHealthReq
            return model(
                investigation_id=str(request.investigation_id),
                endpoint=getattr(request, "endpoint", ""),
                probes=getattr(request, "probes", 2),
                timeout=getattr(request, "timeout_seconds", 3.0),
                timeout_seconds=getattr(request, "timeout_seconds", 3.0),
            )
        elif name == "commits":
            inc_at = getattr(request, "incident_at", None)
            inc_at_str = inc_at.isoformat() if inc_at else ""
            return ProtoCommitReq(
                investigation_id=str(request.investigation_id),
                repository=getattr(request, "repository", ""),
                branch=getattr(request, "branch", "main"),
                incident_at=inc_at_str,
                lookback_hours=getattr(request, "lookback_hours", 24),
                max_commits=getattr(request, "max_commits", 20),
                max_diff_bytes=getattr(request, "max_diff_bytes", 8192),
                service_hint=getattr(request, "service_hint", "health"),
            )
        elif name == "security":
            return ProtoSecReq(
                investigation_id=str(request.investigation_id),
                files=dict(getattr(request, "files", {})),
                incident_files=[str(f) for f in getattr(request, "incident_files", [])],
            )
        elif name == "remediation_proposal":
            return ProtoRemedPropReq(
                investigation_id=str(getattr(request, "investigation_id", "")),
                session_id=str(getattr(request, "session_id", "")),
                repository=str(getattr(request, "repository", "")),
                base_branch=str(getattr(request, "base_branch", "main")),
                action=str(getattr(request, "action", "revert_commit")),
                commit_sha=getattr(request, "commit_sha", None),
                confidence=str(getattr(request, "confidence", "medium")),
                evidence=[
                    e.model_dump(mode="json") if hasattr(e, "model_dump") else e
                    for e in getattr(request, "evidence", [])
                ],
                report_json=getattr(request, "report_json", None),
            )
        elif name == "remediation_exec":
            return ProtoRemedExecReq(
                investigation_id=str(getattr(request, "investigation_id", "")),
                proposal_id=str(getattr(request, "proposal_id", "")),
                session_id=str(getattr(request, "session_id", "")),
                confirmation=str(getattr(request, "confirmation", "")),
                idempotency_key=str(getattr(request, "idempotency_key", "")),
            )
        return request

    def _from_proto_response(
        self, name: str, result: Any, response_type: Any, investigation_id: Any
    ) -> Any:
        if isinstance(result, response_type):
            return result
        d = result.dict() if hasattr(result, "dict") else dict(result)
        if name == "commits" and "files" in d:
            self.last_commit_files[str(investigation_id)] = d.pop("files")
        fields = getattr(response_type, "model_fields", None) or response_type.__fields__
        cleaned = {k: v for k, v in d.items() if k in fields and v not in ("", None)}
        if "investigation_id" not in cleaned:
            cleaned["investigation_id"] = str(investigation_id)
        return response_type.model_validate(cleaned)

    async def dispatch(self, name: str, handler: Callable | None, request, response_type):
        if self.cooldowns.get(name, 0) > time.monotonic():
            return response_type(
                investigation_id=request.investigation_id,
                success=False,
                error=AgentError(code="cooldown", message="Worker temporarily unavailable"),
            )

        target_address = self.peer_addresses.get(name)
        if target_address and self.send_fn:
            inv_id_str = str(request.investigation_id)
            key = (name, inv_id_str)
            for attempt in range(2):
                future = asyncio.get_running_loop().create_future()
                self.pending[key] = future
                try:
                    proto_msg = self._to_proto_message(name, request)
                    await self.send_fn(target_address, proto_msg)
                    raw_result = await asyncio.wait_for(future, timeout=self.timeout)
                    response = self._from_proto_response(
                        name, raw_result, response_type, request.investigation_id
                    )
                    if str(response.investigation_id) != str(request.investigation_id):
                        raise ValueError("Worker correlation mismatch")
                    if (
                        not response.success
                        and response.error
                        and (
                            response.error.get("retryable", False)
                            if isinstance(response.error, dict)
                            else response.error.retryable
                        )
                        and attempt == 0
                    ):
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
                except Exception as err:
                    return response_type(
                        investigation_id=request.investigation_id,
                        success=False,
                        error=AgentError(
                            code="invalid_worker_response",
                            message=f"Worker failed contract/correlation checks: {err}",
                        ),
                    )
                finally:
                    self.pending.pop(key, None)

        if handler is not None:
            for attempt in range(2):
                try:
                    wire_request = type(request).model_validate_json(request.model_dump_json())
                    result = await asyncio.wait_for(handler(wire_request), timeout=self.timeout)
                    response = response_type.model_validate_json(result.model_dump_json())
                    if str(response.investigation_id) != str(request.investigation_id):
                        raise ValueError("Worker correlation mismatch")
                    if (
                        not response.success
                        and response.error
                        and response.error.retryable
                        and attempt == 0
                    ):
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

        return response_type(
            investigation_id=request.investigation_id,
            success=False,
            error=AgentError(
                code="worker_unconfigured",
                message=f"Worker {name} has no address or local handler configured",
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
        provider_timeout: float = 3,
    ):
        self.store = store
        self.telemetry = telemetry
        self.commits = commits
        self.security = security
        self.reasoning = reasoning
        self.transport = transport or LocalWorkerTransport()
        self.provider_timeout = provider_timeout

    async def investigate(self, context: InvestigationContext) -> IncidentReport:
        self.store.transition(context.investigation_id, Status.COLLECTING)
        health, commits = await asyncio.gather(
            self.transport.dispatch(
                "health",
                getattr(self.telemetry, "run", None),
                HealthCheckRequest(
                    investigation_id=context.investigation_id, endpoint=context.endpoint
                ),
                HealthCheckResponse,
            ),
            self.transport.dispatch(
                "commits",
                getattr(self.commits, "run", None),
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
                files = getattr(self.transport, "last_commit_files", {}).get(
                    str(context.investigation_id)
                )
                if (
                    not files
                    and hasattr(self.commits, "client")
                    and hasattr(self.commits.client, "files")
                ):
                    files = await asyncio.wait_for(
                        self.commits.client.files(context.repository, commits.commits[0].sha),
                        self.provider_timeout,
                    )
                security = await self.transport.dispatch(
                    "security",
                    self.security.run if hasattr(self.security, "run") else None,
                    SecurityScanRequest(
                        investigation_id=context.investigation_id,
                        files=files or {},
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
        reasoning_warning = None
        try:
            hypothesis = await asyncio.wait_for(
                self.reasoning.synthesize(health, commits), self.provider_timeout
            )
        except (TimeoutError, ValueError, OSError):
            hypothesis = IncidentHypothesis(
                summary="Reasoning unavailable", confidence="insufficient_evidence", evidence_ids=[]
            )
            reasoning_warning = "Reasoning unavailable; structured worker evidence retained"
        allowed = {e.id for r in (health, commits, security) for e in r.evidence}
        candidates = {c.sha: c for c in commits.commits}
        if not set(hypothesis.evidence_ids) <= allowed or (
            hypothesis.commit_sha and hypothesis.commit_sha not in candidates
        ):
            hypothesis = IncidentHypothesis(
                summary="Reasoning output rejected: unsupported evidence references",
                confidence="insufficient_evidence",
                evidence_ids=[],
            )
            reasoning_warning = (
                "Reasoning output rejected: unsupported evidence or commit reference"
            )
        # Never pass free-form model factual claims through just because its references exist.
        selected = candidates.get(hypothesis.commit_sha or "")
        hypothesis.summary = f"Observed health: {health.state}. " + (
            f"Candidate {selected.sha[:8]} has score {selected.score:.3f} from diff/time correlation; not proof of causation."
            if selected
            else "No evidence-backed commit hypothesis established."
        )
        hypothesis.evidence_ids = [e.id for e in health.evidence] + (
            [f"commit:{selected.sha}"] if selected else []
        )
        if health.state != "failing" or not selected:
            hypothesis.confidence = "insufficient_evidence"
        elif hypothesis.confidence == "high":
            hypothesis.confidence = "medium"
        warnings = [w for r in (health, commits, security) for w in r.warnings]
        if reasoning_warning:
            warnings.append(reasoning_warning)
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
