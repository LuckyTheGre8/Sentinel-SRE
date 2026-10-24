"""Initialize identities, cryptographic seeds, ports, and discovery addresses for 5 standalone Sentinel uAgents."""

import json
import secrets
from pathlib import Path

from uagents import Agent

AGENTS_CONFIG = [
    {
        "key": "telemetry",
        "name": "Sentinel-Telemetry",
        "seed_var": "TELEMETRY_SEED",
        "port_var": "TELEMETRY_PORT",
        "port": 8001,
        "addr_var": "TELEMETRY_ADDRESS",
        "handle": "@sentinel-telemetry",
        "role": "Health probes & recovery verification",
    },
    {
        "key": "commit",
        "name": "Sentinel-Commit",
        "seed_var": "COMMIT_SEED",
        "port_var": "COMMIT_PORT",
        "port": 8002,
        "addr_var": "COMMIT_ADDRESS",
        "handle": "@sentinel-commit",
        "role": "GitHub commit analysis & diff ranking",
    },
    {
        "key": "security",
        "name": "Sentinel-Security",
        "seed_var": "SECURITY_SEED",
        "port_var": "SECURITY_PORT",
        "port": 8003,
        "addr_var": "SECURITY_ADDRESS",
        "handle": "@sentinel-security",
        "role": "OSV vulnerability scanning & SAST",
    },
    {
        "key": "remediation",
        "name": "Sentinel-Remediation",
        "seed_var": "REMEDIATION_SEED",
        "port_var": "REMEDIATION_PORT",
        "port": 8004,
        "addr_var": "REMEDIATION_ADDRESS",
        "handle": "@sentinel-remediation",
        "role": "Draft PR creation & revert proposals",
    },
    {
        "key": "orchestrator",
        "name": "Sentinel-Orchestrator",
        "seed_var": "ORCHESTRATOR_SEED",
        "port_var": "ORCHESTRATOR_PORT",
        "port": 8005,
        "addr_var": "ORCHESTRATOR_ADDRESS",
        "handle": "@sentinel-orchestrator",
        "role": "Investigation coordination & ACP intake",
    },
]


def load_env_dict(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            k, sep, v = line.partition("=")
            if sep:
                values[k.strip()] = v.strip().strip("'\"")
    return values


def main():
    root = Path(__file__).resolve().parents[1]
    runtime_dir = root / ".local" / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    env_path = root / ".env"
    existing_env = load_env_dict(env_path)

    updates: dict[str, str] = dict(existing_env)
    print("=" * 70)
    print("Sentinel-Ops 5-Agent Identity Initialization")
    print("=" * 70)

    for cfg in AGENTS_CONFIG:
        key = cfg["key"]
        seed_var = cfg["seed_var"]
        seed_file = runtime_dir / f"{key}.seed"

        # Check existing seed from env or seed file, or generate new
        seed = updates.get(seed_var)
        if not seed and seed_file.exists():
            seed = seed_file.read_text(encoding="utf-8").strip()
        if not seed:
            seed = secrets.token_urlsafe(48)

        seed_file.write_text(seed, encoding="utf-8")
        updates[seed_var] = seed
        updates[cfg["port_var"]] = str(cfg["port"])

        # Derive deterministic uAgents address from seed
        dummy = Agent(name=cfg["name"], seed=seed, port=cfg["port"])
        addr = dummy.address
        updates[cfg["addr_var"]] = addr

        # Also populate TELEMETRY_AGENT_ADDRESS aliases if desired
        updates[f"{key.upper()}_AGENT_ADDRESS"] = addr

        # Save to .local/runtime/{agent}.address.json
        addr_file = runtime_dir / f"{key}.address.json"
        addr_file.write_text(
            json.dumps({"name": cfg["name"], "address": addr, "port": cfg["port"]}, indent=2),
            encoding="utf-8",
        )

        print(f"\n[+] {cfg['name']} ({cfg['handle']})")
        print(f"    Port:    {cfg['port']}")
        print(f"    Address: {addr}")
        print(f"    Role:    {cfg['role']}")

    # Write updated .env
    lines = [
        "# Agent seeds (each 32+ chars, generated once via init)",
        f"ORCHESTRATOR_SEED={updates.get('ORCHESTRATOR_SEED', '')}",
        f"TELEMETRY_SEED={updates.get('TELEMETRY_SEED', '')}",
        f"COMMIT_SEED={updates.get('COMMIT_SEED', '')}",
        f"SECURITY_SEED={updates.get('SECURITY_SEED', '')}",
        f"REMEDIATION_SEED={updates.get('REMEDIATION_SEED', '')}",
        "",
        "# Agent ports",
        f"ORCHESTRATOR_PORT={updates.get('ORCHESTRATOR_PORT', '8005')}",
        f"TELEMETRY_PORT={updates.get('TELEMETRY_PORT', '8001')}",
        f"COMMIT_PORT={updates.get('COMMIT_PORT', '8002')}",
        f"SECURITY_PORT={updates.get('SECURITY_PORT', '8003')}",
        f"REMEDIATION_PORT={updates.get('REMEDIATION_PORT', '8004')}",
        "",
        "# Agent addresses (populated after first run, for orchestrator to know where to send)",
        f"TELEMETRY_ADDRESS={updates.get('TELEMETRY_ADDRESS', '')}",
        f"COMMIT_ADDRESS={updates.get('COMMIT_ADDRESS', '')}",
        f"SECURITY_ADDRESS={updates.get('SECURITY_ADDRESS', '')}",
        f"REMEDIATION_ADDRESS={updates.get('REMEDIATION_ADDRESS', '')}",
        f"ORCHESTRATOR_ADDRESS={updates.get('ORCHESTRATOR_ADDRESS', '')}",
        "",
        "# Shared",
        f"ASI1_API_KEY={updates.get('ASI1_API_KEY', '')}",
        f"ASI1_DATA_SHARING={updates.get('ASI1_DATA_SHARING', 'true')}",
        f"ASI1_MODEL={updates.get('ASI1_MODEL', 'asi1-mini')}",
        f"GITHUB_TOKEN={updates.get('GITHUB_TOKEN', '')}",
        f"SENTINEL_REPOSITORIES={updates.get('SENTINEL_REPOSITORIES', '')}",
        f"SENTINEL_SENDERS={updates.get('SENTINEL_SENDERS', '')}",
        f"SENTINEL_HEALTH_URLS={updates.get('SENTINEL_HEALTH_URLS', '')}",
        f"AGENT_MAILBOX={updates.get('AGENT_MAILBOX', 'true')}",
        f"AGENT_ENDPOINT={updates.get('AGENT_ENDPOINT', '')}",
        f"AGENTVERSE_API_KEY={updates.get('AGENTVERSE_API_KEY', '')}",
        f"LOG_LEVEL={updates.get('LOG_LEVEL', 'INFO')}",
    ]
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n" + "=" * 70)
    print("Configuration written to .env and .local/runtime/*.address.json")
    print("Next step: Run `powershell -File scripts/start_all_agents.ps1` to launch all 5 agents.")
    print("=" * 70)


if __name__ == "__main__":
    main()
