# Effortless Windows install for new users:
#   collect config -> pip install -> write .env -> verify -> optional automation -> fixture dry-run
#
# Interactive:
#   powershell -ExecutionPolicy Bypass -File scripts\install.ps1
#
# Non-interactive (CI / harness):
#   powershell -ExecutionPolicy Bypass -File scripts\install.ps1 -NonInteractive `
#     -DeliveryMode dry_run -SkipAutomation

[CmdletBinding()]
param(
    [switch]$NonInteractive,
    [ValidateSet('bot', 'webhook', 'dry_run', 'no_discord')]
    [string]$DeliveryMode = '',
    [string]$DiscordToken = '',
    [string]$DiscordWebhookUrl = '',
    [string]$DiscordChannelId = '',
    [string]$UntilPhase = '',
    [string]$PythonPath = '',
    [double]$PortfolioValue = 0,
    [switch]$EnableAutomation,
    [switch]$SkipAutomation,
    [switch]$SkipFirstRun,
    [switch]$SkipPip,
    [string]$Timezone = 'America/Los_Angeles'
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

function Write-Step([string]$msg) {
    Write-Host ''
    Write-Host "==> $msg" -ForegroundColor Cyan
}
function Write-Ok([string]$msg) {
    Write-Host "  OK  $msg" -ForegroundColor Green
}
function Write-WarnMsg([string]$msg) {
    Write-Host "  WARN $msg" -ForegroundColor Yellow
}
function Write-ErrMsg([string]$msg) {
    Write-Host "  FAIL $msg" -ForegroundColor Red
}

function Read-Default {
    param([string]$Prompt, [string]$Default = '')
    if ($NonInteractive) { return $Default }
    $suffix = if ($Default -ne '') { " [$Default]" } else { '' }
    $raw = Read-Host ($Prompt + $suffix)
    if ([string]::IsNullOrWhiteSpace($raw)) { return $Default }
    return $raw.Trim()
}

function Read-YesNo {
    param([string]$Prompt, [bool]$DefaultYes = $true)
    if ($NonInteractive) { return $DefaultYes }
    $hint = if ($DefaultYes) { 'Y/n' } else { 'y/N' }
    $raw = Read-Host "$Prompt ($hint)"
    if ([string]::IsNullOrWhiteSpace($raw)) { return $DefaultYes }
    return @('y', 'yes', '1', 'true') -contains $raw.Trim().ToLower()
}

function Resolve-InstallPython {
    param([string]$Preferred)
    $candidates = @()
    if ($Preferred) { $candidates += $Preferred }
    if ($env:TRADING_AGENT_PYTHON) { $candidates += $env:TRADING_AGENT_PYTHON }
    $candidates += @(
        (Join-Path $env:LOCALAPPDATA 'Python\bin\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python314\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe')
    )
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -and ($cmd.Source -notmatch 'WindowsApps')) {
        $candidates += $cmd.Source
    }
    $cmd3 = Get-Command python3 -ErrorAction SilentlyContinue
    if ($cmd3 -and $cmd3.Source -and ($cmd3.Source -notmatch 'WindowsApps')) {
        $candidates += $cmd3.Source
    }
    foreach ($c in $candidates) {
        if ($c -and (Test-Path -LiteralPath $c)) {
            return (Resolve-Path -LiteralPath $c).Path
        }
    }
    return $null
}

function Import-ExistingEnvDefaults {
    param([string]$Path)
    $map = @{}
    if (-not (Test-Path -LiteralPath $Path)) { return $map }
    Get-Content -LiteralPath $Path -ErrorAction SilentlyContinue | ForEach-Object {
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
        $map[$name] = $value
        if ([string]::IsNullOrEmpty([Environment]::GetEnvironmentVariable($name, 'Process'))) {
            [Environment]::SetEnvironmentVariable($name, $value, 'Process')
        }
    }
    return $map
}

function Infer-DeliveryModeFromEnv {
    param([hashtable]$Map)
    $dry = $Map['TRADING_AGENT_DRY_RUN']
    $noD = $Map['TRADING_AGENT_NO_DISCORD']
    if (($dry -match '^(1|true|yes)$') -or ($noD -match '^(1|true|yes)$')) {
        if ($noD -match '^(1|true|yes)$' -and -not ($dry -match '^(1|true|yes)$')) { return 'no_discord' }
        return 'dry_run'
    }
    if ($Map['DISCORD_WEBHOOK_URL'] -and $Map['DISCORD_WEBHOOK_URL'].StartsWith('https://')) { return 'webhook' }
    if ($Map['DISCORD_TOKEN']) { return 'bot' }
    return ''
}

Write-Host '============================================'
Write-Host ' Trading Agent - Windows Install Wizard'
Write-Host " Repo: $RepoRoot"
Write-Host '============================================'

# --- Prerequisites ---
Write-Step 'Checking prerequisites'
$gitOk = [bool](Get-Command git -ErrorAction SilentlyContinue)
if ($gitOk) {
    Write-Ok 'git found'
} else {
    Write-WarnMsg 'git not on PATH (optional for install, needed for auto-update)'
}

