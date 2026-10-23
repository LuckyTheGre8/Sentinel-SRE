# Sentinel-Ops — Codex GPT-6 Astra Prompt Pack

Use these prompts in order in the same Codex chat and the same repository. Attach or place `sentinel_ops_astra_build_spec.md` in the repository before starting.

Recommended model: **GPT-6 Astra**
Recommended reasoning: **High**

Do not paste all prompts at once. Let Codex finish and verify each phase before sending the next prompt.

---

## Prompt 0 — Orient and Plan

```text
We are building Sentinel-Ops for Fetch-A-Thon 3.0 in this repository.

Read `sentinel_ops_astra_build_spec.md` completely and inspect the current repository. Treat the live repository as the source of truth. Use the official Fetch.ai documentation to verify current uAgents, Agentverse, ACP, ASI:One Interactive Cards, and Payment Protocol interfaces; do not invent SDK methods or deployment commands.

First perform a read-only preflight. Report:
1. The current repository state and relevant files.
2. The proposed implementation phases and dependencies.
3. Decisions or assumptions that require my input.
4. Credentials or external accounts that will eventually be needed, without asking me to paste secrets into chat.
5. The exact first-phase files you intend to create or change.
6. The validation gate for the first phase.

Do not modify files, install dependencies, commit, push, deploy, or perform external writes in this turn. Keep the plan focused on the required incident-to-PR workflow. Payments, auto-merge, and advanced monitoring are optional until the core workflow passes end to end.
```

After reviewing the response, send Prompt 1.

---

## Prompt 1 — Repository Foundation and Contracts

```text
Proceed with Phases 0 and 1 from `sentinel_ops_astra_build_spec.md`: repository safety, project scaffolding, configuration, shared schemas, investigation state, deterministic fixtures, and contract tests.

Requirements:
- Preserve any valid existing work.
- Use a pinned, compatible Python toolchain.
- Create `.gitignore` before any generated or secret-bearing files.
- Create `.env.example` with variable names only.
- Never place agent seeds, API keys, wallet keys, GitHub tokens, or real credentials in source, fixtures, logs, or documentation.
- Implement typed contracts with `investigation_id` and structured errors.
- Implement and test valid and invalid state transitions.
- Add the required hackathon badges to the README.
- Run the focused tests and relevant static checks.

Do not implement worker integrations, deploy, commit, push, or contact external services in this phase.

Before finishing:
1. Inspect the complete diff.
2. Report the files changed.
3. Report observed test results, not expected results.
4. Identify remaining risks or assumptions.
5. State whether the validation gate passed.
6. Recommend a commit message, but do not commit until I explicitly approve it.

Stop after this phase.
```

Suggested commit after it passes:

```text
chore: scaffold sentinel ops and add typed investigation contracts
```

---

## Prompt 2 — Read-Only Evidence Agents

```text
Implement Phase 2 from `sentinel_ops_astra_build_spec.md`: Telemetry-Watchdog, Commit-Detective, and Security-Investigator, including their service clients and tests.

Use current official Fetch.ai and third-party API documentation. Do not invent response fields. Keep external APIs behind small typed clients so recorded fixtures can test behavior deterministically.

Required behavior:
- Telemetry-Watchdog returns bounded, sanitized health evidence and distinguishes HTTP failure, timeout, DNS, TLS, and connection errors.
- Its URL handling protects against unsafe schemes, metadata endpoints, redirects, and private networks except in explicit local demo mode.
- Commit-Detective retrieves bounded commit and diff evidence, ranks candidate commits without blaming authors, and clearly distinguishes correlation from proof.
- Security-Investigator parses supported manifests, queries OSV batches, performs the narrow documented code checks, redacts suspected secrets, and never invents fixed versions.
- Incident likelihood and security severity remain separate.
- External timeouts produce structured partial results rather than false success.

Create deterministic fixtures containing one known bad commit and one known vulnerability. Add unit, contract, and fixture-based integration tests. If live network access is unavailable, validate the client contracts with recorded fixtures and clearly report that limitation.

Do not implement repository writes, remediation, deployment, commits, pushes, payments, or auto-merge.

Run focused tests and relevant checks. Inspect the diff. Report changed files, observed evidence, limitations, validation-gate status, and a recommended commit message. Stop after this phase.
```

