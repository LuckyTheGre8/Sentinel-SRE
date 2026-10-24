"""OSV batch lookup contract with live and recorded implementations."""

import asyncio
import json
from pathlib import Path
from typing import Protocol

from sentinel_ops.schemas import Dependency


class OSVClient(Protocol):
    async def query_batch(self, dependencies: list[Dependency]) -> list[list[dict]]: ...


class RecordedOSVClient:
    simulated = True

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


class OSVAPIError(OSError):
    """A bounded, non-sensitive OSV API failure."""


class LiveOSVClient:
    """Public OSV queries with bounded pagination and full advisory hydration."""

    simulated = False
    api_root = "https://api.osv.dev/v1"

    def __init__(self, timeout: float = 10, transport=None):
        self.timeout = timeout
        self.transport = transport

    async def _request(self, method, path, body=None):
        from sentinel_ops.services.http_api import request_json

        value = await request_json(
            method,
            self.api_root + path,
            body=body,
            timeout=self.timeout,
            transport=self.transport,
        )
        if not isinstance(value, dict):
            raise OSVAPIError("Invalid OSV response")
        return value

    async def query_batch(self, dependencies: list[Dependency]) -> list[list[dict]]:
        from urllib.parse import quote

        if len(dependencies) > 100:
            raise ValueError("OSV batch is limited to 100 dependencies")
        if not dependencies:
            return []
        queries = [
            {"package": {"ecosystem": d.ecosystem, "name": d.name}, "version": d.version}
            for d in dependencies
        ]
        ids: list[list[str]] = [[] for _ in dependencies]
        pending = list(enumerate(queries))
        for _ in range(10):
            response = await self._request(
                "POST",
                "/querybatch",
                {
                    "queries": [query for _, query in pending],
                },
            )
            results = response.get("results")
            if not isinstance(results, list) or len(results) != len(pending):
                raise OSVAPIError("OSV batch response did not match request")
            next_pending = []
            for (index, query), result in zip(pending, results, strict=True):
                if not isinstance(result, dict) or not isinstance(result.get("vulns", []), list):
                    raise OSVAPIError("Invalid OSV result")
                for vuln in result.get("vulns", []):
                    if not isinstance(vuln, dict) or not isinstance(vuln.get("id"), str):
                        raise OSVAPIError("Invalid OSV advisory identifier")
                    if vuln["id"] not in ids[index]:
                        ids[index].append(vuln["id"])
                token = result.get("next_page_token")
                if token:
                    if not isinstance(token, str):
                        raise OSVAPIError("Invalid OSV page token")
                    next_pending.append((index, {**query, "page_token": token}))
            if sum(map(len, ids)) > 500:
                raise OSVAPIError("OSV advisory bound exceeded; scan incomplete")
            pending = next_pending
            if not pending:
                break
        if pending:
            raise OSVAPIError("OSV pagination bound exceeded; scan incomplete")
        semaphore = asyncio.Semaphore(8)

        async def detail(identifier):
            async with semaphore:
                value = await self._request("GET", "/vulns/" + quote(identifier, safe="-_."))
            if value.get("id") != identifier:
                raise OSVAPIError("OSV advisory correlation mismatch")
            return identifier, value

        identifiers = dict.fromkeys(identifier for group in ids for identifier in group)
        details = dict(await asyncio.gather(*(detail(identifier) for identifier in identifiers)))
        return [[details[identifier] for identifier in group] for group in ids]
