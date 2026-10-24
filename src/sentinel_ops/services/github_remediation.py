"""Confirmed GitHub draft PRs for bounded reverts of the current branch head."""

import base64
import re
from urllib.parse import quote

from sentinel_ops.agents.remediation_executor import RemediationExecutor, action_key
from sentinel_ops.schemas import RemediationProposal, Status, safe_path
from sentinel_ops.services.github_client import LiveGitHubClient
from sentinel_ops.services.http_api import APIError, request_json
from sentinel_ops.services.sandbox_github import digest


class GitHubRemediationClient(LiveGitHubClient):
    def __init__(self, token, repositories, **kwargs):
        if not token or not repositories:
            raise ValueError("GitHub write token and repository scope required")
        super().__init__(token, **kwargs)
        self.repositories = frozenset(repositories)

    async def call(self, method, path, body=None, params=None):
        return await request_json(
            method,
            self.api_root + path,
            headers=self._headers(),
            body=body,
            params=params,
            timeout=self.timeout,
            transport=self.transport,
        )

    async def file_text(self, repository, path, revision):
        safe_path(path)
        item = await self._get_json(
            f"/repos/{self._repository(repository)}/contents/{quote(path, safe='/')}",
            {"ref": revision},
        )
        if item.get("type") != "file" or item.get("encoding") != "base64":
            raise ValueError("Revert requires an existing text file")
        raw = base64.b64decode(item["content"])
        if len(raw) > 16384 or b"\0" in raw:
            raise ValueError("Revert file is binary or oversized")
        return raw.decode("utf-8")

    async def head(self, repository, branch):
        value = await self._get_json(
            f"/repos/{self._repository(repository)}/git/ref/heads/{quote(branch, safe='')}"
        )
        return value["object"]["sha"]

    def validate(self, proposal):
        expected = set(proposal.expected_files)
        if proposal.repository not in self.repositories:
            raise ValueError("Repository outside write scope")
        if not re.fullmatch(r"[0-9a-f]{40}", proposal.base_sha or ""):
            raise ValueError("Missing immutable base")
        if not expected or len(expected) != len(proposal.expected_files):
            raise ValueError("Empty or duplicate file set")
        if (
            set(proposal.replacements) != expected
            or set(proposal.expected_hashes) != expected
            or set(proposal.file_modes) != expected
        ):
            raise ValueError("Approved file set mismatch")
        if len({p.casefold() for p in expected}) != len(expected):
            raise ValueError("Case-colliding paths")
        if sum(len(p.encode()) + len(c.encode()) for p, c in proposal.replacements.items()) > 16384:
            raise ValueError("Revert exceeds 16 KiB")
        for path in expected:
            safe_path(path)
            if proposal.file_modes[path] not in {"100644", "100755"}:
                raise ValueError("Unsupported file mode")

    async def create_pr(self, proposal, key, body):
        self.validate(proposal)
        if key != action_key(proposal):
            raise ValueError("Idempotency key mismatch")
        repo = self._repository(proposal.repository)
        branch = "sentinel-ops/" + key
        marker = "sentinel-action:" + key
        existing = await self._get_json(
            f"/repos/{repo}/pulls",
            {
                "state": "all",
                "head": proposal.repository.split("/")[0] + ":" + branch,
                "base": proposal.base_branch,
                "per_page": 100,
            },
        )
        for item in existing:
            if marker in (item.get("body") or ""):
                return item["number"], item["html_url"]
        try:
            branch_sha = await self.head(proposal.repository, branch)
        except APIError as error:
            if error.status != 404:
                raise
            branch_sha = None
        if not branch_sha:
            if await self.head(proposal.repository, proposal.base_branch) != proposal.base_sha:
                raise ValueError("Base branch changed; review a new proposal")
            for path, expected_hash in proposal.expected_hashes.items():
                if (
                    digest(await self.file_text(proposal.repository, path, proposal.base_sha))
                    != expected_hash
                ):
                    raise ValueError("Approved baseline changed")
            base = await self._get_json(f"/repos/{repo}/git/commits/{proposal.base_sha}")
            tree = await self.call(
                "POST",
                f"/repos/{repo}/git/trees",
                {
                    "base_tree": base["tree"]["sha"],
                    "tree": [
                        {
                            "path": path,
                            "mode": proposal.file_modes[path],
                            "type": "blob",
                            "content": content,
                        }
                        for path, content in proposal.replacements.items()
                    ],
                },
            )
            commit = await self.call(
                "POST",
                f"/repos/{repo}/git/commits",
                {
                    "message": marker,
                    "tree": tree["sha"],
                    "parents": [proposal.base_sha],
                },
            )
            try:
                await self.call(
                    "POST",
                    f"/repos/{repo}/git/refs",
                    {
                        "ref": "refs/heads/" + branch,
                        "sha": commit["sha"],
                    },
                )
            except APIError as error:
                if error.status != 422:
                    raise
            branch_sha = await self.head(proposal.repository, branch)
        # Validate a branch left behind by an interrupted attempt before reusing it.
        branch_commit = await self._get_json(f"/repos/{repo}/git/commits/{branch_sha}")
        if branch_commit["message"] != marker or [p["sha"] for p in branch_commit["parents"]] != [
            proposal.base_sha
        ]:
            raise ValueError("Existing branch does not match this approval")
        comparison = await self._get_json(
            f"/repos/{repo}/compare/{proposal.base_sha}...{branch_sha}"
        )
        if {f["filename"] for f in comparison["files"]} != set(proposal.expected_files):
            raise ValueError("Branch contains unapproved files")
        for path, content in proposal.replacements.items():
            if await self.file_text(proposal.repository, path, branch_sha) != content:
                raise ValueError("Branch differs from approved replacement")
        if await self.head(proposal.repository, proposal.base_branch) != proposal.base_sha:
            raise ValueError("Base branch changed; draft branch retained without a PR")
        result = await self.call(
            "POST",
            f"/repos/{repo}/pulls",
            {
                "title": f"Sentinel-Ops: revert {proposal.commit_sha[:8]}",
                "head": branch,
                "base": proposal.base_branch,
                "body": body + "\n<!-- " + marker + " -->",
                "draft": True,
            },
        )
        return result["number"], result["html_url"]


