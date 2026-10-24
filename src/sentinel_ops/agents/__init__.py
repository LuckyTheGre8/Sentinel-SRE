"""Independent workers and standalone uAgents for Sentinel-Ops."""

from sentinel_ops.agents.commit_detective import CommitDetective
from sentinel_ops.agents.orchestrator import (
    IncidentReport,
    LocalWorkerTransport,
    NetworkWorkerTransport,
    SentinelOrchestrator,
)
from sentinel_ops.agents.remediation_executor import RemediationExecutor
from sentinel_ops.agents.security_investigator import SecurityInvestigator
from sentinel_ops.agents.telemetry_watchdog import TelemetryWatchdog


def __getattr__(name):
    # Load entry points on demand: importing runtime settings must not import
    # an agent entry point which imports those same settings again.
    builders = {
        "build_commit_agent": "commit_agent",
        "build_orchestrator_agent": "orchestrator_agent",
        "build_remediation_agent": "remediation_agent",
        "build_security_agent": "security_agent",
        "build_telemetry_agent": "telemetry_agent",
    }
    if name not in builders:
        raise AttributeError(name)
    from importlib import import_module

    value = getattr(import_module(f"sentinel_ops.agents.{builders[name]}"), name)
    globals()[name] = value
    return value

__all__ = [
    "CommitDetective",
    "SecurityInvestigator",
    "TelemetryWatchdog",
    "RemediationExecutor",
    "SentinelOrchestrator",
    "IncidentReport",
    "LocalWorkerTransport",
    "NetworkWorkerTransport",
    "build_telemetry_agent",
    "build_commit_agent",
    "build_security_agent",
    "build_remediation_agent",
    "build_orchestrator_agent",
]
