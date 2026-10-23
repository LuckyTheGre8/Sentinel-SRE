from pathlib import Path

import pytest

from sentinel_ops.schemas import InvestigationRequest


def pytest_configure(config):
    (Path(__file__).resolve().parents[1] / ".local").mkdir(exist_ok=True)


@pytest.fixture
def request_data():
    return InvestigationRequest.model_validate_json(
        (Path(__file__).parent / "fixtures/investigation.json").read_text()
    )
