# Verify trading_agent is ready to run (manual or scheduled).
# Core READY does not require weekday automation (optional for new installs).

$ErrorActionPreference = 'Continue'
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$script:allOk = $true
function Check($label, $pass, $detail) {
    $script:allOk = $script:allOk -and $pass
    $mark = if ($pass) { 'OK' } else { 'FAIL' }
    Write-Host "[$mark] $label - $detail"
}

function Info($label, $detail) {
    Write-Host "[INFO] $label - $detail"
}

function Import-DotEnvFile([string]$Path) {
    if (-not (Test-Path $Path)) { return }
    Get-Content $Path -ErrorAction SilentlyContinue | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith('#')) { return }
        $eq = $line.IndexOf('=')
        if ($eq -lt 1) { return }
        $name = $line.Substring(0, $eq).Trim()
        $value = $line.Substring($eq + 1).Trim()
        if ($value.Length -ge 2 -and (
            ($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))
        )) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        $existing = [Environment]::GetEnvironmentVariable($name, 'Process')
        if ([string]::IsNullOrEmpty($existing)) {
            [Environment]::SetEnvironmentVariable($name, $value, 'Process')
        }
    }
}

Write-Host '=== Trading Agent Environment Check ==='
Write-Host "Repo: $RepoRoot"
Write-Host "Time: $(Get-Date) ($([TimeZoneInfo]::Local.Id))"
Write-Host ''

$envFile = Join-Path $RepoRoot '.env'
Import-DotEnvFile $envFile

# Python
$Python = $env:TRADING_AGENT_PYTHON
if (-not $Python -or -not (Test-Path $Python)) {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Python\bin\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python314\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe')
    )
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -and ($cmd.Source -notmatch 'WindowsApps')) {
        $candidates += $cmd.Source
    }
    foreach ($c in $candidates) {
        if ($c -and (Test-Path $c)) { $Python = $c; break }
    }
}
$pyOk = $Python -and (Test-Path $Python)
Check 'Python' $pyOk $(if ($pyOk) { $Python } else { 'not found - set TRADING_AGENT_PYTHON or re-run scripts/install.ps1' })

if ($pyOk) {
    $ver = & $Python --version 2>&1
    Check 'Python version' ($ver -match 'Python 3\.(1[0-9]|[2-9][0-9])') $ver
    & $Python -c 'import trading_agent; import yfinance; import requests; import dotenv' 2>$null | Out-Null
    $importOk = $LASTEXITCODE -eq 0
    Check 'Package install' $importOk $(if ($importOk) { 'trading_agent importable' } else { 'run: pip install -e .[dev]  or scripts/install.ps1' })

    & $Python -c "from trading_agent.runtime.stdio import configure_stdio, safe_print; configure_stdio(); safe_print('Phase scope: intelligence -> preopen (smoke)')" 2>$null | Out-Null
    $utfOk = $LASTEXITCODE -eq 0
    Check 'UTF-8 console smoke' $utfOk $(if ($utfOk) { 'safe_print OK' } else { 'stdio hardening missing — pull latest' })
}

# Git
$gitOk = (Get-Command git -ErrorAction SilentlyContinue) -ne $null
Check 'Git' $gitOk $(if ($gitOk) { (git remote get-url origin 2>$null) } else { 'git not on PATH (optional for manual runs)' })

# .env
$hasEnv = Test-Path $envFile
Check '.env file' $hasEnv $(if ($hasEnv) { $envFile } else { 'run scripts/install.ps1 (or copy .env.example to .env)' })

# Discord delivery / explicit opt-out
$dry = $env:TRADING_AGENT_DRY_RUN
$noDiscord = $env:TRADING_AGENT_NO_DISCORD
$optOut = ($dry -match '^(1|true|yes)$') -or ($noDiscord -match '^(1|true|yes)$')
$token = $env:DISCORD_TOKEN
$webhook = $env:DISCORD_WEBHOOK_URL
$channel = $env:DISCORD_CHANNEL_ID

# Optional legacy author path (never required)
$researcherEnv = 'C:\Personal\Scripts\researcher\.env'
if (-not $token -and (Test-Path $researcherEnv)) {
    Get-Content $researcherEnv | ForEach-Object {
        if ($_ -match '^\s*DISCORD_TOKEN=(.+)$') { $token = $matches[1].Trim() }
    }
}

