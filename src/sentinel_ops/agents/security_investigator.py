import ast
import asyncio

from sentinel_ops.schemas import (
    AgentError,
    Evidence,
    Finding,
    SecurityScanRequest,
    SecurityScanResponse,
)
from sentinel_ops.services.osv_client import OSVClient
from sentinel_ops.services.security import code_findings, dependencies


class SecurityInvestigator:
    def __init__(self, client: OSVClient):
        self.client = client

    async def run(self, request: SecurityScanRequest) -> SecurityScanResponse:
        files = dict(list(request.files.items())[:100])
        warnings = ["Recorded OSV data; narrow SAST is not a complete security audit"]
        if len(request.files) > 100:
            warnings.append("File count truncated")
        oversized = [p for p, content in files.items() if len(content.encode()) > 65536]
        for path in oversized:
            del files[path]
            warnings.append(f"Oversized file omitted: {path}")
        deps, parser_warnings = dependencies(files)
        warnings.extend(parser_warnings)
        for path, content in files.items():
            if path.endswith(".py"):
                try:
                    ast.parse(content)
                except SyntaxError:
                    warnings.append(f"Python parse failed; code analysis incomplete: {path}")
        findings = code_findings(files, request.incident_files)
        error = None
        try:
            results = await asyncio.wait_for(self.client.query_batch(deps), 3)
            if len(results) != len(deps):
                raise ValueError("OSV batch length mismatch")
            for dep, vulns in zip(deps, results, strict=True):
                for vuln in vulns:
                    if vuln.get("withdrawn"):
                        warnings.append(f"Withdrawn advisory omitted: {vuln['id']}")
                        continue
                    affected = [
                        a
                        for a in vuln.get("affected", [])
                        if a.get("package", {}).get("name") == dep.name
                        and a.get("package", {}).get("ecosystem") == dep.ecosystem
                    ]
                    fixed = sorted(
                        {
                            event["fixed"]
                            for a in affected
                            for r in a.get("ranges", [])
                            for event in r.get("events", [])
                            if "fixed" in event
                        }
                    )
                    severity = vuln.get("database_specific", {}).get("severity", "unknown").lower()
                    if severity not in {"critical", "high", "medium", "low", "info"}:
                        severity = "medium"
                        warnings.append(
                            f"Severity unavailable for {vuln['id']}; conservative medium label"
                        )
                    findings.append(
                        Finding(
                            id=vuln["id"],
                            kind="dependency",
                            severity=severity,
                            confidence=1,
                            file=dep.file,
                            evidence=f"{dep.ecosystem}:{dep.name}=={dep.version}; {vuln['id']}",
                            remediation="Review upstream fixed versions: "
                            + (", ".join(fixed) or "unknown"),
                            fixed_versions=fixed,
                            aliases=vuln.get("aliases", []),
                            references=[r["url"] for r in vuln.get("references", [])],
                            related_to_incident=False,
                        )
                    )
        except (OSError, ValueError, TimeoutError, KeyError):
            error = AgentError(
                code="osv_unavailable", message="Dependency analysis incomplete", retryable=True
            )
            warnings.append("OSV unavailable or outside recorded coverage; code findings retained")
        weights = {"critical": 10, "high": 8, "medium": 5, "low": 2, "info": 0}
        risk = max((weights[f.severity] * f.confidence for f in findings), default=0)
        return SecurityScanResponse(
            investigation_id=request.investigation_id,
            findings=findings,
            success=error is None,
            error=error,
            warnings=warnings,
            risk_score=risk,
            evidence=[
                Evidence(id=f"security:{f.id}", source="security", summary=f.evidence)
                for f in findings
            ],
        )
