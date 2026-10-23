"""Batch OSV lookup contract; recorded responses retain batch IDs and full details."""

import json
from pathlib import Path
from typing import Protocol

from sentinel_ops.schemas import Dependency


class OSVClient(Protocol):
    async def query_batch(self, dependencies: list[Dependency]) -> list[list[dict]]: ...


class RecordedOSVClient:
    def __init__(self, fixture: Path):
        self.data = json.loads(fixture.read_text(encoding="utf-8"))

    async def query_batch(self, dependencies: list[Dependency]) -> list[list[dict]]:
        results = []
        for dep in dependencies:
            key = f"{dep.ecosystem}:{dep.name}:{dep.version}"
            if key not in self.data["queries"]:
                raise ValueError("Dependency absent from recorded OSV coverage")
            batch = self.data["queries"][key]
            results.append([self.data["details"][v["id"]] for v in batch.get("vulns", [])])
        return results
