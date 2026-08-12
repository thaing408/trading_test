# Start PST trading desk: git pull, install deps, run prep session (phases 1-4 by default).
# Designed for Windows Task Scheduler (Mon-Fri 01:55 AM Pacific).

$ErrorActionPreference = "Continue"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

# Task Scheduler often uses a legacy code page; normalize console + Python I/O.
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
    chcp 65001 > $null
} catch { }

$logDir = Join-Path $env:USERPROFILE ".trading_agent\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$lockFile = Join-Path $logDir "desk_session.lock"

function Write-Log {
    param([string]$Message)
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] $Message"
    Write-Host $line
    if ($script:StartupLog) {
        Add-Content -Path $script:StartupLog -Value $line -Encoding UTF8 -ErrorAction SilentlyContinue
    }
}

function Convert-ToLogText {
    param($InputObject)
    if ($null -eq $InputObject) { return "" }
    if ($InputObject -is [System.Array]) {
        return ($InputObject | ForEach-Object { "$_" }) -join "`n"
    }
    return "$InputObject"
}

# Keep the machine awake for the full prep window (wait 02:00-06:25 + pipelines).
function Enable-DeskAwake {
    try {
        Add-Type -Namespace TradingAgent -Name Native -ErrorAction SilentlyContinue -MemberDefinition @"
[DllImport("kernel32.dll")]
public static extern uint SetThreadExecutionState(uint esFlags);
"@
        # ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED
        $flags = [uint32](0x80000000 -bor 0x00000001 -bor 0x00000040)
        [void][TradingAgent.Native]::SetThreadExecutionState($flags)
        return $true
    } catch {
        return $false
    }
}

function Disable-DeskAwake {
    try {
        if ("TradingAgent.Native" -as [type]) {
            # ES_CONTINUOUS only - clear previous request
            [void][TradingAgent.Native]::SetThreadExecutionState([uint32]0x80000000)
        }
    } catch { }
}

function Import-DotEnv {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return $false }
    Get-Content $Path -ErrorAction SilentlyContinue | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        $eq = $line.IndexOf("=")
        if ($eq -lt 1) { return }
        $name = $line.Substring(0, $eq).Trim()
        $value = $line.Substring($eq + 1).Trim()
        # Strip optional surrounding quotes
        if ($value.Length -ge 2) {
            if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
                ($value.StartsWith("'") -and $value.EndsWith("'"))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
        }
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
    return $true
}

function Resolve-Python {
    $candidates = @()
    if ($env:TRADING_AGENT_PYTHON) { $candidates += $env:TRADING_AGENT_PYTHON }
    $candidates += @(
        "$env:LOCALAPPDATA\Python\bin\python.exe",
        "$env:LOCALAPPDATA\Python\pythoncore-3.14-64\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python314\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
    )
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -and ($cmd.Source -notmatch "WindowsApps")) {
        $candidates += $cmd.Source
    }
    foreach ($c in $candidates) {
        if ($c -and (Test-Path -LiteralPath $c)) { return $c }
    }
    return $null
}

function Invoke-LoggedCommand {
    param(
        [string]$Label,
        [scriptblock]$ScriptBlock,
        [switch]$Critical
    )
    Write-Log $Label
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & $ScriptBlock 2>&1
        $code = $LASTEXITCODE
        if ($null -eq $code) { $code = 0 }
        $text = (Convert-ToLogText $output).Trim()
        if ($text) { Write-Log $text }
        if ($code -ne 0) {
            $msg = "$Label failed with exit code $code"
            if ($Critical) {
                Write-Log "ERROR: $msg"
                throw $msg
            }
            Write-Log "WARN: $msg (continuing)"
        }
        return $code
    } catch {
        if ($Critical) {
            Write-Log "ERROR: $Label exception: $_"
            throw
        }
        Write-Log "WARN: $Label exception: $_ (continuing)"
        return 1
    } finally {
        $ErrorActionPreference = $prevEap
    }
}

# --- weekend guard ---
$today = Get-Date
if ($today.DayOfWeek -eq "Saturday" -or $today.DayOfWeek -eq "Sunday") {
    Write-Host "Weekend - desk session not started."
    exit 0
}

