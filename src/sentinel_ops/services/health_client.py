"""Bounded probes. Real connections are restricted to exact numeric loopback URLs."""

import asyncio
import ipaddress
import socket
import ssl
import time
from typing import Literal, Protocol
from urllib.parse import urlsplit

import httpx

from sentinel_ops.logging import redact
from sentinel_ops.schemas import Probe


class HealthClient(Protocol):
    simulated: bool

    async def probe(self, endpoint: str, timeout: float) -> Probe: ...


def validate_url(url: str, local_demo: bool = False) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
        or parsed.query
    ):
        raise ValueError("Unsafe URL")
    host = parsed.hostname.lower().rstrip(".")
    if host in {"localhost", "metadata.google.internal"} or "%" in host:
        raise ValueError("Use explicit numeric demo loopback; metadata is forbidden")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if host.endswith((".internal", ".local")) or "." not in host:
            raise ValueError("Internal host forbidden") from None
    else:
        if not address.is_global and not (local_demo and address.is_loopback):
            raise ValueError("Non-public target forbidden")
    if parsed.port is not None and not 1 <= parsed.port <= 65535:
        raise ValueError("Invalid port")


def classify_exception(exc: BaseException) -> Literal["timeout", "dns", "tls", "connection"]:
    chain: BaseException | None = exc
    seen = set()
    while chain and id(chain) not in seen:
        seen.add(id(chain))
        if isinstance(chain, (httpx.TimeoutException, TimeoutError)):
            return "timeout"
        if isinstance(chain, socket.gaierror):
            return "dns"
        if isinstance(chain, ssl.SSLError):
            return "tls"
        chain = chain.__cause__ or chain.__context__
    return "connection"


class HttpHealthClient:
    def __init__(
        self,
        *,
        allowed_urls: set[str],
        local_demo: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
        max_bytes: int = 4096,
    ):
        self.allowed_urls = frozenset(allowed_urls)
        self.local_demo = local_demo
        self.simulated = transport is not None
        self.max_bytes = max_bytes
        if not 128 <= max_bytes <= 65536:
            raise ValueError("Invalid response bound")
        if transport is None:
            for url in allowed_urls:
                validate_url(url, local_demo)
                if (
                    not local_demo
                    or not ipaddress.ip_address(urlsplit(url).hostname or "").is_loopback
                ):
                    raise ValueError("External network disabled in this build")
        self.transport = transport

    async def probe(self, endpoint: str, timeout: float) -> Probe:
        start = time.perf_counter()
        try:
            validate_url(endpoint, self.local_demo)
            if endpoint not in self.allowed_urls:
                raise ValueError("Target not allowlisted")
        except ValueError:
            return Probe(failure="unsafe_url", excerpt="URL rejected by local policy")
        try:
            async with asyncio.timeout(timeout):
                async with httpx.AsyncClient(
                    transport=self.transport,
                    trust_env=False,
                    follow_redirects=False,
                    timeout=timeout,
                ) as client:
                    async with client.stream("GET", endpoint) as response:
                        data = bytearray()
                        async for chunk in response.aiter_bytes(chunk_size=512):
                            data.extend(chunk[: max(0, self.max_bytes - len(data))])
                            if len(data) >= self.max_bytes:
                                break
                        code = response.status_code
                        return Probe(
                            status=code,
                            latency_ms=(time.perf_counter() - start) * 1000,
                            failure="redirect"
                            if 300 <= code < 400
                            else (None if 200 <= code < 300 else "http"),
                            excerpt=redact(data.decode("utf-8", errors="replace")),
                        )
        except (httpx.HTTPError, OSError, TimeoutError) as exc:
            failure = classify_exception(exc)
            return Probe(
                failure=failure,
                latency_ms=(time.perf_counter() - start) * 1000,
                excerpt=f"Probe failed: {failure}",
            )
