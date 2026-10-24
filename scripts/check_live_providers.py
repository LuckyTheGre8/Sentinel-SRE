"""Explicit public-data provider smoke check; no repository writes or registration."""

import asyncio
from pathlib import Path

from sentinel_ops.runtime import load_settings
from sentinel_ops.schemas import CommitAnalysisResponse, Dependency, HealthCheckResponse
from sentinel_ops.services.asi1_client import ASI1ReasoningClient
from sentinel_ops.services.github_client import LiveGitHubClient
from sentinel_ops.services.health_client import PublicHealthClient
from sentinel_ops.services.osv_client import LiveOSVClient


async def main():
    settings = load_settings(Path.cwd())
    github = LiveGitHubClient()
    osv = LiveOSVClient()
    asi = ASI1ReasoningClient(
        settings.asi1_api_key.get_secret_value(), data_sharing=settings.data_sharing
    )
    checks = {
        "GitHub public repository": github.default_branch("fetchai/uAgents"),
        "OSV public package": osv.query_batch(
            [
                Dependency(
                    ecosystem="PyPI", name="requests", version="2.0.0", file="requirements.txt"
                )
            ]
        ),
        "ASI:One structured reasoning": asi.synthesize(
            HealthCheckResponse(), CommitAnalysisResponse()
        ),
        "Public HTTPS probe": PublicHealthClient().probe("https://api.github.com/", 10),
    }
    results = await asyncio.gather(*checks.values(), return_exceptions=True)
    failed = False
    for name, value in zip(checks, results, strict=True):
        ok = not isinstance(value, BaseException)
        if name == "Public HTTPS probe":
            ok = ok and value.failure is None and value.status == 200
        if name == "OSV public package":
            ok = ok and bool(value and value[0])
        print(name + ": " + ("PASS" if ok else "FAIL (no provider payload displayed)"))
        failed |= not ok
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
