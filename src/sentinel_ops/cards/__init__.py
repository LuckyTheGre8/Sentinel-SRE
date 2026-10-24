"""Validated ASI:One card protocol v1 payloads, independent of worker logic."""

import json
from typing import Literal

from pydantic import Field, model_validator
from uagents_core.contrib.protocols.chat import ChatMessage, MetadataContent, TextContent

from sentinel_ops.schemas import Model


class CTA(Model):
    label: str
    selection: dict[str, str]
    primary: bool = False


class Row(Model):
    label: str
    value: str


class FormField(Model):
    name: str
    kind: Literal["text", "number", "email", "select", "checkbox"] = "text"
    label: str
    required: bool = True
    options: list[dict[str, str]] | None = None

    @model_validator(mode="after")
    def select_options(self):
        if self.kind == "select" and not self.options:
            raise ValueError("Select requires options")
        return self


class Form(Model):
    title: str
    fields: list[FormField]
    submit_cta: CTA


class Detail(Model):
    title: str
    summary_rows: list[Row]
    ctas: list[CTA] = Field(default_factory=list)


class Review(Model):
    title: str
    summary_rows: list[Row]
    approve_cta: CTA
    reject_cta: CTA


def card(narration: str, payload: Form | Detail | Review, terminal: bool = False) -> ChatMessage:
    kind = (
        "form"
        if isinstance(payload, Form)
        else "review"
        if isinstance(payload, Review)
        else "detail"
    )
    encoded = payload.model_dump_json(exclude_none=True)
    if len(encoded.encode()) > 65536:
        raise ValueError("Card exceeds 64 KiB")
    metadata = {
        "card_protocol_version": "1",
        "requires_card_interaction": "true",
        "card_kind": kind,
        "card_payload": encoded,
    }
    if terminal:
        metadata["is_terminal"] = "true"
    return ChatMessage(
        content=[
            TextContent(type="text", text=narration),
            MetadataContent(type="metadata", metadata=metadata),
        ]
    )


def validate_card(message: ChatMessage) -> dict:
    block = next(c for c in message.content if isinstance(c, MetadataContent))
    payload = json.loads(block.metadata["card_payload"])
    models: dict[str, type[Model]] = {"form": Form, "detail": Detail, "review": Review}
    model = models[block.metadata["card_kind"]]
    model.model_validate(payload)
    return payload


def intake(missing: list[str], simulated: bool = True) -> ChatMessage:
    return card(
        ("LOCAL SIMULATION: " if simulated else "") + "Provide and review investigation details.",
        Form(
            title="Investigation intake",
            fields=[FormField(name=x, label=x.replace("_", " ")) for x in missing],
            submit_cta=CTA(label="Review investigation", selection={"action": "intake"}),
        ),
    )


def review_intake(request, simulated: bool = True) -> ChatMessage:
    return card(
        "Confirm these inputs before collecting evidence.",
        Review(
            title="Start local investigation" if simulated else "Start live investigation",
            summary_rows=[
                Row(label=k, value=str(v)) for k, v in request.model_dump(mode="json").items()
            ],
            approve_cta=CTA(
                label="Start",
                selection={"action": "start", "investigation_id": str(request.investigation_id)},
            ),
            reject_cta=CTA(label="Cancel", selection={"action": "cancel"}),
        ),
    )


def progress() -> ChatMessage:
    return card(
        "Collecting evidence; no worker has completed yet.",
        Detail(
            title="Investigation progress",
            summary_rows=[
                Row(label=n, value="pending")
                for n in ["Endpoint", "Commits", "Dependencies", "Code"]
            ],
        ),
        terminal=True,
    )


def incident_report(
    report, simulated: bool = True, remediation_enabled: bool = True, patch_enabled: bool = True
) -> ChatMessage:
    rows = [
        Row(label="Health", value=report.health.state),
        Row(label="Hypothesis", value=report.hypothesis.summary),
        Row(label="Confidence", value=report.hypothesis.confidence),
        Row(label="Evidence", value=", ".join(report.hypothesis.evidence_ids)),
        Row(
            label="Incident-related security",
            value="; ".join(f.id for f in report.security.findings if f.related_to_incident)
            or "Not established",
        ),
        Row(
            label="Other security findings",
            value="; ".join(f.id for f in report.security.findings if not f.related_to_incident)
            or "None observed; see coverage warnings",
        ),
        Row(label="Warnings", value="; ".join(report.warnings)),
    ]
    actions = [
        CTA(label="View evidence", selection={"action": "evidence"}),
        CTA(label="Cancel", selection={"action": "cancel"}),
    ]
    if remediation_enabled and report.commits.success and report.commits.commits:
        actions.insert(0, CTA(label="Review rollback", selection={"action": "review_revert"}))
        if patch_enabled:
            actions.insert(1, CTA(label="Review patch", selection={"action": "review_patch"}))
    return card(
        ("LOCAL SIMULATION: " if simulated else "") + "Evidence-backed incident report.",
        Detail(title="Incident report", summary_rows=rows, ctas=actions),
    )


def confirmation(
    proposal, confirmation_id: str, idempotency_key: str, simulated: bool = True
) -> ChatMessage:
    selection = {
        "action": "confirm",
        "investigation_id": str(proposal.investigation_id),
        "proposal_id": str(proposal.proposal_id),
        "confirmation": confirmation_id,
        "idempotency_key": idempotency_key,
    }
    return card(
        "Explicit approval required. Creates a simulated PR only; no merge."
        if simulated
        else "Explicit approval creates one GitHub draft PR. Review the commit and files; no automatic merge.",
        Review(
            title="Confirm sandbox remediation" if simulated else "Confirm GitHub draft PR",
            summary_rows=[
                Row(label="Repository", value=proposal.repository),
                Row(label="Base branch", value=proposal.base_branch),
                Row(label="Action", value=proposal.action),
                Row(label="Files", value=", ".join(proposal.expected_files)),
                Row(label="Commit", value=proposal.commit_sha or "bounded patch"),
                Row(label="Tests", value=", ".join(proposal.tests)),
                Row(
                    label="Outcome",
                    value="Simulated PR, no merge"
                    if simulated
                    else "GitHub draft PR; no merge or deployment",
                ),
                Row(label="Risks", value="; ".join(proposal.risks)),
            ],
            approve_cta=CTA(
                label="Confirm and create simulated PR"
                if simulated
                else "Confirm and create draft PR",
                selection=selection,
            ),
            reject_cta=CTA(label="Cancel", selection={"action": "cancel"}),
        ),
    )


def resolution(result, initial, final, status: str) -> ChatMessage:
    return card(
        "Local sandbox verification result.",
        Detail(
            title="Resolution",
            summary_rows=[
                Row(label="PR", value=result.pr_url or "not created"),
                Row(label="Validation", value=result.validation),
                Row(label="Initial health", value=initial.state),
                Row(label="Final health", value=final.state),
                Row(label="Result", value=status),
                Row(
                    label="Latency (ms)",
                    value=f"{initial.probes[-1].latency_ms:.2f} -> {final.probes[-1].latency_ms:.2f}",
                ),
                Row(label="Investigation", value=str(result.investigation_id)),
            ],
        ),
        terminal=True,
    )
