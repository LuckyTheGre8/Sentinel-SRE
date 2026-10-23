"""Real HTTP demo reads the sandbox configuration; no mutation HTTP routes."""

import json
import socket
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from sentinel_ops.services.sandbox_github import SandboxGitHubClient
from sentinel_ops.state import StateStore


def create_app(database: Path) -> FastAPI:
    app = FastAPI(title="Sentinel-Ops local demo", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health")
    def health():
        store = StateStore(database)
        try:
            config = json.loads(SandboxGitHubClient(store).files()["config.json"])
            healthy = config["healthy"] is True
        except (ValueError, KeyError):
            healthy = False
        finally:
            store.close()
        return JSONResponse(
            {"state": "healthy" if healthy else "failing", "source": "local-demo"},
            status_code=200 if healthy else 503,
        )

    return app


@contextmanager
def running_service(database: Path):
    """Use a random loopback port; stop and close the owned service on every exit."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(database),
            host="127.0.0.1",
            port=port,
            log_level="warning",
            access_log=False,
            lifespan="off",
        )
    )
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    try:
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError("Local service did not start")
            time.sleep(0.02)
        yield f"http://127.0.0.1:{port}/health"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        listener.close()
        if thread.is_alive():
            raise RuntimeError("Local service did not stop")