$envPathEarly = Join-Path $RepoRoot '.env'
$existingEnv = Import-ExistingEnvDefaults -Path $envPathEarly
if ($existingEnv.Count -gt 0) {
    Write-Ok "Loaded existing defaults from $envPathEarly"
}

$py = Resolve-InstallPython -Preferred $PythonPath
if (-not $py) {
    Write-ErrMsg 'Python 3.10+ not found. Install from https://www.python.org/downloads/ and re-run.'
    exit 1
}
Write-Ok "Python: $py"
$ver = & $py --version 2>&1
Write-Ok "$ver"

# --- Collect answers ---
Write-Step 'Collecting configuration'

$inferredMode = Infer-DeliveryModeFromEnv -Map $existingEnv
$defaultMode = if ($inferredMode) { $inferredMode } else { 'dry_run' }

if (-not $DeliveryMode) {
    if ($NonInteractive) {
        if ($env:DELIVERY_MODE) {
            $DeliveryMode = $env:DELIVERY_MODE
        } elseif ($inferredMode) {
            $DeliveryMode = $inferredMode
        } else {
            $DeliveryMode = 'dry_run'
        }
    } else {
        Write-Host 'Discord delivery options:'
        Write-Host '  1) dry_run     - run pipelines, never post (safest first install)'
        Write-Host '  2) no_discord  - same as dry_run opt-out'
        Write-Host '  3) bot         - DISCORD_TOKEN + DISCORD_CHANNEL_ID'
        Write-Host '  4) webhook     - DISCORD_WEBHOOK_URL'
        $choice = Read-Default 'Choose delivery mode (dry_run/bot/webhook/no_discord)' $defaultMode
        $DeliveryMode = $choice.ToLower().Replace('-', '_')
    }
}

if ($DeliveryMode -eq 'bot') {
    if (-not $DiscordToken) {
        $seed = if ($env:DISCORD_TOKEN) { $env:DISCORD_TOKEN } elseif ($existingEnv['DISCORD_TOKEN']) { $existingEnv['DISCORD_TOKEN'] } else { '' }
        if ($NonInteractive) { $DiscordToken = $seed } else { $DiscordToken = Read-Default 'DISCORD_TOKEN (bot token)' $seed }
    }
    if (-not $DiscordChannelId) {
        $seed = if ($env:DISCORD_CHANNEL_ID) { $env:DISCORD_CHANNEL_ID } elseif ($existingEnv['DISCORD_CHANNEL_ID']) { $existingEnv['DISCORD_CHANNEL_ID'] } else { '1510184298442002502' }
        if ($NonInteractive) { $DiscordChannelId = $seed } else { $DiscordChannelId = Read-Default 'DISCORD_CHANNEL_ID' $seed }
    }
} elseif ($DeliveryMode -eq 'webhook') {
    if (-not $DiscordWebhookUrl) {
        $seed = if ($env:DISCORD_WEBHOOK_URL) { $env:DISCORD_WEBHOOK_URL } elseif ($existingEnv['DISCORD_WEBHOOK_URL']) { $existingEnv['DISCORD_WEBHOOK_URL'] } else { '' }
        if ($NonInteractive) { $DiscordWebhookUrl = $seed } else { $DiscordWebhookUrl = Read-Default 'DISCORD_WEBHOOK_URL' $seed }
    }
    if (-not $DiscordChannelId) {
        $seed = if ($env:DISCORD_CHANNEL_ID) { $env:DISCORD_CHANNEL_ID } elseif ($existingEnv['DISCORD_CHANNEL_ID']) { $existingEnv['DISCORD_CHANNEL_ID'] } else { '1510184298442002502' }
        $DiscordChannelId = $seed
    }
} else {
    if (-not $DiscordChannelId) {
        $seed = if ($env:DISCORD_CHANNEL_ID) { $env:DISCORD_CHANNEL_ID } elseif ($existingEnv['DISCORD_CHANNEL_ID']) { $existingEnv['DISCORD_CHANNEL_ID'] } else { '1510184298442002502' }
        $DiscordChannelId = $seed
    }
}

if (-not $UntilPhase) {
    $seedPhase = if ($env:TRADING_AGENT_UNTIL_PHASE) { $env:TRADING_AGENT_UNTIL_PHASE } elseif ($existingEnv['TRADING_AGENT_UNTIL_PHASE']) { $existingEnv['TRADING_AGENT_UNTIL_PHASE'] } else { 'preopen' }
    if ($NonInteractive) {
        $UntilPhase = $seedPhase
    } else {
        Write-Host 'Phase scope: preopen = prep phases 1-4 (recommended without brokerage).'
        Write-Host '             full    = all 7 phases when you are ready.'
        $UntilPhase = Read-Default 'Until-phase (preopen/full/...)' $seedPhase
    }
}

if ($PortfolioValue -le 0) {
    $seedPv = if ($existingEnv['TRADING_AGENT_PORTFOLIO_VALUE']) { $existingEnv['TRADING_AGENT_PORTFOLIO_VALUE'] } else { '100000' }
    if ($NonInteractive) {
        try { $PortfolioValue = [double]$seedPv } catch { $PortfolioValue = 100000 }
    } else {
        $rawPv = Read-Default 'Portfolio value USD for CIO sizing' $seedPv
        $PortfolioValue = [double]$rawPv
    }
}

