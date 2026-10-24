"""SQLite sandbox PR service. Never shells out, contacts GitHub, or merges Git."""

import hashlib
import json
from typing import Protocol

from sentinel_ops.schemas import RemediationProposal, safe_path
from sentinel_ops.state import StateStore


def digest(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


class PullRequestClient(Protocol):
    async def create_pr(
        self, proposal: RemediationProposal, key: str, body: str
    ) -> tuple[int, str]: ...


class SandboxGitHubClient:
    simulated = True

    def __init__(self, store: StateStore, repository: str = "demo/checkout"):
        if repository != "demo/checkout":
            raise ValueError("Only the fictional local demo repository is supported")
        self.store = store
        self.repository = repository
        self.store.db.executescript("""
            CREATE TABLE IF NOT EXISTS sandbox_files(path TEXT PRIMARY KEY, content TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sandbox_prs(number INTEGER PRIMARY KEY AUTOINCREMENT,
                action_key TEXT UNIQUE NOT NULL, proposal TEXT NOT NULL, body TEXT NOT NULL,
                applied INTEGER NOT NULL DEFAULT 0);
        """)

    def initialize(self, files: dict[str, str]) -> None:
        if self.store.db.execute("SELECT count(*) FROM sandbox_files").fetchone()[0]:
            raise ValueError("Sandbox already initialized; use a fresh demo database")
        with self.store.db:
            for path, content in files.items():
                self.store.db.execute(
                    "INSERT INTO sandbox_files VALUES (?,?)", (safe_path(path), content)
                )

    def files(self) -> dict[str, str]:
        return dict(self.store.db.execute("SELECT path,content FROM sandbox_files").fetchall())

    def validate(self, proposal: RemediationProposal) -> None:
        if proposal.repository != self.repository or proposal.base_branch != "main":
            raise ValueError("Repository/base branch outside sandbox")
        expected = set(proposal.expected_files)
        if len(expected) != len(proposal.expected_files) or not expected:
            raise ValueError("Duplicate/empty approved file set")
        if set(proposal.replacements) != expected or set(proposal.expected_hashes) != expected:
            raise ValueError("Patch differs from exact approved file set")
        if sum(len(p.encode()) + len(c.encode()) for p, c in proposal.replacements.items()) > 16384:
            raise ValueError("Patch exceeds limit")
        for path in expected:
            safe_path(path)
        if len({p.casefold() for p in expected}) != len(expected):
            raise ValueError("Case-colliding paths")
        if "config.json" in proposal.replacements:
            config = json.loads(proposal.replacements["config.json"])
            if not isinstance(config, dict) or type(config.get("healthy")) is not bool:
                raise ValueError("Invalid local service configuration")

    def check_conflicts(self, proposal: RemediationProposal) -> None:
        files = self.files()
        for path, expected in proposal.expected_hashes.items():
            if path not in files or digest(files[path]) != expected:
                raise ValueError("Revert/patch conflict: approved baseline changed")

    async def create_pr(
        self, proposal: RemediationProposal, key: str, body: str
    ) -> tuple[int, str]:
        self.validate(proposal)
        with self.store.db:
            self.store.db.execute("BEGIN IMMEDIATE")
            row = self.store.db.execute(
                "SELECT number,proposal FROM sandbox_prs WHERE action_key=?", (key,)
            ).fetchone()
            if row:
                if row[1] != proposal.model_dump_json():
                    raise ValueError("Idempotency key reused for different proposal")
                number = row[0]
            else:
                self.check_conflicts(proposal)
                cursor = self.store.db.execute(
                    "INSERT INTO sandbox_prs(action_key,proposal,body) VALUES (?,?,?)",
                    (key, proposal.model_dump_json(), body),
                )
                number = cursor.lastrowid
        return int(number), f"sandbox://demo/checkout/pull/{number}"

    def apply_local(self, key: str) -> None:
        """Explicit demo hook; independent of PR creation, atomic in the local DB."""
        with self.store.db:
            self.store.db.execute("BEGIN IMMEDIATE")
            row = self.store.db.execute(
                "SELECT proposal,applied FROM sandbox_prs WHERE action_key=?", (key,)
            ).fetchone()
            if not row:
                raise ValueError("No confirmed sandbox PR")
            if row[1]:
                return
            proposal = RemediationProposal.model_validate_json(row[0])
            self.validate(proposal)
            self.check_conflicts(proposal)
            for path, content in proposal.replacements.items():
                self.store.db.execute(
                    "UPDATE sandbox_files SET content=? WHERE path=?", (content, path)
                )
            self.store.db.execute("UPDATE sandbox_prs SET applied=1 WHERE action_key=?", (key,))

    def count(self) -> int:
        return self.store.db.execute("SELECT count(*) FROM sandbox_prs").fetchone()[0]