if ($optOut) {
    Check 'Discord delivery' $true 'opted out (dry-run / no-discord) - safe local runs only'
} elseif ($webhook -and $webhook.StartsWith('https://')) {
    Check 'Discord delivery' $true 'webhook configured'
} elseif ($token -and $channel) {
    Check 'Discord delivery' $true "bot token + channel $channel"
} elseif ($token -and -not $channel) {
    Check 'Discord delivery' $false 'DISCORD_CHANNEL_ID missing'
} elseif ($channel -and -not $token -and -not $webhook) {
    Check 'Discord delivery' $false 'set DISCORD_TOKEN or DISCORD_WEBHOOK_URL (or dry-run via install)'
} else {
    Check 'Discord delivery' $false 'no credentials - re-run scripts/install.ps1'
}

if ($channel) {
    Info 'Discord channel' $channel
}

$fmpKey = $env:FMP_API_KEY
if ($fmpKey) {
    try {
        $r = Invoke-RestMethod -Uri "https://financialmodelingprep.com/stable/quote?symbol=AAPL&apikey=$fmpKey" -TimeoutSec 15
        $fmpOk = $null -ne $r -and ($r.Count -gt 0 -or $r.symbol)
        Check 'FMP API key' $fmpOk $(if ($fmpOk) { 'authenticated (quote OK)' } else { 'key present but quote failed' })
        Info 'FMP calendar' 'macro calendar needs Starter+; free tier uses earnings calendar fallback'
    } catch {
        Check 'FMP API key' $false "request failed: $($_.Exception.Message)"
    }
} else {
    Info 'FMP API key' 'not set (optional — calendar/backup news)'
}

# Optional automation (does not gate READY for new installs)
Write-Host ''
Write-Host '--- Optional automation (informational) ---'
$task = Get-ScheduledTask -TaskName 'TradingAgentDeskSession' -ErrorAction SilentlyContinue
if ($null -ne $task) {
    $info = Get-ScheduledTaskInfo -TaskName 'TradingAgentDeskSession'
    Info 'Scheduled task' "state=$($task.State) next=$($info.NextRunTime) WakeToRun=$($task.Settings.WakeToRun)"
    $startScript = Join-Path $RepoRoot 'scripts\start_desk_session.ps1'
    $startText = if (Test-Path $startScript) { Get-Content $startScript -Raw } else { '' }
    $safePull = ($startText -match 'Invoke-LoggedCommand') -and ($startText -match 'from-phase') -and ($startText -match 'PYTHONUTF8')
    Info 'Startup script' $(if ($safePull) { 'hardened' } else { 'update scripts/start_desk_session.ps1' })

    $action = $task.Actions | Select-Object -First 1
    $taskScript = $null
    $taskWorkDir = $action.WorkingDirectory
    if ($action.Arguments -match '"([^"]+start_desk_session\.ps1)"') {
        $taskScript = $matches[1]
    }
    $pathOk = ($taskWorkDir -eq $RepoRoot) -and ($taskScript -eq $startScript)
    Check 'Task paths' $pathOk $(if ($pathOk) { "repo=$RepoRoot" } else { "task points to $taskWorkDir / $taskScript - re-run scripts/setup_desk_automation.ps1" })
} else {
    Info 'Scheduled task' 'not registered - run scripts/setup_desk_automation.ps1 when ready'
}
$wakeTask = Get-ScheduledTask -TaskName 'TradingAgentDeskWake' -ErrorAction SilentlyContinue
if ($wakeTask) {
    $wi = Get-ScheduledTaskInfo -TaskName 'TradingAgentDeskWake'
    Info 'Wake pulse task' "next=$($wi.NextRunTime) WakeToRun=$($wakeTask.Settings.WakeToRun)"
} else {
    Info 'Wake pulse task' 'not registered'
}
$rtcRaw = powercfg /query SCHEME_CURRENT SUB_SLEEP bd3b718a-0680-4d9d-8ab2-e1d2b4ac806d 2>$null
$rtcAc = $null
foreach ($line in $rtcRaw) {
    if ($line -match 'Current AC Power Setting Index:\s*0x([0-9a-fA-F]+)') {
        $rtcAc = [Convert]::ToInt32($matches[1], 16)
    }
}
$rtcLabel = switch ($rtcAc) {
    1 { 'Enabled' }
    2 { 'Important only' }
    0 { 'Disabled' }
    default { 'unknown' }
}
Info 'OS wake timers' $rtcLabel
Info 'Logged-in user' "$env:USERNAME (Sleep/Hibernate OK for WakeToRun; full Shutdown will not auto-power-on)"

$until = $env:TRADING_AGENT_UNTIL_PHASE
if (-not $until) { $until = 'preopen (default if unset in session scripts)' }
Info 'Phase scope' "until-phase=$until"

Write-Host ''
if ($script:allOk) {
    Write-Host 'READY - core environment OK.'
    exit 0
} else {
    Write-Host 'NOT READY - fix FAIL items above (or re-run scripts/install.ps1).'
    exit 1
}
