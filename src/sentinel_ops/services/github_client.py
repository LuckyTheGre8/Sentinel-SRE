"""GitHub-shaped recorded fixtures behind the future API's typed read boundary."""

import json
from pathlib import Path
from typing import Protocol

from sentinel_ops.schemas import Commit


class GitHubClient(Protocol):
    async def commits(self, repository: str, branch: str, limit: int) -> list[Commit]: ...
    async def files(self, repository: str, revision: str) -> dict[str, str]: ...
    async def default_branch(self, repository: str) -> str: ...


class RecordedGitHubClient:
    def __init__(self, fixture: Path):
        self.data = json.loads(fixture.read_text(encoding="utf-8"))

    def check_repository(self, repository: str):
        if repository != self.data["repository"]:
            raise ValueError("Repository not present in recorded fixture")

    async def default_branch(self, repository: str) -> str:
        self.check_repository(repository)
        return self.data["default_branch"]

    async def commits(self, repository: str, branch: str, limit: int) -> list[Commit]:
        self.check_repository(repository)
        if branch != self.data["default_branch"]:
            raise ValueError("Branch unavailable")
        return [
            Commit(
                sha=c["sha"],
                timestamp=c["commit"]["committer"]["date"],
                message=c["commit"]["message"],
                url=c["html_url"],
                files={f["filename"]: f.get("patch", "") for f in c["files"]},
            )
            for c in self.data["commits"][:limit]
        ]

    async def files(self, repository: str, revision: str) -> dict[str, str]:
        self.check_repository(repository)
        if revision not in {c["sha"] for c in self.data["commits"]}:
            raise ValueError("Revision unavailable")
        return dict(self.data["files"])
