# Sentinel-Orchestrator

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

**Handle**: `@sentinel-orchestrator`  
**Default Port**: `8005`  
**Seed Env Var**: `ORCHESTRATOR_SEED`  
**Protocol**: `AgentChatProtocol` (ACP) + Dispatches native uAgents protocols to Telemetry, Commit, Security, and Remediation peers.

Primary user-facing entry point. Coordinates complete incident investigation lifecycle:
1. Validates intake repository and endpoint against configured scope.
2. Dispatches parallel health probes (`SentinelHealth`) and commit analysis (`SentinelCommit`).
3. Dispatches dependency scanning (`SentinelSecurity`) based on suspect revision files.
4. Synthesizes hypothesis via ASI:One reasoning client.
5. Manages revert proposals and PR confirmation with Sentinel-Remediation (`SentinelRemediation`).
6. Triggers recovery verification with Sentinel-Telemetry.

### ACP Capabilities
- Full workflow: `intake -> report -> review_revert -> confirm -> verify`

### Chat Examples
- `Investigate owner/repo at https://example.com/health over 24h`
- `{"action": "intake", "repository": "owner/repo", "endpoint": "https://example.com/health"}`
- `{"action": "start", "investigation_id": "..."}`
- `{"action": "verify"}`
