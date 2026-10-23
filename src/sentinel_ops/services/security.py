"""Narrow explainable checks; manifests are parsed, never executed."""

import ast
import json
import re
import tomllib
import xml.etree.ElementTree as ET

from sentinel_ops.logging import redact
from sentinel_ops.schemas import Dependency, Finding


def dependencies(files: dict[str, str]) -> tuple[list[Dependency], list[str]]:
    found: list[Dependency] = []
    warnings = []
    for path, text in files.items():
        if len(text.encode()) > 65536:
            warnings.append(f"Manifest too large: {path}")
            continue
        items: list[tuple[str, str, str]] = []
        try:
            if path.endswith("requirements.txt"):
                items = [
                    ("PyPI", m[0], m[1])
                    for m in re.findall(r"(?m)^([\w.-]+)==([\w.+-]+)\s*$", text)
                ]
                if any(
                    line.strip() and not line.startswith("#") and "==" not in line
                    for line in text.splitlines()
                ):
                    warnings.append(f"Unresolved requirements omitted: {path}")
            elif path.endswith("pyproject.toml"):
                values = tomllib.loads(text).get("project", {}).get("dependencies", [])
                for value in values:
                    match = re.fullmatch(r"([\w.-]+)==([\w.+-]+)", value)
                    if match:
                        items.append(("PyPI", match.group(1), match.group(2)))
                    else:
                        warnings.append(f"Unresolved project dependency: {path}")
            elif path.endswith("package-lock.json"):
                for name, package in json.loads(text).get("packages", {}).items():
                    if "node_modules/" in name and package.get("version"):
                        items.append(
                            ("npm", name.rsplit("node_modules/", 1)[-1], package["version"])
                        )
            elif path.endswith("package.json"):
                if path.replace("package.json", "package-lock.json") in files:
                    continue
                for name, version in json.loads(text).get("dependencies", {}).items():
                    if re.fullmatch(r"\d+\.\d+\.\d+(?:-[\w.]+)?", version):
                        items.append(("npm", name, version))
                    else:
                        warnings.append(f"Unresolved npm range: {name}")
            elif path.endswith("go.mod"):
                items = [
                    ("Go", m[0], m[1])
                    for m in re.findall(r"(?m)^\s*(?:require\s+)?([\w./-]+)\s+(v[\w.+-]+)", text)
                ]
            elif path.endswith("pom.xml"):
                root = ET.fromstring(text)
                for dep in root.findall(".//{*}dependency"):
                    group, name, version = [
                        dep.findtext("{*}" + k) for k in ("groupId", "artifactId", "version")
                    ]
                    if group and name and version and "${" not in version:
                        items.append(("Maven", f"{group}:{name}", version))
                    else:
                        warnings.append(f"Unresolved Maven dependency: {path}")
            elif path.rsplit("/", 1)[-1].startswith("Dockerfile"):
                warnings.append(f"Container OSV mapping unavailable; pin check only: {path}")
            elif path.endswith((".lock", "lock.yaml")):
                warnings.append(f"Unsupported lockfile: {path}")
            found.extend(Dependency(ecosystem=e, name=n, version=v, file=path) for e, n, v in items)
        except (ValueError, ET.ParseError, TypeError):
            warnings.append(f"Invalid manifest: {path}")
    return found, warnings


def code_findings(files: dict[str, str], incident_files: list[str]) -> list[Finding]:
    findings = []

    def add(rule, path, line, evidence, severity="medium"):
        findings.append(
            Finding(
                id=f"{rule}:{path}:{line}",
                kind="code",
                severity=severity,
                confidence=0.8,
                file=path,
                line=line,
                evidence=redact(evidence)[:300],
                remediation=f"Review and remove {rule}; narrow heuristic requires human review",
                related_to_incident=False,
            )
        )

    for path, text in files.items():
        if path.endswith(".py"):
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Assign)
                    and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)
                ):
                    if any(
                        isinstance(t, ast.Name)
                        and re.search(r"(?i)(password|secret|token|api_key)", t.id)
                        for t in node.targets
                    ):
                        add(
                            "hardcoded-credential",
                            path,
                            node.lineno,
                            "Credential literal [REDACTED]",
                            "high",
                        )
                if isinstance(node, ast.Call):
                    name = ast.unparse(node.func)
                    if any(
                        k.arg == "shell"
                        and isinstance(k.value, ast.Constant)
                        and k.value.value is True
                        for k in node.keywords
                    ):
                        add("shell-execution", path, node.lineno, "shell=True", "high")
                    if any(
                        k.arg == "verify"
                        and isinstance(k.value, ast.Constant)
                        and k.value.value is False
                        for k in node.keywords
                    ):
                        add("tls-disabled", path, node.lineno, "verify=False", "high")
                    if (
                        name.endswith("execute")
                        and node.args
                        and isinstance(node.args[0], (ast.JoinedStr, ast.BinOp))
                    ):
                        add(
                            "sql-interpolation",
                            path,
                            node.lineno,
                            "Interpolated SQL passed to execute",
                            "high",
                        )
                    if any(
                        k.arg == "allow_origins"
                        and isinstance(k.value, ast.List)
                        and any(
                            isinstance(v, ast.Constant) and v.value == "*" for v in k.value.elts
                        )
                        for k in node.keywords
                    ):
                        add(
                            "permissive-cors",
                            path,
                            node.lineno,
                            "Wildcard CORS; verify production context",
                        )
        if path.rsplit("/", 1)[-1].startswith("Dockerfile"):
            for number, line in enumerate(text.splitlines(), 1):
                if line.upper().startswith("FROM ") and "@sha256:" not in line:
                    add("unpinned-image", path, number, line)
    return findings
