"""Session-bound, persisted explicit approval and retry-safe sandbox PR execution."""

import hashlib
import hmac
import json
from datetime import timedelta
from typing import Literal
from uuid import UUID, uuid4

from sentinel_ops.schemas import (
    AgentError,
    Evidence,
    RemediationExecutionRequest,
    RemediationExecutionResponse,
    RemediationProposal,
    Status,
    utcnow,
)
from sentinel_ops.services.sandbox_github import SandboxGitHubClient, digest
from sentinel_ops.state import StateStore

BAD_COMMIT = "b" * 40
REVERT_CONTENT = {
    "config.json": '{"healthy": true}\n',
    "requirements.txt": "demo-vulnerable==1.0.1\n",
}


def action_key(proposal: RemediationProposal) -> str:
    return hashlib.sha256(proposal.model_dump_json().encode()).hexdigest()


def pr_body(proposal: RemediationProposal) -> str:
    evidence = "\n".join(f"- {e.id}: {e.summary}" for e in proposal.evidence)
    return (
        f"# LOCAL SIMULATED PR\nInvestigation: {proposal.investigation_id}\n"
        f"Incident: failing demo checkout health\nAction: {proposal.action}\n"
        f"Confidence: {proposal.confidence}; correlation is not proof\n"
        f"Files: {', '.join(proposal.expected_files)}\nEvidence:\n{evidence}\n"
        "Validation: approved path/size/baseline hashes and configuration JSON checked.\n"
        f"Requested tests: {', '.join(proposal.tests)}. Health recovery not yet verified.\n"
        "Rollback: restore the saved pre-action sandbox snapshot using a fresh demo reset.\n"
        "Security: fictional demo dependency restored to fixture fixed version.\n"
        "Agent-generated and explicitly user-approved in the local simulator. No GitHub write or merge.\n"
    )


class RemediationExecutor:
    def __init__(self, store: StateStore, client: SandboxGitHubClient):
        self.store = store
        self.client = client

    def propose(
        self,
        investigation_id: UUID,
        session: str,
        action: Literal["revert_commit", "apply_patch"],
        evidence: list[Evidence],
        confidence: str,
        commit_sha: str | None = None,
        replacements: dict[str, str] | None = None,
    ) -> tuple[RemediationProposal, str, str]:
        context = self.store.get(investigation_id)
        if (
            context.session_id != session
            or context.permission != "create_pr"
            or context.status != Status.AWAITING
        ):
            raise ValueError("Proposal not permitted for this session/state")
        if action == "revert_commit":
            if commit_sha != BAD_COMMIT:
                raise ValueError("No known sandbox inverse for commit")
            content = dict(REVERT_CONTENT)
        elif action == "apply_patch" and replacements:
            content = dict(replacements)
        else:
            raise ValueError("Unsupported proposal")
        baseline = self.client.files()
        proposal = RemediationProposal(
            investigation_id=investigation_id,
            repository=context.repository,
            base_branch=context.branch,
            action=action,
            commit_sha=commit_sha,
            expected_files=sorted(content),
            replacements=content,
            expected_hashes={p: digest(baseline[p]) for p in content},
            evidence=evidence,
            confidence=confidence,
            tests=["validate config JSON", "independent local HTTP health check"],
        )
        self.client.validate(proposal)
        # The proposal object is serialized before it leaves this boundary. Callers cannot mutate approval.
        nonce = str(uuid4())
        key = action_key(proposal)
        document = {
            "proposal": proposal.model_dump(mode="json"),
            "session": session,
            "confirmation_hash": digest(nonce),
            "key": key,
            "expires": (utcnow() + timedelta(minutes=10)).isoformat(),
        }
        self.store.put("proposal", str(proposal.proposal_id), json.dumps(document))
        self.store.put("active_proposal", str(investigation_id), str(proposal.proposal_id))
        return proposal, nonce, key

    async def execute(self, request: RemediationExecutionRequest) -> RemediationExecutionResponse:
        def fail(code, message):
            return RemediationExecutionResponse(
                investigation_id=request.investigation_id,
                success=False,
                error=AgentError(code=code, message=message),
            )

        raw = self.store.read("proposal", str(request.proposal_id))
        if not raw:
            return fail("confirmation_required", "Unknown proposal")
        saved = json.loads(raw)
        proposal = RemediationProposal.model_validate(saved["proposal"])
        context = self.store.get(request.investigation_id)
        if (
            proposal.investigation_id != request.investigation_id
            or saved["session"] != request.session_id
            or context.session_id != request.session_id
            or context.permission != "create_pr"
            or not hmac.compare_digest(saved["confirmation_hash"], digest(request.confirmation))
            or saved["key"] != request.idempotency_key
        ):
            return fail(
                "confirmation_required", "Explicit matching session/proposal confirmation required"
            )
        cached = self.store.read("execution", saved["key"])
        if cached:
            if context.status == Status.EXECUTING:
                self.store.transition(request.investigation_id, Status.VERIFYING)
            return RemediationExecutionResponse.model_validate_json(cached)
        if self.store.read("active_proposal", str(request.investigation_id)) != str(
            request.proposal_id
        ):
            return fail("stale_proposal", "A newer proposal supersedes this action")
        if utcnow().isoformat() > saved["expires"]:
            return fail("expired_confirmation", "Review a new proposal")
        if context.status not in {Status.AWAITING, Status.EXECUTING}:
            return fail("invalid_state", "Investigation cannot execute")
        try:
            self.client.validate(proposal)
            if context.status == Status.AWAITING:
                self.store.transition(request.investigation_id, Status.EXECUTING)
            number, url = await self.client.create_pr(proposal, saved["key"], pr_body(proposal))
        except (ValueError, OSError):
            if self.store.get(request.investigation_id).status == Status.EXECUTING:
                self.store.transition(request.investigation_id, Status.FAILED)
            return fail(
                "sandbox_conflict_or_error",
                "No remediation applied; inspect baseline and create a fresh investigation",
            )
        result = RemediationExecutionResponse(
            investigation_id=request.investigation_id,
            pr_number=number,
            pr_url=url,
            validation="Static proposal checks passed; health verification pending",
            warnings=["Simulated local PR only; service state unchanged"],
            evidence=[
                Evidence(
                    id=f"pr:{number}", source="sandbox", summary="Confirmed simulated PR created"
                )
            ],
        )
        self.store.put("execution", saved["key"], result.model_dump_json())
        self.store.transition(request.investigation_id, Status.VERIFYING)
        return result
