# Sentinel-Commit

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

**Handle**: `@sentinel-commit`  
**Default Port**: `8002`  
**Seed Env Var**: `COMMIT_SEED`  
**Protocol**: `SentinelCommit` (`CommitAnalysisRequest`, `CommitAnalysisResponse`) + `AgentChatProtocol` (ACP)

Inspects GitHub commits within a configurable lookback window (default 24h). Redacts sensitive diffs, inspects modifications touching service code or configuration, detects breaking signals, and ranks candidate commits with bounded confidence scoring.

### ACP Capabilities
- `analyze_commits`: Analyzes branch commit history and diffs for a specified GitHub repository.

### Chat Examples
- `{"action": "analyze_commits", "repository": "owner/repo", "branch": "main"}`
- `owner/repo`
