import json
from uuid import UUID

from sentinel_ops import cards
from sentinel_ops.acp import ChatGateway, text_message
from sentinel_ops.agents.orchestrator import IncidentReport
from sentinel_ops.agents.remediation_executor import REVERT_CONTENT, RemediationExecutor
from sentinel_ops.schemas import RemediationExecutionRequest


class RemediationChatGateway(ChatGateway):
    def __init__(self, orchestrator, executor: RemediationExecutor):
        super().__init__(orchestrator)
        self.executor = executor

    async def action(self, owner: str, action: str, data: dict):
        current_id = self.store.read("session", owner)
        if not current_id:
            raise ValueError("No investigation in this session")
        if action in {"review_revert", "review_patch"}:
            report = IncidentReport.model_validate_json(self.store.read("report", current_id))
            if not report.commits.success or not report.commits.commits:
                raise ValueError("No commit evidence")
            proposal, nonce, key = self.executor.propose(
                UUID(current_id),
                owner,
                "revert_commit" if action == "review_revert" else "apply_patch",
                report.health.evidence + report.commits.evidence + report.security.evidence,
                report.hypothesis.confidence,
                report.commits.commits[0].sha,
                None if action == "review_revert" else REVERT_CONTENT,
            )
            return [cards.confirmation(proposal, nonce, key)]
        if action == "confirm":
            request = RemediationExecutionRequest.model_validate({**data, "session_id": owner})
            if str(request.investigation_id) != current_id:
                raise ValueError("Session investigation mismatch")
            result = await self.executor.execute(request)
            if result.success:
                self.store.put("session_action", owner, request.idempotency_key)
            return [text_message(json.dumps(result.model_dump(mode="json")))]
        return await super().action(owner, action, data)
