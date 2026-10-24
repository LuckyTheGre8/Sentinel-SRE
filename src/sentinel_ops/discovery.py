"""Agent address discovery via static runtime files and environment variables."""

import json
import os
from pathlib import Path

PEER_ENV_MAP: dict[str, list[str]] = {
    "telemetry": ["TELEMETRY_ADDRESS", "TELEMETRY_AGENT_ADDRESS"],
    "commit": ["COMMIT_ADDRESS", "COMMIT_AGENT_ADDRESS"],
    "security": ["SECURITY_ADDRESS", "SECURITY_AGENT_ADDRESS"],
    "remediation": ["REMEDIATION_ADDRESS", "REMEDIATION_AGENT_ADDRESS"],
    "orchestrator": ["ORCHESTRATOR_ADDRESS", "ORCHESTRATOR_AGENT_ADDRESS"],
}


def save_agent_address(runtime_dir: Path, agent_name: str, address: str) -> Path:
    """Save an agent's address to .local/runtime/{agent}.address.json."""
    runtime_dir.mkdir(parents=True, exist_ok=True)
    target = runtime_dir / f"{agent_name}.address.json"
    target.write_text(
        json.dumps({"name": agent_name, "address": address}, indent=2),
        encoding="utf-8",
    )
    return target


def load_agent_address(
    runtime_dir: Path, agent_name: str, env: dict[str, str] | None = None
) -> str | None:
    """Load an agent's address checking environment first, then runtime file."""
    env = env if env is not None else dict(os.environ)
    for env_var in PEER_ENV_MAP.get(agent_name, []):
        val = env.get(env_var, "").strip()
        if val:
            return val
    target = runtime_dir / f"{agent_name}.address.json"
    if target.exists():
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
            if data.get("address"):
                return str(data["address"]).strip()
        except Exception:
            pass
    return None


def discover_peer_addresses(
    runtime_dir: Path, env: dict[str, str] | None = None
) -> dict[str, str]:
    """Discover all peer agent addresses from environment and runtime files."""
    env = env if env is not None else dict(os.environ)
    peers: dict[str, str] = {}
    for agent_name in PEER_ENV_MAP:
        addr = load_agent_address(runtime_dir, agent_name, env)
        if addr:
            peers[agent_name] = addr

    if runtime_dir.exists():
        for path in runtime_dir.glob("*.address.json"):
            name = path.stem.replace(".address", "")
            if name not in peers:
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if data.get("address"):
                        peers[name] = str(data["address"]).strip()
                except Exception:
                    pass
    return peers
