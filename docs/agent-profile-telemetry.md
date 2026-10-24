# Sentinel-Telemetry

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

**Handle**: `@sentinel-telemetry`  
**Default Port**: `8001`  
**Seed Env Var**: `TELEMETRY_SEED`  
**Protocol**: `SentinelHealth` (`HealthCheckRequest`, `HealthCheckResponse`, `VerificationRequest`, `VerificationResponse`) + `AgentChatProtocol` (ACP)

Probes remote HTTPS health endpoints, evaluates latency ms, records consecutive failures, and verifies recovery post-remediation.

### ACP Capabilities
- `investigate`: Conducts bounded HTTP probes (status code, latency, excerpt, failure classification).
- `verify`: Re-probes endpoints after remediation to confirm service recovery.

### Chat Examples
- `{"action": "investigate", "endpoint": "https://service.example/health"}`
- `{"action": "verify", "endpoint": "https://service.example/health"}`
- Direct URL: `https://service.example/health`
