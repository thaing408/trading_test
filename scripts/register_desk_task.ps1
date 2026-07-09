# Register Windows Task Scheduler: wake PC + run trading desk weekdays 01:55 AM Pacific.
# Run once as Administrator if registration fails due to permissions.

$ErrorActionPreference = "Stop"
$TaskName = "TradingAgentDeskSession"
$WakeTaskName = "TradingAgentDeskWake"
$ScriptPath = Join-Path $PSScriptRoot "start_desk_session.ps1"
$EnableWakePath = Join-Path $PSScriptRoot "enable_pc_wake.ps1"
$RepoRoot = Split-Path -Parent $PSScriptRoot

if (-not (Test-Path $ScriptPath)) {
    throw "Missing startup script: $ScriptPath"
}

# 1) OS-level wake timers (required; WakeToRun alone is not enough when set to "Important only")
if (Test-Path $EnableWakePath) {
    Write-Host "Configuring OS wake timers..."
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $EnableWakePath
}

# Prefer Windows PowerShell 5.1 for scheduled tasks.
$psExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
if (-not (Test-Path $psExe)) {
    $psExe = "powershell.exe"
}

function New-WakeCapableSettings {
    $params = @{
        AllowStartIfOnBatteries    = $true
        DontStopIfGoingOnBatteries = $true
        StartWhenAvailable         = $true
        ExecutionTimeLimit         = (New-TimeSpan -Hours 16)
        RestartCount               = 3
        RestartInterval            = (New-TimeSpan -Minutes 10)
        MultipleInstances          = "IgnoreNew"
    }
    try {
        return New-ScheduledTaskSettingsSet @params -WakeToRun
    } catch {
        return New-ScheduledTaskSettingsSet @params
    }
}

function Register-WakeTask {
    param(
        [string]$Name,
        [string]$Execute,
        [string]$Argument,
        [string]$WorkDir,
        [string]$AtTime,
        [string]$Description,
        [TimeSpan]$Limit
    )

    $action = New-ScheduledTaskAction -Execute $Execute -Argument $Argument -WorkingDirectory $WorkDir
    $trigger = New-ScheduledTaskTrigger -Weekly `
        -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
        -At $AtTime
    $settings = New-WakeCapableSettings
    if ($Limit.TotalMinutes -gt 0) {
        $settings.ExecutionTimeLimit = "PT{0}M" -f [int]$Limit.TotalMinutes
    }
    # Force wake flags even if the ctor ignored -WakeToRun on older builds
    $settings.WakeToRun = $true
    $settings.StartWhenAvailable = $true
    $settings.DisallowStartIfOnBatteries = $false
    $settings.StopIfGoingOnBatteries = $false

    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

    Register-ScheduledTask -TaskName $Name -Action $action -Trigger $trigger `
        -Settings $settings -Principal $principal -Description $Description -Force | Out-Null

    # Re-assert after register (some Windows builds drop WakeToRun silently)
    $task = Get-ScheduledTask -TaskName $Name
    $task.Settings.WakeToRun = $true
    $task.Settings.StartWhenAvailable = $true
    Set-ScheduledTask -InputObject $task | Out-Null
}

# 2) Early wake pulse at 01:50 — pure wake timer so the box is up before the desk job
Register-WakeTask `
    -Name $WakeTaskName `
    -Execute $psExe `
    -Argument "-NoProfile -Command `"Write-Host 'Trading desk wake pulse'; exit 0`"" `
    -WorkDir $RepoRoot `
    -AtTime "01:50AM" `
    -Description "Wake PC 5 minutes before Trading Agent desk session (Mon-Fri 01:50 AM Pacific)" `
    -Limit (New-TimeSpan -Minutes 5)

# 3) Main desk session at 01:55
Register-WakeTask `
    -Name $TaskName `
    -Execute $psExe `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`"" `
    -WorkDir $RepoRoot `
    -AtTime "01:55AM" `
    -Description "Trading Agent PST desk: wake PC, git pull, prep phases 1-4 via Discord" `
    -Limit (New-TimeSpan -Hours 16)

foreach ($name in @($WakeTaskName, $TaskName)) {
    $t = Get-ScheduledTask -TaskName $name
    $info = Get-ScheduledTaskInfo -TaskName $name
    Write-Host ""
    Write-Host "Registered: $name"
    Write-Host "  State:       $($t.State)"
    Write-Host "  WakeToRun:   $($t.Settings.WakeToRun)"
    Write-Host "  Next run:    $($info.NextRunTime)"
}

Write-Host ""
Write-Host "Script:  $ScriptPath"
Write-Host "Logs:    $env:USERPROFILE\.trading_agent\logs\"
Write-Host ""
Write-Host "PC will attempt to wake from sleep at 01:50 and run the desk at 01:55 (Mon-Fri)."
Write-Host "Note: cold power-off (full shutdown) cannot be woken by Task Scheduler; use Sleep/Hibernate."
