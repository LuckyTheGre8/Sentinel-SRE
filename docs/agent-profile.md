# Sentinel-Orchestrator

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

Investigate a public GitHub repository and an HTTPS health endpoint inside ASI:One.
Provide the repository as owner/name and the service's HTTPS health URL. Review the
intake card, then start the investigation. Sentinel-Ops probes the endpoint, ranks
recent commits, checks supported dependencies against OSV, and returns an
evidence-backed report with confidence and coverage limits.

Example: "Investigate owner/repository at https://your-service.example/health over 24 hours."
Use your own real repository and endpoint. Missing details are requested.

Commit correlation is not proof of causation. Narrow static analysis is not a full
security audit. Provider failures produce partial results. This live version performs
read-only investigations; it does not modify repositories or merge code.

ASI:One handles intent classification and evidence selection. It receives redacted
intent text and structured health/candidate statistics, not raw repository files or
health response bodies. No payment protocol or automatic merging is enabled.

The agent runs on the operator's PC via Agentverse Mailbox and is available while
that process and PC are running.
