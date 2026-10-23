import json

import pytest

from sentinel_ops.agents.remediation_executor import BAD_COMMIT, RemediationExecutor
from sentinel_ops.schemas import (
    Evidence,
    InvestigationContext,
    RemediationExecutionRequest,
    Status,
    safe_path,
)
from sentinel_ops.services.sandbox_github import SandboxGitHubClient
from sentinel_ops.state import StateStore


def setup(tmp_path, request_data):
    store = StateStore(tmp_path / "state.db")
    context = InvestigationContext(
        **request_data.model_dump(), session_id="owner", status=Status.AWAITING
    )
    store.create(context)
    client = SandboxGitHubClient(store)
    client.initialize(
        {"config.json": '{"healthy": false}\n', "requirements.txt": "demo-vulnerable==1.0.0\n"}
    )
    executor = RemediationExecutor(store, client)
    proposal, nonce, key = executor.propose(
        context.investigation_id,
        "owner",
        "revert_commit",
        [Evidence(id="health:0", source="local", summary="503")],
        "medium",
        BAD_COMMIT,
    )
    request = RemediationExecutionRequest(
        investigation_id=context.investigation_id,
        proposal_id=proposal.proposal_id,
        session_id="owner",
        confirmation=nonce,
        idempotency_key=key,
    )
    return store, client, executor, proposal, request


@pytest.mark.parametrize(
    "field,value", [("confirmation", ""), ("session_id", "other"), ("idempotency_key", "changed")]
)
async def test_confirmation_required(tmp_path, request_data, field, value):
    store, client, executor, proposal, request = setup(tmp_path, request_data)
    setattr(request, field, value)
    result = await executor.execute(request)
    assert not result.success and client.count() == 0
    assert json.loads(client.files()["config.json"])["healthy"] is False
    store.close()


async def test_duplicate_confirmation_survives_restart(tmp_path, request_data):
    store, client, executor, proposal, request = setup(tmp_path, request_data)
    first = await executor.execute(request)
    assert first.success and client.count() == 1
    assert store.get(request.investigation_id).status == Status.VERIFYING
    assert json.loads(client.files()["config.json"])["healthy"] is False
    store.close()
    store = StateStore(tmp_path / "state.db")
    client = SandboxGitHubClient(store)
    replay = await RemediationExecutor(store, client).execute(request)
    assert first == replay and client.count() == 1
    body = store.db.execute("SELECT body FROM sandbox_prs").fetchone()[0]
    for word in ["Evidence", "Confidence", "Validation", "Rollback", str(request.investigation_id)]:
        assert word in body
    client.apply_local(request.idempotency_key)
    assert json.loads(client.files()["config.json"])["healthy"] is True
    client.apply_local(request.idempotency_key)
    store.close()


async def test_conflicts_no_partial_write(tmp_path, request_data):
    store, client, executor, proposal, request = setup(tmp_path, request_data)
    with store.db:
        store.db.execute("UPDATE sandbox_files SET content='changed' WHERE path='requirements.txt'")
    before = client.files()
    result = await executor.execute(request)
    assert not result.success and client.count() == 0 and client.files() == before
    store.close()


@pytest.mark.parametrize(
    "path",
    ["../evil", "/absolute", "C:/evil", "x\\y", ".git/config", ".env", "a/../b", "trailing."],
)
def test_path_traversal_rejected(path):
    with pytest.raises(ValueError):
        safe_path(path)


async def test_unapproved_files_and_oversize(tmp_path, request_data):
    store, client, executor, proposal, request = setup(tmp_path, request_data)
    proposal.replacements["unapproved.py"] = "bad"
    with pytest.raises(ValueError):
        await client.create_pr(proposal, "different", "body")
    del proposal.replacements["unapproved.py"]
    proposal.replacements["requirements.txt"] = "x" * 20000
    with pytest.raises(ValueError):
        await client.create_pr(proposal, "different", "body")
    assert client.count() == 0
    store.close()


async def test_changed_in_memory_proposal_cannot_change_approved_action(tmp_path, request_data):
    store, client, executor, proposal, request = setup(tmp_path, request_data)
    proposal.replacements["config.json"] = '{"healthy": false}'
    assert (await executor.execute(request)).success
    client.apply_local(request.idempotency_key)
    assert json.loads(client.files()["config.json"])["healthy"] is True
    store.close()


async def test_expired_and_superseded_proposals(tmp_path, request_data):
    store, client, executor, proposal, request = setup(tmp_path, request_data)
    raw = json.loads(store.read("proposal", str(proposal.proposal_id)))
    raw["expires"] = "2000-01-01T00:00:00+00:00"
    store.put("proposal", str(proposal.proposal_id), json.dumps(raw))
    assert (await executor.execute(request)).error.code == "expired_confirmation"
    executor.propose(request.investigation_id, "owner", "revert_commit", [], "medium", BAD_COMMIT)
    assert (await executor.execute(request)).error.code == "stale_proposal"
    assert client.count() == 0
    store.close()


async def test_patch_mode_and_backend_error(tmp_path, request_data):
    store, client, executor, proposal, request = setup(tmp_path, request_data)
    proposal, nonce, key = executor.propose(
        request.investigation_id,
        "owner",
        "apply_patch",
        [],
        "medium",
        replacements={"config.json": '{"healthy": true}'},
    )
    request.proposal_id, request.confirmation, request.idempotency_key = (
        proposal.proposal_id,
        nonce,
        key,
    )

    async def broken(*args):
        raise OSError("synthetic failure")

    client.create_pr = broken
    assert not (await executor.execute(request)).success
    assert client.count() == 0
    store.close()


async def test_successful_patch_and_pr_restart_reconciliation(tmp_path, request_data):
    store, client, executor, proposal, request = setup(tmp_path, request_data)
    proposal, nonce, key = executor.propose(
        request.investigation_id,
        "owner",
        "apply_patch",
        [],
        "medium",
        replacements={"config.json": '{"healthy": true}'},
    )
    request.proposal_id, request.confirmation, request.idempotency_key = (
        proposal.proposal_id,
        nonce,
        key,
    )
    # Emulate a process stopping after durable PR creation but before result persistence.
    store.transition(request.investigation_id, Status.EXECUTING)
    await client.create_pr(proposal, key, "simulated crash boundary")
    result = await executor.execute(request)
    assert result.success and client.count() == 1
    client.apply_local(key)
    assert json.loads(client.files()["config.json"])["healthy"]
    assert client.files()["requirements.txt"] == "demo-vulnerable==1.0.0\n"
    store.close()


@pytest.mark.parametrize("path", [".GIT/config", ".env.local", "CON", "x/NUL.txt", "a:b"])
def test_windows_special_paths(path):
    with pytest.raises(ValueError):
        safe_path(path)
