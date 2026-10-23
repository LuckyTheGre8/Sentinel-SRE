import io
import logging
from datetime import datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from sentinel_ops.config import Settings
from sentinel_ops.logging import RedactingFormatter, redact
from sentinel_ops.schemas import AgentError, InvestigationContext, Response, Status
from sentinel_ops.state import TRANSITIONS, StateStore


@pytest.mark.parametrize(
    "values",
    [
        {"payment_enabled": True},
        {"sandbox_auto_merge": True},
        {"external_writes": True},
        {"timeout_seconds": 0},
        {"timeout_seconds": 11},
        {"mode": "production"},
        {"unknown_setting": "bad"},
    ],
)
def test_invalid_configuration(values):
    with pytest.raises(ValidationError):
        Settings(**values)


def test_confined_database(tmp_path):
    with pytest.raises(ValueError):
        Settings(database=Path("../escape.db")).confined_database(tmp_path)


def test_fixture_and_persistence(tmp_path, request_data):
    store = StateStore(tmp_path / "state.db")
    ctx = InvestigationContext(**request_data.model_dump(), session_id="local-user")
    store.create(ctx)
    store.transition(ctx.investigation_id, Status.COLLECTING)
    store.close()
    reopened = StateStore(tmp_path / "state.db")
    assert reopened.get(ctx.investigation_id).status == Status.COLLECTING
    with pytest.raises(ValueError):
        reopened.transition(ctx.investigation_id, Status.RESOLVED)
    reopened.close()


@pytest.mark.parametrize("source", list(Status))
@pytest.mark.parametrize("target", list(Status))
def test_all_transitions(tmp_path, request_data, source, target):
    store = StateStore(tmp_path / "state.db")
    ctx = InvestigationContext(**request_data.model_dump(), session_id="test", status=source)
    store.create(ctx)
    if target in TRANSITIONS[source]:
        assert store.transition(ctx.investigation_id, target).status == target
    else:
        with pytest.raises(ValueError):
            store.transition(ctx.investigation_id, target)
    store.close()


def test_contracts_reject_invalid_response():
    with pytest.raises(ValidationError):
        Response(agent_name="test", success=False)
    with pytest.raises(ValidationError):
        Response(agent_name="test", started_at=datetime(2026, 1, 1))
    with pytest.raises(ValidationError):
        Response(agent_name="test", investigation_id="not-a-uuid")
    assert not Response(
        agent_name="test", success=False, error=AgentError(code="timeout", message="Unavailable")
    ).success


def test_redaction_including_formatted_exception():
    sensitive = "synthetic-" + "credential-value"
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(RedactingFormatter("%(message)s"))
    logger = logging.Logger("test")
    logger.addHandler(handler)
    logger.warning("Authorization: Bearer %s", sensitive)
    try:
        raise ValueError(f"password={sensitive}")
    except ValueError:
        logger.exception("failed")
    assert sensitive not in stream.getvalue()
    assert "REDACTED" in stream.getvalue()
    assert sensitive not in redact(f"https://example.test/?token={sensitive}")