Suggested commit:

```text
feat: add telemetry git and security evidence agents
```

---

## Prompt 3 — Orchestrator, ACP, and ASI:One UX

```text
Implement Phase 3 from `sentinel_ops_astra_build_spec.md`: Sentinel-Orchestrator, Agent Chat Protocol support, intent extraction, worker coordination, evidence synthesis, and the read-only ASI:One card workflow.

Verify all Fetch.ai-specific interfaces against current official documentation before coding. Use ASI:One reasoning as a core part of intent understanding and evidence ranking, while ensuring factual claims are grounded only in structured worker evidence.

Required workflow:
1. Receive and acknowledge the ACP chat message.
2. Extract repository, branch, endpoint, lookback window, and permission mode.
3. Ask for missing required values without inventing them.
4. Render a supported intake/review interaction.
5. Run telemetry and commit analysis concurrently where safe.
6. Run security analysis on the relevant files and dependencies.
7. Return a report containing health state, ranked hypothesis, confidence, evidence, incident-related security findings, unrelated security debt, and warnings.
8. Continue honestly when one worker fails and mark missing evidence as unavailable.

Implement only card components and actions supported by the current ASI:One Interactive Cards specification. Keep card rendering isolated from investigation logic. Add tests for ACP acknowledgements, intent extraction, message correlation, partial failure, contradictory evidence, and unsupported input.

Do not create PRs, deploy, commit, push, enable payments, or merge code in this phase.

Run focused tests and a local read-only conversation simulation. Inspect the diff. Report changed files, observed results, risks, validation-gate status, and a recommended commit message. Stop after the read-only incident report works.
```

Suggested commit:

```text
feat: orchestrate incident investigations through ASI One
```

---

## Prompt 4 — Remediation and GitHub PR Safety

```text
Implement Phase 4 from `sentinel_ops_astra_build_spec.md`: Remediation-Executor, explicit confirmation, bounded rollback and patch proposals, idempotent GitHub PR creation, validation, and resolution reporting.

Begin with a dry-run implementation and tests. Use a dedicated demo repository for any live integration. Do not use or request broad production permissions.

Required controls:
- No repository write before explicit user confirmation.
- Each approved action has a stable idempotency key.
- Repeating the same action returns the existing PR rather than creating another.
- Never force push or push directly to the default branch.
- Automatic merge is disabled.
- Patch mode modifies only the approved file set and rejects path traversal or oversized patches.
- Model-generated text is never executed as an arbitrary shell command.
- Revert conflicts return a non-destructive failure.
- “PR created” and “incident resolved” remain separate states.
- The PR body contains evidence, confidence, tests, rollback instructions, and the investigation ID.

Implement the confirmation and resolution interactions using supported ASI:One card features. Add tests for missing confirmation, duplicate execution, conflicts, unauthorized files, GitHub errors, and successful PR creation with a mocked or sandbox client.

Do not deploy, push, commit, merge, or enable payments. Do not perform a live GitHub write unless I separately authorize it and the target repository is explicitly identified.

Run focused tests and the dry-run flow. Inspect the diff. Report changed files, observed results, risks, validation-gate status, and a recommended commit message. Stop after the safe PR workflow passes locally.
```

Suggested commit:

```text
feat: add confirmed idempotent remediation pull requests
```

---

## Prompt 5 — Deterministic Demo and Full Local Verification

