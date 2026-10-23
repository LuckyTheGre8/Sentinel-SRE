"""Conservative staged/tracked-content scan; reports paths, never matched values."""

import argparse
import re
import subprocess
from pathlib import Path

RULES = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{24,}\b"),
    re.compile(r"https?://[^\s/@]+:[^\s/@]+@"),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--staged", action="store_true")
    args = parser.parse_args()
    command = (
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM", "-z"]
        if args.staged
        else ["git", "ls-files", "-z"]
    )
    paths = subprocess.check_output(command).decode().split("\0")
    failures = []
    for name in filter(None, paths):
        path = Path(name)
        if (path.name.startswith(".env") and path.name != ".env.example") or path.suffix in {
            ".key",
            ".pem",
            ".db",
            ".log",
        }:
            failures.append(name)
            continue
        data = (
            subprocess.check_output(["git", "show", f":{name}"])
            if args.staged
            else path.read_bytes()
        )
        text = data.decode("utf-8", errors="replace")
        if any(rule.search(text) for rule in RULES):
            failures.append(name)
    if failures:
        raise SystemExit("Secret scan failed in: " + ", ".join(failures))
    print(
        f"Secret scan passed ({len(list(filter(None, paths)))} files; pattern-based, not a guarantee)."
    )


if __name__ == "__main__":
    main()
