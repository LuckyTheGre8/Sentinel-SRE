"""Typed inter-agent protocols for Sentinel-Ops."""

from sentinel_ops.protocols.commit import (
    CommitAnalysisRequest,
    CommitAnalysisResponse,
    commit_protocol,
)
from sentinel_ops.protocols.health import (
    HealthCheckRequest,
    HealthCheckResponse,
    VerificationRequest,
    VerificationResponse,
    health_protocol,
)
from sentinel_ops.protocols.orchestration import (
    IncidentReport,
    InvestigationRequest,
    orchestration_protocol,
)
from sentinel_ops.protocols.remediation import (
    RemediationExecutionRequest,
    RemediationExecutionResponse,
    RemediationProposalRequest,
    RemediationProposalResponse,
    remediation_protocol,
)
from sentinel_ops.protocols.security import (
    SecurityScanRequest,
    SecurityScanResponse,
    security_protocol,
)

__all__ = [
    "health_protocol",
    "HealthCheckRequest",
    "HealthCheckResponse",
    "VerificationRequest",
    "VerificationResponse",
    "commit_protocol",
    "CommitAnalysisRequest",
    "CommitAnalysisResponse",
    "security_protocol",
    "SecurityScanRequest",
    "SecurityScanResponse",
    "remediation_protocol",
    "RemediationProposalRequest",
    "RemediationProposalResponse",
    "RemediationExecutionRequest",
    "RemediationExecutionResponse",
    "orchestration_protocol",
    "InvestigationRequest",
    "IncidentReport",
]