```text
Implement the deterministic demo environment and complete the local end-to-end workflow described in `sentinel_ops_astra_build_spec.md`.

Create or finish the toy service with:
- A healthy `/health` state returning 200.
- A known bad commit or scenario returning 503.
- One bounded security issue or vulnerable pinned dependency.
- A rollback or patch path that restores the healthy state.

Wire the real project interfaces to the demo; do not create a separate fake architecture. Provide one documented local command sequence that starts the required components and one smoke-test command that runs the judge path.

Run the complete local flow at least twice:
1. Investigate the failing endpoint.
2. Rank the intended bad commit first.
3. Detect the intended vulnerability.
4. Reach explicit remediation confirmation.
5. Create exactly one sandbox/dry-run PR result for repeated identical confirmation.
6. Verify the recovered health state.

Fix failures within this phase and rerun affected tests. Do not deploy, commit, push, enable payments, or perform unapproved external writes.

Inspect the final diff and configuration for secrets. Report exact commands, observed outputs, changed files, remaining risks, validation-gate status, and the recommended commit boundary. Stop when the local end-to-end gate passes or explain the precise blocker.
```

Suggested commit:

```text
test: add deterministic incident to recovery demo
```

---

## Prompt 6 — Commit Checkpoint

Use this after each completed phase if you want Codex to create the local commit.

```text
Prepare the completed phase for a local commit.

Before committing:
1. Inspect `git status` and the full staged and unstaged diff.
2. Run the focused tests and `git diff --check`.
3. Check staged paths and content for `.env` files, tokens, keys, agent seeds, wallet secrets, private URLs, logs, caches, or generated credentials.
4. Stage only files belonging to the completed phase.
5. Show me the proposed staged file list, validation evidence, and exact commit message.

Do not push, deploy, merge, tag, rewrite history, or include unrelated files. Wait for my explicit approval before creating the commit.
```

After Codex shows the checkpoint and you approve it:

```text
Approved. Create the local commit exactly as proposed. Do not push or begin the next phase. Report the resulting commit hash and confirm the remaining working-tree state.
```

---

## Prompt 7 — Deployment Preflight

```text
Prepare Sentinel-Ops for a smooth Agentverse and ASI:One deployment using the deployment runbook in `sentinel_ops_astra_build_spec.md`.

First perform a read-only deployment preflight. Verify the current official Fetch.ai documentation for:
- uAgents deployment requirements.
- Agentverse registration and agent addresses.
- ACP implementation and manifest publishing.
- ASI:One discoverability and shared-chat behavior.
- ASI:One Interactive Cards support.
- Current environment and secret configuration.

Then:
1. Compare the repository implementation with those current requirements.
2. Identify exact gaps or outdated assumptions.
3. Run local tests, configuration validation, and the smoke test.
4. Prepare deployment configuration and documentation if changes are required, but do not deploy yet.
5. List the accounts, credentials, URLs, and user approvals needed, without asking me to paste secrets into chat or writing secrets to the repository.
6. Provide the exact deployment order and rollback method.

Do not deploy, register agents, push, commit, publish manifests, create PRs, or make other external writes in this turn. Stop with a deployment-readiness report and the precise actions requiring my authorization.
```

---

## Prompt 8 — Deploy to Agentverse and Verify ASI:One

Send this only after reviewing Prompt 7’s preflight and securely configuring the required credentials.

```text
I authorize deployment of Sentinel-Ops to the explicitly configured Fetch.ai demo environment and only the dedicated demo GitHub repository. Follow the validated deployment order from the preflight.

Deploy and verify one component at a time:
1. Telemetry-Watchdog.
2. Commit-Detective.
3. Security-Investigator.
4. Remediation-Executor in dry-run/read-only mode first, then `create_pr` mode only for the dedicated demo repository.
5. Sentinel-Orchestrator with ACP and its published manifest.

After each worker deployment, record its address, send a known request, validate the typed response, and stop to fix any failure before continuing. After deploying the Orchestrator, verify Agentverse registration, ASI:One discovery, message acknowledgements, worker routing, and supported card actions.

Do not expose credentials in commands, logs, documentation, or your response. Do not enable automatic merging or payments. Do not push source code or create a Git commit unless I separately request it.

Finally, run the complete ASI:One judge workflow against the demo repository and endpoint. Report:
- Agent profile URLs and addresses.
- ASI:One discovery result.
- Worker verification evidence.
- PR result, if I confirm the card action.
- Before/after health evidence.
- Any manual steps still required.
- Exact rollback steps for the deployment.

Do not claim success for any check you did not observe.
```

---

## Prompt 9 — Final Hackathon Audit

