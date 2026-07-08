# One-shot setup: register scheduled task and confirm configuration.

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host "=== Trading Agent Desk Automation Setup ==="
Write-Host "Repo: $RepoRoot"
Write-Host "Timezone: $([TimeZoneInfo]::Local.Id)"
Write-Host ""

& "$PSScriptRoot\register_desk_task.ps1"

$task = Get-ScheduledTask -TaskName "TradingAgentDeskSession" -ErrorAction Stop
Write-Host ""
Write-Host "Task state: $($task.State)"
$info = Get-ScheduledTaskInfo -TaskName "TradingAgentDeskSession"
Write-Host "Next run:   $($info.NextRunTime)"
Write-Host ""
Write-Host "Setup complete. Desk will auto-pull from GitHub and run each weekday at 01:55 AM."