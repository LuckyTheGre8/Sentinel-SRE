"""Bounded JSON requests to fixed provider origins; errors never include payloads."""

import json

import httpx


class APIError(OSError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


async def request_json(
    method: str,
    url: str,
    *,
    headers: dict | None = None,
    params: dict | None = None,
    body: dict | None = None,
    timeout: float = 10,
    max_bytes: int = 2 * 1024 * 1024,
    transport: httpx.AsyncBaseTransport | None = None,
):
    try:
        async with httpx.AsyncClient(
            timeout=timeout, trust_env=False, follow_redirects=False, transport=transport
        ) as client:
            async with client.stream(
                method,
                url,
                headers={**(headers or {}), "Accept-Encoding": "identity"},
                params=params,
                json=body,
            ) as response:
                if not 200 <= response.status_code < 300:
                    raise APIError(
                        f"Provider returned HTTP {response.status_code}", response.status_code
                    )
                if response.headers.get("content-encoding", "identity").lower() not in {
                    "",
                    "identity",
                }:
                    raise APIError("Provider returned unsupported compression")
                data = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=4096):
                    if len(data) + len(chunk) > max_bytes:
                        raise APIError("Provider response exceeded size limit")
                    data.extend(chunk)
        result = json.loads(data)
        if not isinstance(result, (dict, list)):
            raise APIError("Provider returned an invalid JSON document")
        return result
    except APIError:
        raise
    except (httpx.HTTPError, ValueError, OSError, TimeoutError):
        raise APIError("Provider request failed") from None