class LiveRemediationExecutor(RemediationExecutor):
    async def propose_revert(self, investigation_id, session, report):
        context = self.store.get(investigation_id)
        if (
            context.session_id != session
            or context.permission != "create_pr"
            or context.status != Status.AWAITING
        ):
            raise ValueError("Proposal not permitted")
        target = report.hypothesis.commit_sha
        if not target or target != await self.client.head(context.repository, context.branch):
            raise ValueError("Automatic revert supports the evidenced branch head only")
        repo = self.client._repository(context.repository)
        detail = await self.client._get_json(f"/repos/{repo}/commits/{target}")
        if len(detail["parents"]) != 1 or not 1 <= len(detail["files"]) <= 20:
            raise ValueError("Merge, root, or oversized commit requires manual review")
        parent = detail["parents"][0]["sha"]
        tree = await self.client._get_json(
            f"/repos/{repo}/git/trees/{detail['commit']['tree']['sha']}", {"recursive": "1"}
        )
        if tree.get("truncated"):
            raise ValueError("Incomplete tree")
        modes = {item["path"]: item["mode"] for item in tree["tree"]}
        replacements, hashes = {}, {}
        for changed in detail["files"]:
            if changed["status"] != "modified":
                raise ValueError("Additions, deletions, and renames require manual remediation")
            path = safe_path(changed["filename"])
            before = await self.client.file_text(context.repository, path, target)
            after = await self.client.file_text(context.repository, path, parent)
            if before == after:
                raise ValueError("Mode-only changes require manual review")
            replacements[path], hashes[path] = after, digest(before)
        proposal = RemediationProposal(
            investigation_id=investigation_id,
            repository=context.repository,
            base_branch=context.branch,
            action="revert_commit",
            commit_sha=target,
            base_sha=target,
            expected_files=sorted(replacements),
            replacements=replacements,
            expected_hashes=hashes,
            file_modes={path: modes[path] for path in replacements},
            evidence=report.health.evidence + report.commits.evidence + report.security.evidence,
            confidence=report.hypothesis.confidence,
            tests=[
                "Manual project tests required before merging",
                "Independent health probe after deployment",
            ],
            risks=[
                "Reverts all modified text files in the current head commit",
                "No merge or service deployment is performed",
            ],
        )
        self.client.validate(proposal)
        return self.save_proposal(proposal, session)
