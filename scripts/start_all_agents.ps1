<#
.SYNOPSIS
    Starts all 5 Sentinel-Ops standalone uAgents in separate PowerShell windows.
.DESCRIPTION
    Launches:
      1. Sentinel-Telemetry    (Port 8001)
      2. Sentinel-Commit       (Port 8002)
      3. Sentinel-Security     (Port 8003)
      4. Sentinel-Remediation  (Port 8004)
      5. Sentinel-Orchestrator (Port 8005)
#>

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Launching 5 Standalone Sentinel-Ops uAgents" -ForegroundColor Cyan
Write-Host " Project root: $ProjectRoot" -ForegroundColor Gray
Write-Host "==========================================================" -ForegroundColor Cyan

$agents = @(
    @{ Name = "Sentinel-Telemetry";    Module = "sentinel_ops.agents.telemetry_agent";    Port = 8001; Color = "Green" },
    @{ Name = "Sentinel-Commit";       Module = "sentinel_ops.agents.commit_agent";       Port = 8002; Color = "Yellow" },
    @{ Name = "Sentinel-Security";     Module = "sentinel_ops.agents.security_agent";     Port = 8003; Color = "Magenta" },
    @{ Name = "Sentinel-Remediation";  Module = "sentinel_ops.agents.remediation_agent";  Port = 8004; Color = "Cyan" },
    @{ Name = "Sentinel-Orchestrator"; Module = "sentinel_ops.agents.orchestrator_agent"; Port = 8005; Color = "White" }
)

foreach ($agent in $agents) {
    Write-Host "[+] Starting $($agent.Name) on Port $($agent.Port)..." -ForegroundColor $agent.Color
    $cmd = "cd '$ProjectRoot'; Write-Host '--- $($agent.Name) (Port $($agent.Port)) ---' -ForegroundColor $($agent.Color); uv run python -m $($agent.Module) serve"
    Start-Process powershell.exe -ArgumentList "-NoExit", "-Command", $cmd
    Start-Sleep -Milliseconds 800
}

Write-Host "`nAll 5 agents launched in separate terminals." -ForegroundColor Green
Write-Host "Check each terminal window for its Inspector URL and Agentverse Mailbox connection." -ForegroundColor Gray
