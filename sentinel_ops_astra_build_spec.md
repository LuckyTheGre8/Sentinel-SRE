# Sentinel-Ops — Astra Build Specification

> **Purpose:** Give Astra a complete, implementation-ready specification for building and deploying Sentinel-Ops for Fetch-A-Thon 3.0.
>
> **Official challenge:** [Fetch-A-Thon 3.0 Hackpack](https://www.fetch.ai/events/hackathons/fetch-a-thon-3/hackpack)
>
> **Primary rule:** Build one reliable end-to-end workflow first. Do not expand the scope until the complete workflow works from an ASI:One conversation.

---

## 1. Instructions for Astra

Act as the lead implementation engineer for this project. Build the system incrementally, keep every module independently testable, and stop at the validation gate after each phase. Do not replace real integrations with mock data without clearly labeling the mock and keeping the interface identical to the real integration.

Before implementing a Fetch.ai-specific API, confirm its current interface against the official Fetch.ai documentation. Do not invent SDK methods, card schemas, deployment commands, Payment Protocol calls, or Agentverse configuration fields.

For every phase:

1. Implement the smallest working slice.
2. Add tests for the new behavior.
3. Run the relevant tests.
4. Report changed files, commands run, and remaining risks.
5. Recommend the exact commit boundary.
6. Do not begin an optional feature while a required validation gate is failing.

Never print, log, commit, or display secrets. Repository-writing actions must require explicit user confirmation. Automatic merging must remain disabled by default.

---

## 2. Product Definition

### Name

**Sentinel-Ops: From Production Incident to Verified Recovery**

### One-line pitch

Sentinel-Ops turns an ASI:One incident request into an evidence-backed diagnosis, a user-approved remediation pull request, and a verified recovery using specialized Fetch.ai agents.

### Problem

Small engineering teams frequently lack continuous SRE and application-security coverage. When production fails, developers must manually inspect telemetry, correlate deployments and commits, scan code and dependencies, decide between rollback and patching, create a pull request, and verify recovery. The fragmented process increases downtime and encourages rushed, unsafe decisions.

### Target users

- Startup engineering teams without a dedicated 24/7 SRE team.
- Developers operating small production services.
- DevSecOps teams that want a conversational first-response assistant.
- Maintainers who need an auditable, human-approved remediation workflow.

### Executable outcome

The system must produce all of the following inside one ASI:One conversation:

1. A live health assessment.
2. An evidence-backed incident diagnosis.
3. A ranked suspected commit with a confidence score.
4. Relevant dependency and code-security findings.
5. A user-approved rollback or patch proposal.
6. A real GitHub pull request, or a clearly marked sandbox PR during the demo.
7. A post-action verification report.

The product is not complete if it only returns recommendations or alerts.

---

## 3. Hackathon Alignment

The implementation must satisfy these non-negotiable requirements from the official hackpack:

- Register at least one agent on Agentverse.
- Make the public agent discoverable and usable through ASI:One.
- Implement the Agent Chat Protocol (ACP).
- Demonstrate meaningful tool execution or multi-agent orchestration.
- Complete the primary workflow inside the ASI:One conversation.
- Publish a public GitHub repository with run and test instructions.

Optimize the build for the judging weights:

- **25% Functionality and technical implementation:** prioritize a working incident-to-PR loop.
- **20% Fetch.ai technology:** make ASI:One reasoning, Agentverse discovery, ACP, and agent-to-agent communication visible.
- **20% Innovation:** show evidence fusion and specialist-agent collaboration.
- **20% Real-world impact:** demonstrate reduced incident response time with safety controls.
- **15% UX and presentation:** use concise, guided interactive cards and a reproducible demo.

Bonus features are allowed only after the core validation gate passes:

- Fetch.ai Payment Protocol with a credible specialist-agent payment model.
- Scheduled monitoring.
- Automatic merging in a sandbox.
- Additional scanners or deployment providers.

---

## 4. Scope

### Required MVP workflow

The demo user enters a request similar to:

> Investigate the checkout outage in `owner/payment-service` using `https://demo.example/health`. Review recent commits and prepare the safest remediation.

The system must then:

1. Extract and confirm the repository, branch, endpoint, lookback window, and permission mode.
2. Check current endpoint health.
3. Inspect recent commits and diffs within the incident window.
4. Scan relevant dependencies and changed code.
5. Rank incident hypotheses and explain the evidence.
6. Present rollback and patch options.
7. Require explicit confirmation.
8. Create the chosen PR.
9. Run or observe validation checks.
10. Recheck service health or the sandbox recovery signal.
11. Present a final audit summary with links.

### Explicitly out of MVP scope

- Supporting every Git provider.
- Full enterprise SAST coverage.
- Fully autonomous production deployment.
- Automatic merging without confirmation.
- Kubernetes remediation.
- A separate web dashboard.
- Complex billing or production token settlement.

---

## 5. System Architecture

Use five independently testable agents. The Orchestrator is the only user-facing ASI:One entry point. Worker agents communicate using typed messages and return structured evidence.

```text
User in ASI:One
       |
       | ACP conversation + interactive cards
       v
Sentinel-Orchestrator
       |
       +------ HealthCheckRequest ------> Telemetry-Watchdog
       |
       +------ CommitAnalysisRequest ---> Commit-Detective
       |
       +------ SecurityScanRequest -----> Security-Investigator
       |
       +------ RemediationRequest ------> Remediation-Executor
       |
       v
Evidence synthesis, confirmation, PR result, recovery report
```

### Recommended implementation stack

- Python 3.11 or the version currently supported by the chosen uAgents release.
- `uagents` and `uagents-core` for agents and ACP.
- `httpx` for asynchronous HTTP calls.
- GitHub REST API or the officially supported GitHub MCP integration.
- OSV API for dependency-vulnerability lookup.
- Pydantic/uAgents models for typed contracts.
- `pytest` and async test support.
- A toy FastAPI service for the deterministic demo environment.

Pin dependency versions after verifying compatibility. Do not use unbounded dependency ranges.

### Suggested repository structure

```text
sentinel-ops/
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── docker-compose.yml                 # optional local demo orchestration
├── src/
│   └── sentinel_ops/
│       ├── config.py
│       ├── logging.py
│       ├── schemas.py
│       ├── state.py
│       ├── agents/
│       │   ├── orchestrator.py
│       │   ├── telemetry_watchdog.py
│       │   ├── commit_detective.py
│       │   ├── security_investigator.py
│       │   └── remediation_executor.py
│       ├── services/
│       │   ├── github_client.py
│       │   ├── osv_client.py
│       │   ├── health_client.py
│       │   ├── redaction.py
│       │   └── risk_engine.py
│       └── cards/
│           ├── intake.py
│           ├── progress.py
│           ├── incident_report.py
│           ├── confirmation.py
│           └── resolution.py
├── demo_service/
│   ├── app.py
│   ├── requirements.txt
│   └── scenarios/
│       ├── healthy.json
│       └── failing.json
├── tests/
│   ├── unit/
│   ├── contract/
│   └── integration/
├── scripts/
│   ├── smoke_test.py
│   └── verify_deployment.py
└── docs/
    ├── architecture.md
    ├── deployment.md
    ├── demo-script.md
    └── threat-model.md
```

---

## 6. Shared Models and State

All messages must contain an `investigation_id` so logs and responses can be correlated. Use UUIDs. Dates must use UTC ISO 8601 internally and may be localized for display.

### Core enums

```python
InvestigationStatus = Literal[
    "created",
    "collecting_evidence",
    "awaiting_confirmation",
    "executing",
    "verifying",
    "resolved",
    "partially_resolved",
    "failed",
    "cancelled",
]

PermissionMode = Literal["read_only", "create_pr", "sandbox_auto_merge"]
RemediationType = Literal["revert_commit", "apply_patch"]
FindingSeverity = Literal["critical", "high", "medium", "low", "info"]
ConfidenceLevel = Literal["high", "medium", "low", "insufficient_evidence"]
```

### Minimum request and response contracts

Implement and test typed models for:

- `InvestigationRequest`
- `InvestigationContext`
- `HealthCheckRequest` / `HealthCheckResponse`
- `CommitAnalysisRequest` / `CommitAnalysisResponse`
- `SecurityScanRequest` / `SecurityScanResponse`
- `IncidentHypothesis`
- `RemediationProposal`
- `RemediationExecutionRequest` / `RemediationExecutionResponse`
- `VerificationRequest` / `VerificationResponse`
- `AgentError`

Every worker response must include:

- `investigation_id`
- `agent_name`
- `success`
- `started_at`
- `completed_at`
- `evidence`
- `warnings`
- `error`, when unsuccessful

### Investigation state machine

```text
CREATED
  -> COLLECTING_EVIDENCE
  -> AWAITING_CONFIRMATION
  -> EXECUTING
  -> VERIFYING
  -> RESOLVED | PARTIALLY_RESOLVED | FAILED

At any pre-execution state:
  -> CANCELLED
```

Reject invalid transitions. Store enough state to make retries idempotent and prevent duplicate PR creation.

---

## 7. Detailed Agent Specifications

## 7.1 Sentinel-Orchestrator

### Responsibility

Own the ASI:One conversation, interpret user intent, coordinate workers, synthesize evidence, obtain approval, and present the final outcome.

### Inputs

- Natural-language ACP messages.
- Interactive-card submissions.
- Worker-agent responses.
- Tool failure events and timeouts.

### Required behavior

1. Acknowledge every supported ACP message correctly.
2. Use ASI:One reasoning to extract:
   - Repository identifier.
   - Branch, defaulting to the repository default branch.
   - Health endpoint.
   - Incident lookback window.
   - Requested mode.
3. Never silently invent a missing repository or endpoint.
4. Render an intake/review card before starting an investigation.
5. Dispatch health and commit analysis concurrently when possible.
6. Dispatch security analysis once relevant files, dependencies, and commits are known.
7. Combine deterministic evidence with LLM reasoning.
8. Label hypotheses as likely, possible, or unconfirmed.
9. Present remediation options with expected effect and risk.
10. Require a confirmation card before any GitHub write.
11. Generate one idempotency key per approved action.
12. Render final status even when a worker fails.

### Evidence-synthesis policy

The LLM may rank and explain evidence, but it must not fabricate tool results. Every factual claim in the incident report must point to structured evidence returned by a worker. If evidence conflicts, show the conflict.

Suggested confidence inputs:

- Temporal proximity of commit/deployment to incident.
- Whether changed files affect the failing endpoint.
- Whether the diff contains a plausible breaking change.
- Whether tests or validation reproduce the failure.
- Whether reverting the change restores the sandbox service.

### Failure behavior

- If telemetry fails, continue with Git and security analysis but mark live health as unknown.
- If GitHub fails, do not offer a real remediation action.
- If OSV fails, show SAST results and mark dependency analysis unavailable.
- If a worker times out, retry once with jitter, then return a partial report.
- Never turn an unavailable tool into a clean bill of health.

### Acceptance tests

- A valid chat request creates an investigation ID.
- Missing required data results in a guided intake request.
- Worker messages are correlated to the correct investigation.
- A PR cannot be created before confirmation.
- Repeated confirmation does not create a second PR.
- Partial worker failure still produces an honest report.

---

## 7.2 Telemetry-Watchdog

### Responsibility

Collect live endpoint evidence and verify service recovery.

### Inputs

- Endpoint URL.
- HTTP method, default `GET`.
- Timeout.
- Expected status range.
- Optional safe response match.
- Number of probes and interval.

### Output

- Individual probe timestamps.
- Status codes.
- Latency in milliseconds.
- Consecutive failures.
- Last successful probe.
- Sanitized error or response excerpt.
- Overall state: healthy, degraded, failing, or unknown.

### Safety and reliability

- Permit only `http` and `https` schemes.
- Add an allowlist for demo endpoints.
- Block localhost, metadata services, and private network ranges unless explicitly running in local demo mode.
- Limit redirects and response body size.
- Use bounded timeouts.
- Redact authorization headers and suspected secrets.
- Distinguish DNS failure, timeout, TLS failure, connection refusal, and non-success HTTP responses.

### Acceptance tests

- Correctly classifies healthy, degraded, failing, and unreachable endpoints.
- Does not follow an unsafe redirect.
- Does not leak response secrets.
- Verification uses the same probe policy as the initial check.

---

## 7.3 Commit-Detective

### Responsibility

Inspect recent Git history and rank changes that plausibly contributed to the incident.

### Inputs

- Repository.
- Branch.
- Incident timestamp or lookback period.
- Relevant endpoint/service hints.
- Maximum commits and diff-size limits.

### Output

For each candidate commit:

- SHA and web URL.
- Commit timestamp.
- Author display name; avoid unnecessary personal information.
- Pull request, when available.
- Changed files.
- Sanitized diff excerpts.
- Risk indicators.
- Confidence score from 0 to 1.
- Explanation tied to evidence.

### Ranking signals

- Commit occurred shortly before the first observed failure.
- Changed files map to the failing route or service.
- Configuration, dependency, gateway, or environment logic changed.
- Error-handling, authentication, rate limiting, or routing changed.
- Tests were deleted or weakened.
- Diff introduces a syntax or configuration error.

Do not use commit author identity as a risk signal. Avoid blame-oriented language.

### Failure behavior

- On rate limiting, return retry information and any completed partial analysis.
- On oversized diffs, inspect filenames and bounded excerpts rather than failing the entire investigation.
- On private-repository authorization failure, provide a precise configuration error without exposing token details.

### Acceptance tests

- Ranks the known bad demo commit above unrelated commits.
- Labels correlation as correlation, not proof.
- Truncates large diffs safely.
- Handles a repository with no recent commits.

---

## 7.4 Security-Investigator

### Responsibility

Perform focused dependency analysis and lightweight code-security analysis on the relevant commit and changed files.

### Dependency analysis

- Parse supported manifests: `requirements.txt`, `pyproject.toml`, `package.json`, lockfiles when practical, `go.mod`, `pom.xml`, and Dockerfiles.
- Normalize package ecosystems to OSV-supported values.
- Query OSV in batches.
- Parse vulnerability aliases, affected ranges, severity data when available, references, and fixed versions.
- Never invent a fixed version. Return `unknown` when the upstream data does not establish one.
- Prefer lockfile-resolved versions over manifest ranges.

### Code analysis

For the MVP, implement a small, explainable ruleset:

- Hardcoded credentials, with secret-value redaction.
- Obvious SQL string interpolation.
- Shell execution with unsafe user-controlled input or `shell=True`.
- Unpinned container images.
- Disabled TLS verification.
- Overly permissive CORS in production configuration.

Use AST analysis where practical and regex only for narrow, well-tested patterns. Return confidence and explain limitations.

### Output

- Dependency findings.
- Code findings.
- Severity.
- Confidence.
- File and line reference.
- Redacted evidence.
- Suggested remediation.
- Whether the finding is likely related to the incident.
- Aggregate risk score with a documented formula.

### Risk model

Keep incident likelihood and security severity separate. Do not allow several low-confidence regex matches to outweigh a reproducible outage signal.

### Acceptance tests

- Detects the intentionally vulnerable demo dependency.
- Detects the intentionally insecure code sample.
- Does not print the secret value.
- Handles OSV timeout with an incomplete-analysis warning.
- Does not report an arbitrary “latest stable” version as a verified fix.

---

## 7.5 Remediation-Executor

### Responsibility

Turn an approved proposal into a reviewable GitHub pull request and return an auditable result.

### Supported MVP actions

#### Revert commit

- Create a uniquely named branch.
- Revert the selected commit without rewriting history.
- Handle conflicts as a non-destructive failure.
- Push the branch.
- Open a PR containing incident evidence and validation instructions.

#### Apply bounded patch

- Accept only a pre-reviewed patch payload tied to the investigation.
- Limit modifications to approved files.
- Update a dependency or apply a narrow source fix.
- Run formatting and relevant tests before opening the PR.
- Never make unrelated cleanup changes.

### Confirmation requirements

Execution requires:

- Investigation ID.
- Proposal ID.
- User confirmation token or signed card action.
- Repository and base branch.
- Exact action.
- Expected file set.
- Idempotency key.

### Pull request template

Include:

- Incident summary.
- Evidence and confidence.
- Chosen remediation.
- Files changed.
- Security findings addressed.
- Tests run and results.
- Rollback plan.
- Sentinel-Ops investigation ID.
- Disclosure that the PR was agent-generated and user-approved.

### Safety

- Use a least-privilege GitHub token.
- Do not force push.
- Do not push directly to the default branch.
- Do not merge by default.
- Do not execute arbitrary shell commands derived from model output.
- Validate repository, branch, file paths, and patch size.
- Prevent path traversal.

### Acceptance tests

- Confirmation is mandatory.
- Duplicate execution returns the original PR rather than creating another.
- A revert conflict produces a safe failure with next steps.
- Patch mode cannot modify unapproved files.
- The final response includes the real PR URL and validation status.

---

## 8. ASI:One Conversation and Interactive Cards

The primary workflow must be usable without an external dashboard.

### Card 1: Investigation intake

Fields:

- Repository.
- Branch.
- Health endpoint.
- Lookback window.
- Permission mode.

Actions:

- Start investigation.
- Cancel.

### Card 2: Progress

Show a compact status list:

- Endpoint check.
- Commit analysis.
- Dependency analysis.
- Code-security analysis.

Do not claim completion until the worker response arrives.

### Card 3: Incident report

Show:

- Service state.
- Leading hypothesis and confidence.
- Suspected commit.
- Supporting evidence.
- Incident-related vulnerabilities.
- Unrelated security debt, separately.
- Recommended remediation.

Actions:

- Review rollback.
- Review patch.
- View evidence.
- Cancel.

### Card 4: Execution confirmation

Show exactly:

- Repository and branch.
- Proposed action.
- Commit or files affected.
- Tests to run.
- Whether a PR will be created or merged.
- Known risks.

Actions:

- Confirm and create PR.
- Go back.
- Cancel.

### Card 5: Resolution

Show:

- PR URL and number.
- Test/check status.
- Initial health versus final health.
- Latency comparison.
- Final result: resolved, partially resolved, or unresolved.
- Investigation ID.

Use the current official ASI1 Interactive Cards schema. If an action or component is unsupported, use a supported alternative instead of fabricating a card feature.

---

## 9. Demo Environment

Build a deterministic toy service so the full story works during judging.

### Required demo behavior

- `/health` returns `200` in the healthy state.
- A known bad commit changes the service into a failing state returning `503`.
- The bad change should also contain one small, obvious security issue or vulnerable dependency.
- Reverting the commit or applying the prepared patch restores the healthy state.
- The service must expose no real secrets.

### Recommended scenario

1. Initial commit: healthy checkout service.
2. Normal unrelated commit: documentation or harmless UI change.
3. Bad commit: broken route/configuration plus a vulnerable pinned dependency.
4. Sentinel-Ops should rank the bad commit first.
5. User approves the revert PR.
6. A local or hosted demo hook updates the sandbox state after the approved action.
7. Final health check returns `200`.

Keep a prerecorded fallback demonstration and cached read-only responses, but clearly state when fallback data is being used.

---

## 10. Configuration and Secrets

Create `.env.example` with names only, never values:

```dotenv
GITHUB_TOKEN=
GITHUB_OWNER=
GITHUB_REPO=
GITHUB_DEFAULT_BRANCH=main
DEMO_HEALTH_URL=
TELEMETRY_AGENT_ADDRESS=
COMMIT_AGENT_ADDRESS=
SECURITY_AGENT_ADDRESS=
REMEDIATION_AGENT_ADDRESS=
ASI1_API_KEY=
AGENTVERSE_API_KEY=
PAYMENT_ENABLED=false
SANDBOX_AUTO_MERGE=false
LOG_LEVEL=INFO
```

Add `.env`, private keys, agent seeds, token files, caches, generated logs, and local databases to `.gitignore` before the first commit.

Agent seeds must come from secret configuration, not source code. Logs must redact tokens, authorization headers, suspected credentials, and sensitive diff content.

---

## 11. Reliability Requirements

- Apply bounded timeouts to every external request.
- Retry only transient errors and cap retry attempts.
- Use exponential backoff with jitter.
- Return partial results when safe.
- Propagate structured errors rather than raw stack traces.
- Add circuit-breaking or cooldown for repeated failures.
- Use idempotency keys for GitHub writes.
- Persist minimal investigation state so a restart does not repeat an action.
- Validate every cross-agent message.
- Record timestamps and correlation IDs.
- Make health verification independent from the remediation result.
- Treat “PR created” and “incident resolved” as separate states.

---

## 12. Deployment Runbook

Follow this order. Do not deploy all agents simultaneously before testing them locally.

### Stage 1: Local validation

1. Create the environment and install pinned dependencies.
2. Validate configuration at startup.
3. Start the demo service.
4. Run unit and contract tests.
5. Run every worker locally with recorded fixtures.
6. Run a local end-to-end investigation without GitHub writes.
7. Run the sandbox PR flow against the demo repository.

**Gate:** One command or documented sequence completes the full local workflow twice without duplicate PRs.

### Stage 2: Deploy read-only worker agents

Deploy in this order:

1. Telemetry-Watchdog.
2. Commit-Detective.
3. Security-Investigator.

After each deployment:

- Record the Agentverse address.
- Send one known request.
- Validate the typed response.
- Test an invalid request.
- Test timeout or dependency failure behavior.

**Gate:** All read-only workers respond independently from their deployed addresses.

### Stage 3: Deploy Remediation-Executor

1. Start in read-only/dry-run mode.
2. Validate proposal rendering.
3. Enable `create_pr` mode only for the dedicated demo repository.
4. Verify least-privilege GitHub access.
5. Confirm idempotency by repeating the same request.

**Gate:** One confirmed request creates exactly one PR in the demo repository.

### Stage 4: Deploy Sentinel-Orchestrator

1. Configure deployed worker addresses.
2. Implement and validate ACP acknowledgements and session handling.
3. Publish the ACP manifest using the current official method.
4. Register/categorize the agent as required by the hackathon.
5. Confirm Agentverse discovery.
6. Confirm ASI:One routes a natural-language request to the agent.
7. Validate every card action.

**Gate:** A fresh ASI:One conversation completes the workflow without a custom frontend.

### Stage 5: Production-style smoke test

Run the exact judge path:

1. Start from a new ASI:One chat.
2. Enter the demo request.
3. Confirm the intake card.
4. Wait for real worker responses.
5. Review the evidence card.
6. Confirm a remediation.
7. Open the returned PR URL.
8. Verify the final health result.
9. Save the public shared-chat URL.

Run this at least twice before recording. Save screenshots of agent profiles and the successful conversation as fallback evidence.

### Stage 6: Payment Protocol, only if stable

Enable payment behind `PAYMENT_ENABLED`.

Credible model:

- The Orchestrator receives an investigation budget.
- It pays specialist agents for completed, structured results.
- The UI shows quoted cost, settlement state, and transaction reference.
- Failed or timed-out calls must not be represented as successful paid work.

Use the Fetch.ai Payment Protocol, not a generic Stripe substitute, when claiming Fetch.ai payment integration.

**Gate:** Payment failure does not break the free/demo incident workflow.

---

## 13. Build Order and Validation Gates

### Phase 0 — Repository safety

- Initialize project structure.
- Add `.gitignore` and `.env.example`.
- Add configuration validation.
- Add the official hackathon badges to `README.md`.

**Commit after:** secret scan and configuration test pass.

### Phase 1 — Contracts and fixtures

- Implement shared schemas.
- Implement investigation states.
- Create deterministic fixtures.
- Add contract tests.

**Commit after:** model validation and state-transition tests pass.

### Phase 2 — Read-only evidence agents

- Implement health client and Telemetry-Watchdog.
- Implement GitHub client and Commit-Detective.
- Implement OSV client and Security-Investigator.
- Add unit and fixture-based integration tests.

**Commit after:** known bad commit and vulnerability are detected from fixtures.

### Phase 3 — Orchestration and ASI:One UX

- Implement ACP.
- Implement intent extraction.
- Coordinate read-only agents.
- Implement intake, progress, and incident cards.
- Support partial failures.

**Commit after:** a local conversation reaches an evidence-backed incident report.

### Phase 4 — Remediation

- Implement confirmation flow.
- Implement dry-run remediation.
- Implement GitHub PR creation.
- Add idempotency and conflict handling.
- Add confirmation and resolution cards.

**Commit after:** one approved request creates exactly one valid demo PR.

### Phase 5 — Agentverse deployment

- Deploy and validate workers.
- Deploy and register the Orchestrator.
- Verify ASI:One discovery.
- Run the full shared-chat workflow.

**Commit after:** deployment configuration and runbook match the working deployment.

### Phase 6 — Submission polish

- Finish README.
- Add architecture diagram.
- Add agent names and addresses.
- Write setup, test, deployment, and demo instructions.
- Record the 3–5 minute demo.
- Collect Agentverse URLs, GitHub URL, and ASI:One shared-chat URL.

**Commit after:** a clean clone can follow the README successfully.

### Phase 7 — Optional bonuses

- Payment Protocol.
- Scheduled monitoring.
- Sandbox auto-merge.

**Commit each optional feature separately. Never mix it into the stable core commit.**

---

## 14. Commit and Push Strategy

Do not wait until tomorrow to create one large commit. Create local commits tonight at every green validation gate. Local commits do not require publishing the repository and give safe restore points. Pushing the complete history tomorrow is acceptable.

Recommended commits:

1. `chore: scaffold sentinel ops and secure configuration`
2. `feat: add typed agent contracts and investigation state`
3. `feat: add telemetry commit and security evidence agents`
4. `feat: orchestrate investigations through ASI One`
5. `feat: add confirmed idempotent remediation pull requests`
6. `deploy: register agents and document Agentverse setup`
7. `docs: finalize hackathon demo and submission guide`
8. Optional: `feat: add specialist agent payments`

### When to commit

Commit only when all of the following are true:

- The phase’s focused tests pass.
- No secret or `.env` file is staged.
- The service starts or imports successfully.
- The README is updated when behavior or setup changed.
- The diff contains one coherent milestone.

Before each commit, inspect the staged file list and staged diff. Stage specific files rather than blindly staging the entire repository. Never commit agent seeds, API keys, wallet keys, GitHub tokens, logs, or recorded private responses.

### Tonight versus tomorrow

**Tonight / build period:** make local milestone commits as the system becomes stable. Do not rewrite or squash them during active development.

**Tomorrow / submission period:**

1. Run the complete test suite.
2. Run a secret scan.
3. Perform the clean-clone setup test.
4. Run the ASI:One judge workflow twice.
5. Update real Agentverse addresses and public URLs.
6. Commit only the deployment/submission changes.
7. Push the existing commit history.
8. Tag the demonstrated revision, for example `hackathon-demo-v1`.
9. Record the video from that exact revision.
10. Do not add untested features after recording.

---

## 15. README and Submission Checklist

The public repository must contain:

- Problem, target user, and executable outcome.
- Architecture diagram.
- Names, responsibilities, and addresses of submitted agents.
- Exact local setup instructions.
- Exact test instructions.
- Deployment instructions.
- Required environment-variable names.
- Security and permission model.
- Known limitations.
- Demo scenario and example prompt.
- ASI:One shared-chat URL.
- Agentverse profile URLs.
- Demo video URL.
- Required badges:

```markdown
![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)
```

Before submission, confirm:

- [ ] At least one agent is registered on Agentverse.
- [ ] Sentinel-Orchestrator is discoverable through ASI:One.
- [ ] ACP is implemented and the manifest is published.
- [ ] The full primary workflow runs within ASI:One.
- [ ] Worker-agent communication is visible in logs or the final audit trail.
- [ ] One real or sandbox GitHub PR is created from the chat.
- [ ] Confirmation is required before GitHub writes.
- [ ] Health is checked before and after remediation.
- [ ] External failures return clear partial results.
- [ ] The public repository contains no secrets.
- [ ] The README includes agent names and addresses.
- [ ] The public shared-chat URL works in a fresh session.
- [ ] The demo video is 3–5 minutes.
- [ ] The demonstrated commit is tagged and unchanged.

---

## 16. Demo Script

Target duration: approximately four minutes.

### 0:00–0:30 — Problem

Explain that small teams lose time switching between monitoring, Git history, security scanners, and pull-request tooling during incidents.

### 0:30–1:00 — Intent and discovery

Open a fresh ASI:One conversation, locate Sentinel-Orchestrator, and enter the investigation request. Confirm the intake card.

### 1:00–2:00 — Multi-agent investigation

Show the health failure, candidate commits, dependency finding, and code-security finding. Briefly expose that independent Fetch.ai agents produced the evidence.

### 2:00–2:45 — Decision

Show the incident report, evidence-backed confidence, and rollback/patch choices. Select the safest option and review the confirmation card.

### 2:45–3:30 — Action

Confirm the action. Show the real GitHub PR and its generated audit description.

### 3:30–4:00 — Verified outcome

Show tests or validation, the new health result, the final resolution card, and optional agent-payment settlement.

Do not spend the demo reading code or explaining every library. Demonstrate the user’s journey and the produced outcome.

---

## 17. Definition of Done

Sentinel-Ops is hackathon-ready only when a judge can start from a fresh ASI:One conversation, provide the demo repository and endpoint, receive real multi-agent evidence, approve a remediation, obtain a valid PR URL, and see an honest post-action verification result without using an external frontend.

If Payment Protocol, auto-merge, continuous monitoring, or advanced scanners threaten this path, disable them and submit the stable core.
