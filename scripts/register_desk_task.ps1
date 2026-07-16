# Register Windows Task Scheduler: wake PC + run trading desk weekdays 01:55 AM Pacific.
# IMPORTANT: Task actions call pythonw.exe (not powershell -WindowStyle Hidden).
# Defender flags hidden PowerShell sub-execution as Trojan:Win32/PowhidSubExec.B.

$ErrorActionPreference = "Stop"
$TaskName = "TradingAgentDeskSession"
$WakeTaskName = "TradingAgentDeskWake"
$ScriptPath = Join-Path $PSScriptRoot "start_desk_session.py"
$EnableWakePath = Join-Path $PSScriptRoot "enable_pc_wake.ps1"
$RepoRoot = Split-Path -Parent $PSScriptRoot

if (-not (Test-Path $ScriptPath)) {
    throw "Missing startup script: $ScriptPath"
}

# 1) OS-level wake timers
if (Test-Path $EnableWakePath) {
    Write-Host "Configuring OS wake timers..."
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $EnableWakePath
}

# Resolve python / pythonw (prefer pythonw for no console; no Defender Powhid heuristic)
function Resolve-PythonW {
    $candidates = @()
    if ($env:TRADING_AGENT_PYTHON) {
        $p = $env:TRADING_AGENT_PYTHON
        $w = $p -replace 'python\.exe$', 'pythonw.exe'
        $candidates += @($w, $p)
    }
    $envFile = Join-Path $RepoRoot ".env"
    if (Test-Path $envFile) {
        Get-Content $envFile | ForEach-Object {
            if ($_ -match '^\s*TRADING_AGENT_PYTHON\s*=\s*(.+)$') {
                $p = $Matches[1].Trim().Trim('"').Trim("'")
                $w = $p -replace 'python\.exe$', 'pythonw.exe'
                $candidates += @($w, $p)
            }
        }
    }
    $candidates += @(
        "$env:LOCALAPPDATA\Python\bin\pythonw.exe",
        "$env:LOCALAPPDATA\Python\bin\python.exe",
        "$env:LOCALAPPDATA\Python\pythoncore-3.14-64\pythonw.exe",
        "$env:LOCALAPPDATA\Python\pythoncore-3.14-64\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python314\pythonw.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python314\python.exe"
    )
    foreach ($c in $candidates) {
        if ($c -and (Test-Path -LiteralPath $c)) { return $c }
    }
    throw "Python not found. Set TRADING_AGENT_PYTHON in .env"
}

$Python = Resolve-PythonW
Write-Host "Launcher Python: $Python"

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
    $settings.WakeToRun = $true
    $settings.StartWhenAvailable = $true
    $settings.DisallowStartIfOnBatteries = $false
    $settings.StopIfGoingOnBatteries = $false
    try { $settings.Hidden = $true } catch { }

    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

    Register-ScheduledTask -TaskName $Name -Action $action -Trigger $trigger `
        -Settings $settings -Principal $principal -Description $Description -Force | Out-Null

    $task = Get-ScheduledTask -TaskName $Name
    $task.Settings.WakeToRun = $true
    $task.Settings.StartWhenAvailable = $true
    try { $task.Settings.Hidden = $true } catch { }
    Set-ScheduledTask -InputObject $task | Out-Null
}

# 2) Wake pulse at 01:50 — use cmd.exe (not hidden PowerShell) to avoid Defender
$cmdExe = Join-Path $env:SystemRoot "System32\cmd.exe"
Register-WakeTask `
    -Name $WakeTaskName `
    -Execute $cmdExe `
    -Argument "/c exit 0" `
    -WorkDir $RepoRoot `
    -AtTime "01:50AM" `
    -Description "Wake PC 5 minutes before Trading Agent desk session (Mon-Fri 01:50 AM Pacific)" `
    -Limit (New-TimeSpan -Minutes 5)

# 3) Main desk — pythonw/python running start_desk_session.py (no PowerShell)
Register-WakeTask `
    -Name $TaskName `
    -Execute $Python `
    -Argument "`"$ScriptPath`"" `
    -WorkDir $RepoRoot `
    -AtTime "01:55AM" `
    -Description "Trading Agent PST desk via pythonw (no PowerShell; avoids Defender PowhidSubExec)" `
    -Limit (New-TimeSpan -Hours 16)

foreach ($name in @($WakeTaskName, $TaskName)) {
    $t = Get-ScheduledTask -TaskName $name
    $info = Get-ScheduledTaskInfo -TaskName $name
    $a = $t.Actions[0]
    Write-Host ""
    Write-Host "Registered: $name"
    Write-Host "  State:       $($t.State)"
    Write-Host "  Execute:     $($a.Execute)"
    Write-Host "  Args:        $($a.Arguments)"
    Write-Host "  WakeToRun:   $($t.Settings.WakeToRun)"
    Write-Host "  Next run:    $($info.NextRunTime)"
}

Write-Host ""
Write-Host "Script:  $ScriptPath"
Write-Host "Logs:    $env:USERPROFILE\.trading_agent\logs\"
Write-Host "Note: uses pythonw/python - not powershell -WindowStyle Hidden (Defender safe)."
