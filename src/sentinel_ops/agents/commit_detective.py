import asyncio
from datetime import timedelta

from sentinel_ops.logging import redact
from sentinel_ops.schemas import (
    AgentError,
    CommitAnalysisRequest,
    CommitAnalysisResponse,
    Evidence,
    utcnow,
)
from sentinel_ops.services.github_client import GitHubClient


class CommitDetective:
    def __init__(self, client: GitHubClient):
        self.client = client

    async def run(self, request: CommitAnalysisRequest) -> CommitAnalysisResponse:
        start = utcnow()
        try:
            commits = await asyncio.wait_for(
                self.client.commits(request.repository, request.branch, request.max_commits), 3
            )
        except (OSError, ValueError, TimeoutError):
            return CommitAnalysisResponse(
                investigation_id=request.investigation_id,
                success=False,
                error=AgentError(
                    code="github_unavailable",
                    message="Recorded GitHub evidence unavailable",
                    retryable=True,
                ),
            )
        candidates = []
        warnings = ["Recorded GitHub evidence; correlation is not proof"]
        for commit in commits:
            if (
                not request.incident_at - timedelta(hours=request.lookback_hours)
                <= commit.timestamp
                <= request.incident_at
            ):
                continue
            budget = request.max_diff_bytes
            bounded = {}
            for path, diff in commit.files.items():
                clean = redact(diff).encode()
                bounded[path] = clean[:budget].decode(errors="ignore")
                if len(clean) > budget:
                    warnings.append(f"Diff truncated for {commit.sha[:8]}:{path}")
                budget = max(0, budget - len(clean))
            commit.files = bounded
            commit.message = redact(commit.message)
            joined = " ".join(bounded.values()).lower()
            touches = any(
                request.service_hint.lower() in p.lower() or p.endswith("config.json")
                for p in bounded
            )
            breaking = any(
                signal in joined
                for signal in ["503", '"healthy": false', "+raise ", "+verify=false"]
            )
            recent = max(
                0,
                1
                - (request.incident_at - commit.timestamp).total_seconds()
                / (request.lookback_hours * 3600),
            )
            commit.score = round(min(0.95, 0.2 * recent + 0.3 * touches + 0.4 * breaking), 3)
            commit.explanation = f"Correlation, not proof: recent={recent:.2f}, service_files={touches}, breaking_signal={breaking}"
            candidates.append(commit)
        candidates.sort(key=lambda c: (-c.score, c.sha))
        return CommitAnalysisResponse(
            investigation_id=request.investigation_id,
            started_at=start,
            completed_at=utcnow(),
            commits=candidates,
            warnings=warnings,
            evidence=[
                Evidence(id=f"commit:{c.sha}", source="github-recorded", summary=c.explanation)
                for c in candidates
            ],
        )
