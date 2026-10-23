"""SQLite transactions serialize state transitions and retain action records."""

import sqlite3
from pathlib import Path
from uuid import UUID

from sentinel_ops.schemas import InvestigationContext, Status

TRANSITIONS = {
    Status.CREATED: {Status.COLLECTING, Status.CANCELLED},
    Status.COLLECTING: {Status.AWAITING, Status.FAILED, Status.CANCELLED},
    Status.AWAITING: {Status.EXECUTING, Status.CANCELLED},
    Status.EXECUTING: {Status.VERIFYING, Status.FAILED},
    Status.VERIFYING: {Status.RESOLVED, Status.PARTIAL, Status.FAILED},
    Status.RESOLVED: set(),
    Status.PARTIAL: set(),
    Status.FAILED: set(),
    Status.CANCELLED: set(),
}


class StateStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=5)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS investigations(id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS documents(kind TEXT, id TEXT, data TEXT NOT NULL,
                PRIMARY KEY(kind,id));
        """)

    def create(self, context: InvestigationContext) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO investigations VALUES (?,?)",
                (str(context.investigation_id), context.model_dump_json()),
            )

    def get(self, investigation_id: UUID) -> InvestigationContext:
        row = self.db.execute(
            "SELECT data FROM investigations WHERE id=?", (str(investigation_id),)
        ).fetchone()
        if row is None:
            raise KeyError("Unknown investigation")
        return InvestigationContext.model_validate_json(row[0])

    def transition(self, investigation_id: UUID, target: Status) -> InvestigationContext:
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            context = self.get(investigation_id)
            if target not in TRANSITIONS[context.status]:
                raise ValueError(f"Invalid transition: {context.status} -> {target}")
            context.status = target
            self.db.execute(
                "UPDATE investigations SET data=? WHERE id=?",
                (context.model_dump_json(), str(investigation_id)),
            )
        return context

    def put(self, kind: str, key: str, data: str) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO documents VALUES (?,?,?) ON CONFLICT(kind,id) "
                "DO UPDATE SET data=excluded.data",
                (kind, key, data),
            )

    def read(self, kind: str, key: str) -> str | None:
        row = self.db.execute(
            "SELECT data FROM documents WHERE kind=? AND id=?", (kind, key)
        ).fetchone()
        return row[0] if row else None

    def close(self) -> None:
        self.db.close()