$dateArg = $today.ToString("yyyy-MM-dd")
$script:StartupLog = Join-Path $logDir "desk_startup_$dateArg.log"
$sessionLog = Join-Path $logDir "desk_$dateArg.log"

# Prevent overlapping runs if a prior session is still active.
if (Test-Path $lockFile) {
    $lockAge = (Get-Date) - (Get-Item $lockFile).LastWriteTime
    if ($lockAge.TotalHours -lt 14) {
        Write-Log "Desk lock present ($([int]$lockAge.TotalMinutes)m old) - another session may still be running. Exiting."
        exit 0
    }
    Remove-Item $lockFile -Force -ErrorAction SilentlyContinue
}
New-Item -ItemType File -Force -Path $lockFile | Out-Null

try {
    Write-Log "=== Trading desk startup ==="
    Write-Log "Repo: $RepoRoot"
    Write-Log "Host: $env:COMPUTERNAME  User: $env:USERNAME"
    Write-Log "PWD:  $(Get-Location)"

    if (Enable-DeskAwake) {
        Write-Log "Sleep inhibited for desk session (SetThreadExecutionState)"
    } else {
        Write-Log "WARN: could not inhibit sleep; ensure wake timers remain enabled"
    }

    # Load .env before resolving Python / phase scope
    $envFile = Join-Path $RepoRoot ".env"
    if (Import-DotEnv $envFile) {
        Write-Log "Loaded .env from $envFile"
    } else {
        Write-Log "WARN: no .env at $envFile (using process/system env only)"
    }

    $Python = Resolve-Python
    if (-not $Python) {
        throw "Python not found. Set TRADING_AGENT_PYTHON in .env to a real python.exe (not WindowsApps shim)."
    }
    Write-Log "Python: $Python"
    $pyVer = & $Python --version 2>&1
    Write-Log "Python version: $(Convert-ToLogText $pyVer)"

    # Non-fatal: keep local tree if network/auth/dirty-worktree issues
    if (Get-Command git -ErrorAction SilentlyContinue) {
        $branch = (& git rev-parse --abbrev-ref HEAD 2>$null)
        if (-not $branch) { $branch = "unknown" }
        Write-Log "Git branch: $branch"
        # Fetch + merge origin/main into current branch (repo tracks origin/main from master)
        Invoke-LoggedCommand "Pulling latest from origin/main ..." {
            git pull --ff-only origin main
        } | Out-Null
    } else {
        Write-Log "WARN: git not on PATH; skipping pull"
    }

    # Non-fatal with retry: package may already be installed
    $pipOk = $false
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        $code = Invoke-LoggedCommand "Installing package dependencies (attempt $attempt/3) ..." {
            & $Python -m pip install -e ".[dev]" -q
        }
        if ($code -eq 0) { $pipOk = $true; break }
        if ($attempt -lt 3) { Start-Sleep -Seconds 5 }
    }
    if (-not $pipOk) {
        Write-Log "WARN: pip install did not succeed after 3 attempts (continuing with existing install)"
    }

    # Single-line -c avoids PowerShell here-string parse failures under Task Scheduler / PS 5.1.
    Invoke-LoggedCommand "Preflight: import trading_agent + UTF-8 smoke test ..." {
        $pySmoke = "import os; os.environ.setdefault('PYTHONUTF8','1'); from trading_agent.runtime.stdio import configure_stdio, safe_print; configure_stdio(); safe_print('Phase scope: intelligence to cio_review (smoke)'); import trading_agent"
        & $Python -c $pySmoke
    } -Critical | Out-Null

    # Full weekday desk by default: intelligence through CIO daily review (incl. intraday
    # PT/SL + discovery refreshes at 07:00 / 09:30 / 11:00 PT). Always start from
    # intelligence so a late StartWhenAvailable catch-up still runs morning prep.
    # Override with TRADING_AGENT_UNTIL_PHASE=preopen for prep-only.
    # full day includes evening_scan (18:00 ET swing + multi-method)
    $untilRaw = if ($env:TRADING_AGENT_UNTIL_PHASE) { $env:TRADING_AGENT_UNTIL_PHASE.Trim() } else { "evening_scan" }
    if ($untilRaw -in @("full", "all", "day", "fullday", "full_day")) { $untilRaw = "evening_scan" }
    if ($untilRaw -eq "cio_review") {
        # legacy alias still valid — stops before 6pm ET evening scanners
    }
    if ($untilRaw -in @("prep", "pre-market", "premarket")) { $untilRaw = "preopen" }
    $untilPhase = $untilRaw
    $fromPhase = if ($env:TRADING_AGENT_FROM_PHASE) { $env:TRADING_AGENT_FROM_PHASE.Trim() } else { "intelligence" }

    Write-Log "Starting desk session for $dateArg (from-phase: $fromPhase, until-phase: $untilPhase)"
    Write-Log "Session log: $sessionLog"
    if ($untilPhase -eq "cio_review") {
        Write-Log "Mode: FULL DAY (intraday PT/SL + discovery refreshes + close reviews)"
    } elseif ($untilPhase -eq "preopen") {
        Write-Log "Mode: PREP ONLY (phases 1-4; no intraday desk)"
    }

    # Task Scheduler defaults to a legacy code page; force UTF-8 for desk output (em dashes, arrows, etc.).
    $env:PYTHONUTF8 = "1"
    $env:PYTHONIOENCODING = "utf-8"
    if (-not $env:TRADING_AGENT_FROM_PHASE) {
        $env:TRADING_AGENT_FROM_PHASE = "intelligence"
    }
    if (-not $env:TRADING_AGENT_UNTIL_PHASE) {
        $env:TRADING_AGENT_UNTIL_PHASE = "cio_review"
    }
    if (-not $env:TRADING_AGENT_DISCOVERY_REFRESH) {
        $env:TRADING_AGENT_DISCOVERY_REFRESH = "1"
    }

    # Start-Process gives a reliable exit code under Task Scheduler (pipeline LASTEXITCODE is flaky).
    $stdoutFile = Join-Path $logDir "desk_session_stdout_$dateArg.log"
    $stderrFile = Join-Path $logDir "desk_session_stderr_$dateArg.log"
    $argList = @(
        "-m", "trading_agent", "session",
        "--date", $dateArg,
        "--from-phase", $fromPhase,
        "--until-phase", $untilPhase,
        "--output", $sessionLog
    )

    $proc = Start-Process -FilePath $Python `
        -ArgumentList $argList `
        -WorkingDirectory $RepoRoot `
        -NoNewWindow `
        -Wait `
        -PassThru `
        -RedirectStandardOutput $stdoutFile `
        -RedirectStandardError $stderrFile

    foreach ($f in @($stdoutFile, $stderrFile)) {
        if (Test-Path $f) {
            Get-Content $f -ErrorAction SilentlyContinue | ForEach-Object {
                Write-Host $_
                Add-Content -Path $script:StartupLog -Value $_ -Encoding UTF8 -ErrorAction SilentlyContinue
            }
        }
    }

    $code = $proc.ExitCode
    if ($null -eq $code) { $code = 1 }

    if ($code -ne 0) {
        Write-Log "WARN: desk session failed (exit $code); retrying once after 30s ..."
        Start-Sleep -Seconds 30
        $proc = Start-Process -FilePath $Python `
            -ArgumentList $argList `
            -WorkingDirectory $RepoRoot `
            -NoNewWindow `
            -Wait `
            -PassThru `
            -RedirectStandardOutput $stdoutFile `
            -RedirectStandardError $stderrFile
        $code = $proc.ExitCode
        if ($null -eq $code) { $code = 1 }
    }

    Write-Log "Desk session exited with code $code"
    exit $code
} catch {
    Write-Log "FATAL: $_"
    if ($_.ScriptStackTrace) {
        Write-Log $_.ScriptStackTrace
    }
    exit 1
} finally {
    Disable-DeskAwake
    if (Test-Path $lockFile) {
        Remove-Item $lockFile -Force -ErrorAction SilentlyContinue
    }
}
