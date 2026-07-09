# Register Windows Task Scheduler: auto-update + run trading desk weekdays 01:55 AM Pacific.
# Run once as Administrator if registration fails due to permissions.

$ErrorActionPreference = "Stop"
$TaskName = "TradingAgentDeskSession"
$ScriptPath = Join-Path $PSScriptRoot "start_desk_session.ps1"
$RepoRoot = Split-Path -Parent $PSScriptRoot

if (-not (Test-Path $ScriptPath)) {
    throw "Missing startup script: $ScriptPath"
}

# Prefer Windows PowerShell 5.1 for scheduled tasks (more stable under Task Scheduler than pwsh).
$psExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
if (-not (Test-Path $psExe)) {
    $psExe = "powershell.exe"
}

$action = New-ScheduledTaskAction `
    -Execute $psExe `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`"" `
    -WorkingDirectory $RepoRoot

# Machine is Pacific — 01:55 AM local = 5 min before Market Intelligence (02:00)
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At "01:55AM"

$settingsParams = @{
    AllowStartIfOnBatteries    = $true
    DontStopIfGoingOnBatteries = $true
    StartWhenAvailable         = $true
    ExecutionTimeLimit         = (New-TimeSpan -Hours 16)
    RestartCount               = 3
    RestartInterval            = (New-TimeSpan -Minutes 10)
    MultipleInstances          = "IgnoreNew"
}
# Wake the PC if it is sleeping (supported on most Windows builds).
try {
    $settings = New-ScheduledTaskSettingsSet @settingsParams -WakeToRun
} catch {
    $settings = New-ScheduledTaskSettingsSet @settingsParams
}

# Interactive: runs in the logged-on user session (needs user signed in, or StartWhenAvailable after login).
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description "Trading Agent PST desk: git pull + prep phases 1-4 (through preopen) via Discord" -Force | Out-Null

Write-Host "Registered: $TaskName"
Write-Host "  When:    Mon-Fri 01:55 AM (Pacific local time)"
Write-Host "  Script:  $ScriptPath"
Write-Host "  Shell:   $psExe"
Write-Host "  Logs:    $env:USERPROFILE\.trading_agent\logs\"
Write-Host ""
Write-Host "Verify:  Get-ScheduledTask -TaskName $TaskName | Format-List"
Write-Host "Test now: Start-ScheduledTask -TaskName $TaskName"
