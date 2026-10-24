"""Resolve and pin public addresses while preserving TLS hostname verification."""

import asyncio
import ipaddress
import socket

import httpx


class PublicHTTPStransport(httpx.AsyncBaseTransport):
    def __init__(self):
        self.inner = httpx.AsyncHTTPTransport(trust_env=False)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.scheme != "https":
            raise httpx.ConnectError("Public probes require HTTPS")
        host = request.url.host
        addresses = await asyncio.get_running_loop().getaddrinfo(
            host,
            request.url.port or 443,
            type=socket.SOCK_STREAM,
        )
        ips = sorted({entry[4][0] for entry in addresses})
        if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
            raise httpx.ConnectError("Non-public DNS target rejected")
        pinned = httpx.Request(
            request.method,
            request.url.copy_with(host=ips[0]),
            headers=request.headers,
            stream=request.stream,
            extensions={**request.extensions, "sni_hostname": host},
        )
        return await self.inner.handle_async_request(pinned)

    async def aclose(self):
        await self.inner.aclose()
