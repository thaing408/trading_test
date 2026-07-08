# Register Windows Task Scheduler: auto-update + run trading desk weekdays 01:55 AM Pacific.
# Run once as Administrator if registration fails due to permissions.

$ErrorActionPreference = "Stop"
$TaskName = "TradingAgentDeskSession"
$ScriptPath = Join-Path $PSScriptRoot "start_desk_session.ps1"
$RepoRoot = Split-Path -Parent $PSScriptRoot

if (-not (Test-Path $ScriptPath)) {
    throw "Missing startup script: $ScriptPath"
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`"" `
    -WorkingDirectory $RepoRoot

# Machine is Pacific — 01:55 AM local = 5 min before Market Intelligence (02:00)
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At "01:55AM"

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 16) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 10) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description "Trading Agent PST desk: git pull, then 7-phase session through Discord" -Force

Write-Host "Registered: $TaskName"
Write-Host "  When:    Mon-Fri 01:55 AM (Pacific local time)"
Write-Host "  Script:  $ScriptPath"
Write-Host "  Logs:    $env:USERPROFILE\.trading_agent\logs\"
Write-Host ""
Write-Host "Verify:  Get-ScheduledTask -TaskName $TaskName | Format-List"
Write-Host "Test now: Start-ScheduledTask -TaskName $TaskName"