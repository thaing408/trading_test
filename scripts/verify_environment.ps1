# Verify trading_agent is ready to run (manual or scheduled).

$ErrorActionPreference = "Continue"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$script:allOk = $true
function Check($label, $pass, $detail) {
    $script:allOk = $script:allOk -and $pass
    $mark = if ($pass) { "OK" } else { "FAIL" }
    Write-Host "[$mark] $label - $detail"
}

Write-Host "=== Trading Agent Environment Check ==="
Write-Host "Repo: $RepoRoot"
Write-Host "Time: $(Get-Date) ($([TimeZoneInfo]::Local.Id))"
Write-Host ""

# Python
$Python = $env:TRADING_AGENT_PYTHON
if (-not $Python -or -not (Test-Path $Python)) {
    $Python = "$env:LOCALAPPDATA\Python\bin\python.exe"
}
$pyOk = Test-Path $Python
Check "Python" $pyOk $(if ($pyOk) { $Python } else { "not found - set TRADING_AGENT_PYTHON" })

if ($pyOk) {
    $ver = & $Python --version 2>&1
    Check "Python version" ($ver -match "Python 3\.1[0-9]") $ver
    & $Python -c "import trading_agent; import yfinance; import requests; import dotenv" 2>$null | Out-Null
    $importOk = $LASTEXITCODE -eq 0
    Check "Package install" $importOk $(if ($importOk) { "trading_agent importable" } else { "run: pip install -e .[dev]" })
}

# Git
$gitOk = (Get-Command git -ErrorAction SilentlyContinue) -ne $null
Check "Git" $gitOk $(if ($gitOk) { (git remote get-url origin 2>$null) } else { "git not on PATH" })

# .env
$envFile = Join-Path $RepoRoot ".env"
$hasEnv = Test-Path $envFile
Check ".env file" $hasEnv $(if ($hasEnv) { $envFile } else { "copy .env.example to .env" })

# Discord token (researcher .env or local)
$researcherEnv = "C:\Personal\Scripts\researcher\.env"
$token = $env:DISCORD_TOKEN
if (-not $token -and (Test-Path $researcherEnv)) {
    Get-Content $researcherEnv | ForEach-Object {
        if ($_ -match '^\s*DISCORD_TOKEN=(.+)$') { $token = $matches[1].Trim() }
    }
}
$channel = $env:DISCORD_CHANNEL_ID
if (-not $channel -and $hasEnv) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*DISCORD_CHANNEL_ID=(.+)$') { $channel = $matches[1].Trim() }
    }
}
Check "Discord token" ([bool]$token) $(if ($token) { "set (from env or researcher)" } else { "missing DISCORD_TOKEN" })
Check "Discord channel" ([bool]$channel) $(if ($channel) { "channel $channel" } else { "set DISCORD_CHANNEL_ID in .env" })

# Scheduled task
$task = Get-ScheduledTask -TaskName "TradingAgentDeskSession" -ErrorAction SilentlyContinue
$taskOk = $null -ne $task
Check "Scheduled task" $taskOk $(if ($taskOk) { "state=$($task.State)" } else { "run scripts/setup_desk_automation.ps1" })
if ($taskOk) {
    $info = Get-ScheduledTaskInfo -TaskName "TradingAgentDeskSession"
    Check "Next run" ($null -ne $info.NextRunTime) " $($info.NextRunTime)"
    $last = $info.LastTaskResult
    # 267011 = never run; 0 = success. Prior failures are informational once the script is hardened.
    if ($info.LastRunTime -and $info.LastRunTime.Year -gt 2000) {
        Check "Last task result" $true "exit=$last at $($info.LastRunTime) (historical; next run uses hardened script)"
    } else {
        Check "Last task result" $true "not run yet"
    }
    $startScript = Join-Path $RepoRoot "scripts\start_desk_session.ps1"
    $startText = if (Test-Path $startScript) { Get-Content $startScript -Raw } else { "" }
    $safePull = ($startText -match "Invoke-LoggedCommand") -and ($startText -match "from-phase")
    Check "Startup script hardened" $safePull $(if ($safePull) { "git/pip non-fatal + from-phase set" } else { "update scripts/start_desk_session.ps1" })
    $wakeOk = [bool]$task.Settings.WakeToRun
    Check "Task WakeToRun" $wakeOk $(if ($wakeOk) { "enabled (will wake from sleep)" } else { "disabled - re-run register_desk_task.ps1" })
}
$wakeTask = Get-ScheduledTask -TaskName "TradingAgentDeskWake" -ErrorAction SilentlyContinue
if ($wakeTask) {
    $wi = Get-ScheduledTaskInfo -TaskName "TradingAgentDeskWake"
    Check "Wake pulse task" ([bool]$wakeTask.Settings.WakeToRun) "01:50 AM next=$($wi.NextRunTime) WakeToRun=$($wakeTask.Settings.WakeToRun)"
} else {
    Check "Wake pulse task" $false "missing - re-run register_desk_task.ps1"
}
$rtcRaw = powercfg /query SCHEME_CURRENT SUB_SLEEP bd3b718a-0680-4d9d-8ab2-e1d2b4ac806d 2>$null
$rtcAc = $null
foreach ($line in $rtcRaw) {
    if ($line -match "Current AC Power Setting Index:\s*0x([0-9a-fA-F]+)") {
        $rtcAc = [Convert]::ToInt32($matches[1], 16)
    }
}
Check "OS wake timers" ($rtcAc -eq 1) $(if ($rtcAc -eq 1) { "Enabled" } elseif ($rtcAc -eq 2) { "Important only - run enable_pc_wake.ps1" } else { "Disabled - run enable_pc_wake.ps1" })
Check "Logged-in user" ([bool]$env:USERNAME) "Interactive logon as $env:USERNAME - stay signed in (Sleep/Hibernate OK; full Shutdown will not auto-power-on)"

# Phase scope
$until = $env:TRADING_AGENT_UNTIL_PHASE
if (-not $until -and $hasEnv) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*TRADING_AGENT_UNTIL_PHASE=(.+)$') { $until = $matches[1].Trim() }
    }
}
if (-not $until) { $until = "preopen (default)" }
Check "Phase scope" $true "until-phase=$until"

Write-Host ""
if ($script:allOk) {
    Write-Host "READY - environment OK for automatic run tomorrow."
    exit 0
} else {
    Write-Host "NOT READY - fix FAIL items above before tomorrow."
    exit 1
}
