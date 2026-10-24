"""Typed GitHub reads with a recorded fixture implementation for the local demo."""

import asyncio
import base64
import json
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

from sentinel_ops.schemas import Commit, safe_path
from sentinel_ops.services.http_api import request_json


class GitHubClient(Protocol):
    async def commits(self, repository: str, branch: str, limit: int) -> list[Commit]: ...
    async def files(self, repository: str, revision: str) -> dict[str, str]: ...
    async def default_branch(self, repository: str) -> str: ...


class RecordedGitHubClient:
    simulated = True

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


class GitHubAPIError(OSError):
    """A bounded, non-sensitive GitHub API failure."""


class LiveGitHubClient:
    """Read public or private repository evidence from GitHub's REST API."""

    simulated = False
    api_root = "https://api.github.com"
    max_json_bytes = 2 * 1024 * 1024

    def __init__(self, token: str | None = None, timeout: float = 10.0, transport=None):
        self.token = token
        self.timeout = timeout
        self.transport = transport

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def _get_json(self, path: str, params: dict | None = None):
        return await request_json(
            "GET",
            f"{self.api_root}{path}",
            headers=self._headers(),
            params=params,
            timeout=self.timeout,
            max_bytes=self.max_json_bytes,
            transport=self.transport,
        )

    @staticmethod
    def _repository(repository: str) -> str:
        parts = repository.split("/")
        if len(parts) != 2 or any(not p or p in {".", ".."} for p in parts):
            raise ValueError("Repository must be owner/name")
        if any(not all(c.isalnum() or c in "-_." for c in p) for p in parts):
            raise ValueError("Invalid repository name")
        return "/".join(quote(p, safe="-_.") for p in parts)

    async def default_branch(self, repository: str) -> str:
        repo = self._repository(repository)
        data = await self._get_json(f"/repos/{repo}")
        branch = data.get("default_branch")
        if not isinstance(branch, str) or not branch or len(branch) > 200:
            raise GitHubAPIError("GitHub repository response was invalid")
        return branch

    async def commits(self, repository: str, branch: str, limit: int) -> list[Commit]:
        repo = self._repository(repository)
        if not 1 <= limit <= 50 or not branch or len(branch) > 200:
            raise ValueError("Commit query is outside its bounds")
        data = await self._get_json(
            f"/repos/{repo}/commits",
            {"sha": branch, "per_page": limit},
        )
        if not isinstance(data, list):
            raise GitHubAPIError("GitHub commit response was invalid")

        semaphore = asyncio.Semaphore(5)

        async def details(item):
            sha = item.get("sha")
            if not isinstance(sha, str) or len(sha) != 40:
                raise GitHubAPIError("GitHub commit response was invalid")
            async with semaphore:
                detail = await self._get_json(f"/repos/{repo}/commits/{quote(sha, safe='')}")
            raw_commit = item.get("commit", {})
            files = {}
            budget = 8192
            for changed in detail.get("files", []):
                path = changed.get("filename")
                if not isinstance(path, str):
                    continue
                try:
                    safe_path(path)
                except ValueError:
                    continue
                patch_text = changed.get("patch", "")
                if not isinstance(patch_text, str):
                    continue
                encoded = patch_text.encode("utf-8")[:budget]
                files[path] = encoded.decode("utf-8", errors="ignore")
                budget -= len(encoded)
                if budget <= 0:
                    break
            return Commit(
                sha=sha,
                timestamp=raw_commit.get("committer", {}).get("date"),
                message=raw_commit.get("message", "")[:4096],
                url=item.get("html_url", ""),
                files=files,
            )

        return await asyncio.gather(*(details(item) for item in data[:limit]))

    async def files(self, repository: str, revision: str) -> dict[str, str]:
        """Return a bounded set of safe text files at a revision for security analysis."""
        repo = self._repository(repository)
        if len(revision) != 40 or any(c not in "0123456789abcdef" for c in revision.lower()):
            raise ValueError("Revision must be a commit SHA")
        tree = await self._get_json(
            f"/repos/{repo}/git/trees/{quote(revision)}", {"recursive": "1"}
        )
        entries = tree.get("tree", [])
        if not isinstance(entries, list) or tree.get("truncated"):
            raise GitHubAPIError("GitHub tree response was invalid")
        selected = []
        for entry in entries:
            path = entry.get("path")
            if entry.get("type") != "blob" or not isinstance(path, str):
                continue
            try:
                safe_path(path)
            except ValueError:
                continue
            supported = path.endswith((".py", "/Dockerfile")) or Path(path).name in {
                "requirements.txt",
                "pyproject.toml",
                "package.json",
                "package-lock.json",
                "go.mod",
                "pom.xml",
                "Dockerfile",
            }
            if (
                supported
                and entry.get("mode") != "120000"
                and entry.get("size", self.max_json_bytes + 1) <= 65536
            ):
                selected.append(path)
        if len(selected) > 100:
            raise GitHubAPIError("Security file scope exceeds 100 files")
        semaphore = asyncio.Semaphore(8)

        async def content(path: str):
            async with semaphore:
                encoded_path = "/".join(quote(part, safe="-_.") for part in path.split("/"))
                blob = await self._get_json(
                    f"/repos/{repo}/contents/{encoded_path}", {"ref": revision}
                )
            if blob.get("encoding") != "base64" or not isinstance(blob.get("content"), str):
                return path, None
            try:
                raw = base64.b64decode(blob["content"], validate=False)
                if len(raw) > 65536 or b"\0" in raw:
                    return path, None
                return path, raw.decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                return path, None

        results = await asyncio.gather(*(content(path) for path in selected))
        return {path: value for path, value in results if value is not None}
