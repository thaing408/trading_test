# Register Windows Task Scheduler job for daily PST trading desk.
# Runs weekdays at 01:55 AM Pacific (5 min before Market Intelligence at 02:00).

$ErrorActionPreference = "Stop"
$TaskName = "TradingAgentDeskSession"
$ScriptPath = Join-Path $PSScriptRoot "start_desk_session.ps1"

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""

# 01:55 local time — adjust if machine is not on Pacific time
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
    -At "01:55AM"

$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "Trading Agent PST desk: intelligence through CIO review" -Force

Write-Host "Registered scheduled task: $TaskName"
Write-Host "Script: $ScriptPath"
Write-Host "Note: trigger uses local machine timezone — set system clock to Pacific or edit the trigger."