# Start the full PST trading desk session (runs all day, posts to Discord).
# Auto-updates from GitHub, installs deps, then launches the 7-phase desk.

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$logDir = Join-Path $env:USERPROFILE ".trading_agent\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Write-Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] $msg"
    Write-Host $line
    Add-Content -Path $script:StartupLog -Value $line -Encoding UTF8
}

$today = Get-Date
if ($today.DayOfWeek -eq "Saturday" -or $today.DayOfWeek -eq "Sunday") {
    Write-Host "Weekend — desk session not started."
    exit 0
}

$dateArg = $today.ToString("yyyy-MM-dd")
$script:StartupLog = Join-Path $logDir "desk_startup_$dateArg.log"
$sessionLog = Join-Path $logDir "desk_$dateArg.log"

Write-Log "=== Trading desk startup ==="
Write-Log "Repo: $RepoRoot"

# Resolve Python (scheduled tasks may not have WindowsApps shim on PATH)
$Python = $env:TRADING_AGENT_PYTHON
if (-not $Python -or -not (Test-Path $Python)) {
    $candidates = @(
        "$env:LOCALAPPDATA\Python\bin\python.exe",
        "$env:LOCALAPPDATA\Python\pythoncore-3.14-64\python.exe",
        (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
    )
    foreach ($c in $candidates) {
        if ($c -and (Test-Path $c)) { $Python = $c; break }
    }
}
if (-not $Python) { throw "Python not found. Set TRADING_AGENT_PYTHON." }
Write-Log "Python: $Python"

# Auto-update from GitHub
Write-Log "Pulling latest from origin/main ..."
$pullOut = git pull origin main 2>&1
Write-Log ($pullOut | Out-String).Trim()

# Install / refresh package + dependencies after pull
Write-Log "Installing package dependencies ..."
& $Python -m pip install -e ".[dev]" -q 2>&1 | ForEach-Object { Write-Log $_ }

# Load local .env into process (Discord channel id, etc.)
$envFile = Join-Path $RepoRoot ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
    Write-Log "Loaded .env from $envFile"
}

# Phases 1-4 only (no brokerage / intraday execution): intelligence → research → CIO → pre-open
$untilPhase = if ($env:TRADING_AGENT_UNTIL_PHASE) { $env:TRADING_AGENT_UNTIL_PHASE } else { "preopen" }
Write-Log "Starting desk session for $dateArg (phases through: $untilPhase, log: $sessionLog)"
& $Python -m trading_agent session --date $dateArg --until-phase $untilPhase --output $sessionLog
$code = $LASTEXITCODE
Write-Log "Desk session exited with code $code"
exit $code