```text
Perform a release-candidate audit of Sentinel-Ops against `sentinel_ops_astra_build_spec.md` and the current official Fetch-A-Thon 3.0 hackpack.

Review the live repository and deployed configuration. Do not rely on earlier summaries. Check:
- Functional incident-to-PR-to-verification workflow.
- Agent-to-agent communication.
- Agentverse registration and discoverability.
- ACP and manifest behavior.
- ASI:One-only primary workflow.
- Interactive-card actions.
- Error handling, retries, partial results, and idempotency.
- Secret handling and least privilege.
- README setup, tests, agent names, addresses, badges, and limitations.
- Public URLs required for submission.
- Demo reproducibility from a fresh conversation.

Run the full test suite, static checks, secret scan, clean-start smoke test, and `git diff --check`. If safe local defects are found, fix them and rerun affected checks. Do not add new product features.

Return findings ordered by severity with file references and observed evidence. Then provide:
1. A pass/fail decision for each mandatory hackathon requirement.
2. The exact remaining manual actions.
3. The recommended final commit message.
4. The recommended demo tag.
5. A freeze recommendation stating what must not change after the video is recorded.

Do not commit, push, deploy, tag, merge, or modify external state without separate approval.
```

Suggested final commit:

```text
docs: finalize Fetch-A-Thon demo and submission
```

Suggested tag after the demonstrated revision is verified:

```text
hackathon-demo-v1
```

---

## Prompt 10 — Optional Payment Protocol

Use this only if the core workflow is already deployed and repeatably passing.

```text
The required Sentinel-Ops workflow is stable. Implement the optional Fetch.ai Payment Protocol integration described in `sentinel_ops_astra_build_spec.md` behind `PAYMENT_ENABLED=false` by default.

Verify the current official Payment Protocol documentation before editing. Implement a credible specialist-agent settlement flow with quote, authorization, completion, and settlement status. A failed or timed-out worker must not be represented as successful paid work. Payment failure must not break the free/demo incident workflow.

Use only test/sandbox assets and least-privilege credentials. Never store wallet secrets in source or logs. Add focused tests and documentation. Do not enable the feature in the deployed demo, deploy it, commit it, push it, or perform a real transaction without separate approval.

Run the relevant tests and report changed files, observed results, risks, validation-gate status, and a recommended isolated commit message. Stop after the optional feature is verified locally.
```

---

## Recovery Prompt — When a Phase Fails

```text
Do not continue to the next phase. Diagnose the current failure using the live repository and actual command output.

Identify:
1. The first root-cause failure rather than downstream symptoms.
2. Whether it is caused by our code, configuration, credentials, permissions, network access, or an external service.
3. The smallest safe fix.
4. Tests that reproduce the failure before the fix and pass afterward.

Implement only the bounded fix if it does not require new credentials, broader permissions, destructive actions, or external writes. Rerun the affected validation gate and report observed evidence. If user action is required, stop with one precise request and preserve all working state.

Do not weaken tests, replace real checks with unconditional mocks, expose secrets, reset the repository, delete unrelated work, commit, push, or deploy.
```

---

## Final Push Prompt — Tomorrow

Use this only after the final audit passes and you are ready to publish.

```text
Prepare the verified Sentinel-Ops release for public hackathon submission.

Before any push:
1. Inspect repository status and commit history.
2. Confirm the full test suite, smoke test, secret scan, and `git diff --check` pass.
3. Confirm `.env`, tokens, keys, seeds, wallet data, private logs, and credentials are not tracked anywhere in history being pushed.
4. Confirm README agent addresses and public URLs match the deployed agents.
5. Confirm the current revision is the exact revision used in the successful ASI:One demo.

Show me the readiness evidence, commits that will be pushed, remote and branch, and proposed tag. Wait for explicit approval before pushing or tagging. Do not rewrite history or force push.
```

After reviewing the report:

```text
Approved. Push the verified branch to the confirmed remote and create/push the `hackathon-demo-v1` tag at the demonstrated revision. Do not change or deploy anything afterward. Report the public repository URL, branch, tag, and final commit hash.
```
