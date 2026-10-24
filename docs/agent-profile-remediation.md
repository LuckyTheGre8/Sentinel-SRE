# Sentinel-Remediation

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

**Handle**: `@sentinel-remediation`  
**Default Port**: `8004`  
**Seed Env Var**: `REMEDIATION_SEED`  
**Protocol**: `SentinelRemediation` (`RemediationProposalRequest`, `RemediationProposalResponse`, `RemediationExecutionRequest`, `RemediationExecutionResponse`) + `AgentChatProtocol` (ACP)

Generates explicit revert proposals with nonces and sha256 action keys. Executes confirmed PR creation in a sandbox SQLite backend or scoped live GitHub repository. Automatic merging is strictly disabled; requires human operator confirmation.

### ACP Capabilities
- `propose_revert`: Generates structured revert diffs and confirmation nonces.
- `confirm`: Verifies nonce and idempotency key before creating the remediation PR.

### Chat Examples
- `{"action": "propose_revert", "investigation_id": "..."}`
- `{"action": "confirm", "proposal_id": "...", "confirmation": "...", "idempotency_key": "..."}`
