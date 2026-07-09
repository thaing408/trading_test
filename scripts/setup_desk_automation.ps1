# One-shot setup: register scheduled task and confirm configuration.

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

Write-Host "=== Trading Agent Desk Automation Setup ==="
Write-Host "Repo: $RepoRoot"
Write-Host "Timezone: $([TimeZoneInfo]::Local.Id)"
Write-Host ""

& "$PSScriptRoot\enable_pc_wake.ps1"
& "$PSScriptRoot\register_desk_task.ps1"
& "$PSScriptRoot\verify_environment.ps1"

$task = Get-ScheduledTask -TaskName "TradingAgentDeskSession" -ErrorAction Stop
Write-Host ""
Write-Host "Task state: $($task.State)"
Write-Host "WakeToRun:  $($task.Settings.WakeToRun)"
$info = Get-ScheduledTaskInfo -TaskName "TradingAgentDeskSession"
Write-Host "Next run:   $($info.NextRunTime)"
Write-Host ""
Write-Host "Setup complete. PC wakes ~01:50 AM; desk runs 01:55 AM weekdays (Sleep/Hibernate)."