$doAuto = $false
if ($SkipAutomation) {
    $doAuto = $false
} elseif ($EnableAutomation) {
    $doAuto = $true
} elseif ($NonInteractive) {
    $doAuto = $false
} else {
    $doAuto = Read-YesNo 'Register weekday automation (wake ~01:50, desk 01:55 AM Pacific)?' $true
}

$doFirst = -not $SkipFirstRun
if (-not $NonInteractive -and -not $SkipFirstRun) {
    $doFirst = Read-YesNo 'Run a safe first session now (fixture + dry-run, prep phases)?' $true
}

# --- pip install ---
if (-not $SkipPip) {
    Write-Step 'Installing package (pip install -e .[dev])'
    & $py -m pip install -e '.[dev]' -q
    if ($LASTEXITCODE -ne 0) {
        Write-ErrMsg "pip install failed (exit $LASTEXITCODE)"
        exit $LASTEXITCODE
    }
    Write-Ok 'trading_agent installed'
} else {
    Write-WarnMsg 'Skipping pip install (-SkipPip)'
}

# --- write .env via pure helper ---
Write-Step 'Writing .env'
$envPath = Join-Path $RepoRoot '.env'
$examplePath = Join-Path $RepoRoot '.env.example'
# Use --flag=value so empty strings do not steal the next argument.
$writeArgs = @(
    '-m', 'trading_agent.install_wizard', 'write-env',
    "--output=$envPath",
    "--delivery-mode=$DeliveryMode",
    "--discord-token=$DiscordToken",
    "--discord-webhook-url=$DiscordWebhookUrl",
    "--discord-channel-id=$DiscordChannelId",
    "--until-phase=$UntilPhase",
    "--timezone=$Timezone",
    "--python-path=$py",
    "--portfolio-value=$PortfolioValue",
    '--strict'
)
if (Test-Path $examplePath) {
    $writeArgs += "--example=$examplePath"
}
& $py @writeArgs
if ($LASTEXITCODE -ne 0) {
    Write-ErrMsg 'Failed to write .env (validation or write error)'
    exit $LASTEXITCODE
}
Write-Ok "Env written: $envPath"

# Load process env from file for subsequent steps
Get-Content $envPath | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
        [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), 'Process')
    }
}

# --- optional automation ---
if ($doAuto) {
    Write-Step 'Registering automation (wake timers + scheduled tasks)'
    try {
        & (Join-Path $PSScriptRoot 'enable_pc_wake.ps1')
        & (Join-Path $PSScriptRoot 'register_desk_task.ps1')
        Write-Ok 'Automation registered'
    } catch {
        Write-WarnMsg "Automation registration failed: $_"
        Write-WarnMsg 'You can re-run scripts\setup_desk_automation.ps1 later.'
    }
} else {
    Write-WarnMsg 'Automation skipped (enable later with scripts\setup_desk_automation.ps1)'
}

# --- verify ---
Write-Step 'Verifying environment'
$verifyExit = 0
try {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'verify_environment.ps1')
    $verifyExit = $LASTEXITCODE
} catch {
    Write-WarnMsg "verify_environment threw: $_"
    $verifyExit = 1
}
if ($verifyExit -ne 0) {
    Write-WarnMsg "Verify reported issues (exit $verifyExit). Review messages above."
}

# --- first run ---
$firstExit = 0
if ($doFirst) {
    Write-Step 'Safe first run (fixture + dry-run + prep phases)'
    $dateArg = (Get-Date).ToString('yyyy-MM-dd')
    $logDir = Join-Path $env:USERPROFILE '.trading_agent\logs'
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $firstLog = Join-Path $logDir "first_run_$dateArg.log"
    & $py -m trading_agent session --fixture --dry-run --date $dateArg --from-phase intelligence --until-phase preopen --output $firstLog
    $firstExit = $LASTEXITCODE
    if ($firstExit -eq 0) {
        Write-Ok "First run completed (log: $firstLog)"
    } else {
        Write-ErrMsg "First run failed (exit $firstExit). See $firstLog"
    }
}

Write-Host ''
Write-Host '============================================'
if ($verifyExit -eq 0 -and $firstExit -eq 0) {
    Write-Host ' INSTALL COMPLETE - READY' -ForegroundColor Green
} elseif ($verifyExit -eq 0) {
    Write-Host ' INSTALL COMPLETE - env READY (first run had issues)' -ForegroundColor Yellow
} else {
    Write-Host ' INSTALL FINISHED WITH WARNINGS' -ForegroundColor Yellow
}
Write-Host '============================================'
Write-Host 'Next:'
Write-Host '  python -m trading_agent session --fixture --dry-run --until-phase preopen'
Write-Host '  scripts\setup_desk_automation.ps1   # if you skipped automation'
Write-Host '  Edit .env anytime, or re-run this installer.'
Write-Host ''

if ($verifyExit -ne 0) { exit $verifyExit }
if ($firstExit -ne 0) { exit $firstExit }
exit 0
