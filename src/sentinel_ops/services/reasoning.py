"""ASI:One boundary. Only the explicitly simulated local implementation is provided."""

import json
import re
from typing import Protocol

from sentinel_ops.schemas import CommitAnalysisResponse, HealthCheckResponse, IncidentHypothesis


class ReasoningClient(Protocol):
    async def extract(self, text: str) -> dict: ...
    async def synthesize(
        self, health: HealthCheckResponse, commits: CommitAnalysisResponse
    ) -> IncidentHypothesis: ...


class LocalReasoningClient:
    """Deterministic simulator, NOT an ASI:One model call."""

    async def extract(self, text: str) -> dict:
        try:
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                raise ValueError("Expected object")
            return parsed
        except json.JSONDecodeError:
            result: dict = {}
            url = re.search(r"https?://[^\s`]+", text)
            cleaned = text
            if url:
                result["endpoint"] = url.group().rstrip(".,")
                cleaned = cleaned.replace(url.group(), "")
            repo = re.search(r"(?<![\w/])([\w.-]+/[\w.-]+)(?![\w/])", cleaned)
            if repo:
                result["repository"] = repo.group(1)
            branch = re.search(r"\bbranch[ =]+([\w./-]+)", text)
            if branch:
                result["branch"] = branch.group(1)
            window = re.search(r"\b(\d+)\s*hours?", text)
            if window:
                result["lookback_hours"] = int(window.group(1))
            result["permission"] = "create_pr" if "create_pr" in text else "read_only"
            return result

    async def synthesize(
        self, health: HealthCheckResponse, commits: CommitAnalysisResponse
    ) -> IncidentHypothesis:
        top = commits.commits[0] if commits.commits else None
        refs = [e.id for e in health.evidence]
        if top:
            refs.append(f"commit:{top.sha}")
        summary = f"Observed health: {health.state}. "
        if top:
            summary += f"Candidate {top.sha[:8]} ranks first by recorded diff/time correlation; not proof of causation."
        else:
            summary += "No candidate commit established."
        return IncidentHypothesis(
            summary=summary,
            confidence="medium" if top and health.state == "failing" else "insufficient_evidence",
            evidence_ids=refs,
            commit_sha=top.sha if top else None,
        )
