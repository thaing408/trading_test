# Enable OS wake timers so Task Scheduler can wake this PC from sleep/hibernate.
# Safe to re-run; does not require Administrator on most Windows builds.

$ErrorActionPreference = "Continue"

function Set-WakeTimersEnabled {
    # RTCWAKE: 0=Disable, 1=Enable, 2=Important only (user tasks often blocked)
    $schemes = @("SCHEME_CURRENT", "SCHEME_BALANCED", "SCHEME_MIN", "SCHEME_MAX")
    foreach ($scheme in $schemes) {
        powercfg /SETACVALUEINDEX $scheme SUB_SLEEP RTCWAKE 1 2>$null | Out-Null
        powercfg /SETDCVALUEINDEX $scheme SUB_SLEEP RTCWAKE 1 2>$null | Out-Null
    }
    powercfg /SETACTIVE SCHEME_CURRENT 2>$null | Out-Null
}

function Get-WakeTimerState {
    $raw = powercfg /query SCHEME_CURRENT SUB_SLEEP bd3b718a-0680-4d9d-8ab2-e1d2b4ac806d 2>$null
    $ac = $null
    $dc = $null
    foreach ($line in $raw) {
        if ($line -match "Current AC Power Setting Index:\s*0x([0-9a-fA-F]+)") {
            $ac = [Convert]::ToInt32($matches[1], 16)
        }
        if ($line -match "Current DC Power Setting Index:\s*0x([0-9a-fA-F]+)") {
            $dc = [Convert]::ToInt32($matches[1], 16)
        }
    }
    return [pscustomobject]@{ Ac = $ac; Dc = $dc }
}

Write-Host "=== Enable PC wake for trading desk ==="
Set-WakeTimersEnabled
$state = Get-WakeTimerState
$names = @{ 0 = "Disable"; 1 = "Enable"; 2 = "Important only" }
Write-Host ("Allow wake timers AC: {0} ({1})" -f $state.Ac, $(if ($null -ne $state.Ac) { $names[$state.Ac] } else { "?" }))
Write-Host ("Allow wake timers DC: {0} ({1})" -f $state.Dc, $(if ($null -ne $state.Dc) { $names[$state.Dc] } else { "?" }))

if ($state.Ac -ne 1) {
    Write-Host "WARN: AC wake timers are not fully enabled. Scheduled tasks may not wake the PC."
    exit 1
}

Write-Host "OK - wake timers enabled (task WakeToRun can resume from sleep)."
exit 0
