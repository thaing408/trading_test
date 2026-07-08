# Start the full PST trading desk session (runs all day, posts to Discord).
# Requires: python, trading_agent package, .env with DISCORD_CHANNEL_ID,
# and DISCORD_TOKEN from C:\Personal\Scripts\researcher\.env

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$today = Get-Date
if ($today.DayOfWeek -eq "Saturday" -or $today.DayOfWeek -eq "Sunday") {
    Write-Host "Weekend — desk session not started."
    exit 0
}

$dateArg = $today.ToString("yyyy-MM-dd")
$logDir = Join-Path $env:USERPROFILE ".trading_agent\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir "desk_$dateArg.log"

Write-Host "Starting trading desk session for $dateArg ..."
python -m trading_agent session --date $dateArg --output $logFile
exit $LASTEXITCODE