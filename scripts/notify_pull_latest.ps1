# Optional: after git push from work, post a short Discord cue for home Mac (no secrets/paths).
# Usage: powershell -File scripts/notify_pull_latest.ps1
# Requires DISCORD_TOKEN + DISCORD_CHANNEL_ID or DISCORD_WEBHOOK_URL in .env (work bot only).

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        $eq = $line.IndexOf("=")
        if ($eq -lt 1) { return }
        $name = $line.Substring(0, $eq).Trim()
        $value = $line.Substring($eq + 1).Trim().Trim('"').Trim("'")
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

$sha = (git log -1 --oneline 2>$null)
if (-not $sha) { $sha = "main" }

$msg = @"
**PULL_LATEST** ``trading_agent`` ``main``

Research host pushed methods/code.
Home Mac: run ``./scripts/macos/pull-and-ready.sh`` then use **local** TOS only.

``$sha``
"@

$env:PYTHONUTF8 = "1"
python -c @"
from trading_agent.discord.config import DiscordConfig
from trading_agent.discord.poster import post_message
cfg = DiscordConfig.from_env()
post_message('''$($msg.Replace("'","''"))''', cfg, username='Trading Agent')
print('posted PULL_LATEST cue')
"@
