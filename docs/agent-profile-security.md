# Sentinel-Security

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

**Handle**: `@sentinel-security`  
**Default Port**: `8003`  
**Seed Env Var**: `SECURITY_SEED`  
**Protocol**: `SentinelSecurity` (`SecurityScanRequest`, `SecurityScanResponse`) + `AgentChatProtocol` (ACP)

Performs OSV vulnerability batch queries against declared dependencies (`requirements.txt`, etc.) and narrow AST/SAST analysis over candidate Python code. Computes risk scores and returns remediation recommendations and fixed versions.

### ACP Capabilities
- `scan_dependencies`: Scans manifests for known CVEs and advisories via the Open Source Vulnerabilities (OSV) API.

### Chat Examples
- `{"action": "scan_dependencies", "files": {"requirements.txt": "demo-vulnerable==1.0.0"}}`
