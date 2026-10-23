from typing import Literal

from sentinel_ops.schemas import (
    AgentError,
    Evidence,
    HealthCheckRequest,
    HealthCheckResponse,
    utcnow,
)
from sentinel_ops.services.health_client import HealthClient


class TelemetryWatchdog:
    def __init__(self, client: HealthClient):
        self.client = client

    async def run(self, request: HealthCheckRequest) -> HealthCheckResponse:
        started = utcnow()
        probes = [
            await self.client.probe(request.endpoint, request.timeout_seconds)
            for _ in range(request.probes)
        ]
        good = [p for p in probes if p.failure is None and p.status is not None]
        known = [p for p in probes if p.status is not None]
        state: Literal["healthy", "degraded", "failing", "unknown"] = (
            "healthy"
            if len(good) == len(probes)
            else "degraded"
            if good
            else "failing"
            if known
            else "unknown"
        )
        consecutive = 0
        for probe in reversed(probes):
            if probe.failure is None:
                break
            consecutive += 1
        return HealthCheckResponse(
            investigation_id=request.investigation_id,
            started_at=started,
            completed_at=utcnow(),
            state=state,
            probes=probes,
            consecutive_failures=consecutive,
            last_success=good[-1].timestamp if good else None,
            success=bool(known),
            error=None
            if known
            else AgentError(code=probes[-1].failure or "unavailable", message="Health unavailable"),
            evidence=[
                Evidence(
                    id=f"health:{i}",
                    source="health",
                    simulated=self.client.simulated,
                    summary=f"HTTP {p.status}; failure={p.failure}; latency_ms={p.latency_ms:.2f}",
                )
                for i, p in enumerate(probes)
            ],
            warnings=["Recorded HTTP transport"] if self.client.simulated else [],
        )
