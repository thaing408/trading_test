#!/usr/bin/env python3
"""Weekday trading desk launcher for Task Scheduler (no PowerShell).

Why Python instead of start_desk_session.ps1 under the task:
  Microsoft Defender flags `powershell.exe -WindowStyle Hidden` spawning
  children as Trojan:Win32/PowhidSubExec.B. Running via pythonw.exe avoids
  that heuristic while still writing logs under ~/.trading_agent/logs/.

Manual / debug: still fine to run start_desk_session.ps1 in a visible window.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = Path.home() / ".trading_agent" / "logs"
LOCK_FILE = LOG_DIR / "desk_session.lock"


def _log(path: Path, msg: str) -> None:
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass
    # Also print if console attached (python.exe); pythonw has no console
    try:
        print(line, flush=True)
    except Exception:
        pass


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name:
            os.environ.setdefault(name, value)


def _resolve_python() -> str:
    candidates = []
    env_py = os.environ.get("TRADING_AGENT_PYTHON", "").strip()
    if env_py:
        candidates.append(env_py)
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    candidates.extend(
        [
            str(local / "Python" / "bin" / "python.exe"),
            str(local / "Python" / "pythoncore-3.14-64" / "python.exe"),
            str(local / "Programs" / "Python" / "Python314" / "python.exe"),
            str(local / "Programs" / "Python" / "Python313" / "python.exe"),
            sys.executable,
        ]
    )
    for c in candidates:
        if c and Path(c).is_file() and "WindowsApps" not in c:
            return c
    return sys.executable


def main() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now()
    if today.weekday() >= 5:
        _log(LOG_DIR / f"desk_startup_{today:%Y-%m-%d}.log", "Weekend - desk session not started.")
        return 0

    date_arg = today.strftime("%Y-%m-%d")
    startup_log = LOG_DIR / f"desk_startup_{date_arg}.log"
    session_log = LOG_DIR / f"desk_{date_arg}.log"
    stdout_log = LOG_DIR / f"desk_session_stdout_{date_arg}.log"
    stderr_log = LOG_DIR / f"desk_session_stderr_{date_arg}.log"

    # Stale lock guard
    if LOCK_FILE.is_file():
        age_h = (time.time() - LOCK_FILE.stat().st_mtime) / 3600.0
        if age_h < 14:
            _log(startup_log, f"Desk lock present ({age_h * 60:.0f}m old) - exiting.")
            return 0
        try:
            LOCK_FILE.unlink()
        except OSError:
            pass

    try:
        LOCK_FILE.write_text(
            f"pid=pending started={today.isoformat()} launcher=start_desk_session.py\n",
            encoding="utf-8",
        )
    except OSError:
        pass

    _log(startup_log, "=== Trading desk startup (python launcher) ===")
    _log(startup_log, f"Repo: {REPO_ROOT}")
    os.chdir(REPO_ROOT)
    _load_dotenv(REPO_ROOT / ".env")

    # UTF-8 for Discord-facing text
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    python = _resolve_python()
    _log(startup_log, f"Python: {python}")

    # Non-fatal git pull
    try:
        r = subprocess.run(
            ["git", "pull", "--ff-only", "origin", "main"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        _log(startup_log, f"git pull exit={r.returncode}")
        if r.stdout.strip():
            _log(startup_log, r.stdout.strip()[:500])
        if r.stderr.strip():
            _log(startup_log, r.stderr.strip()[:500])
    except Exception as exc:
        _log(startup_log, f"WARN: git pull skipped: {exc}")

    # Non-fatal pip
    for attempt in range(1, 4):
        try:
            r = subprocess.run(
                [python, "-m", "pip", "install", "-e", ".[dev]", "-q"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if r.returncode == 0:
                _log(startup_log, "pip install OK")
                break
            _log(startup_log, f"pip install attempt {attempt} exit={r.returncode}")
        except Exception as exc:
            _log(startup_log, f"pip install attempt {attempt} failed: {exc}")
        time.sleep(5)

    # Phase scope
    until = (os.environ.get("TRADING_AGENT_UNTIL_PHASE") or "evening_scan").strip()
    if until in ("full", "all", "day", "fullday", "full_day"):
        until = "evening_scan"
    if until in ("prep", "pre-market", "premarket"):
        until = "preopen"
    from_phase = (os.environ.get("TRADING_AGENT_FROM_PHASE") or "intelligence").strip()
    os.environ.setdefault("TRADING_AGENT_FROM_PHASE", from_phase)
    os.environ.setdefault("TRADING_AGENT_UNTIL_PHASE", until)
    os.environ.setdefault("TRADING_AGENT_DISCOVERY_REFRESH", "1")

    _log(startup_log, f"Starting desk session for {date_arg} ({from_phase} -> {until})")
    _log(startup_log, f"Session log: {session_log}")

    cmd = [
        python,
        "-m",
        "trading_agent",
        "session",
        "--date",
        date_arg,
        "--from-phase",
        from_phase,
        "--until-phase",
        until,
        "--output",
        str(session_log),
    ]

    # CREATE_NO_WINDOW on Windows so console never flashes (python.exe child)
    creationflags = 0
    if sys.platform == "win32":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

    try:
        with stdout_log.open("w", encoding="utf-8") as out_f, stderr_log.open(
            "w", encoding="utf-8"
        ) as err_f:
            proc = subprocess.Popen(
                cmd,
                cwd=str(REPO_ROOT),
                stdout=out_f,
                stderr=err_f,
                env=os.environ.copy(),
                creationflags=creationflags,
            )
        try:
            LOCK_FILE.write_text(
                f"pid={proc.pid} started={datetime.now().isoformat()} "
                f"from={from_phase} until={until} launcher=start_desk_session.py\n",
                encoding="utf-8",
            )
        except OSError:
            pass
        _log(startup_log, f"Session PID={proc.pid}")
        code = proc.wait()
        # Retry once on failure (same as PS launcher)
        if code != 0:
            _log(startup_log, f"WARN: desk session failed (exit {code}); retrying once after 30s")
            time.sleep(30)
            with stdout_log.open("w", encoding="utf-8") as out_f, stderr_log.open(
                "w", encoding="utf-8"
            ) as err_f:
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(REPO_ROOT),
                    stdout=out_f,
                    stderr=err_f,
                    env=os.environ.copy(),
                    creationflags=creationflags,
                )
            code = proc.wait()
        _log(startup_log, f"Desk session exited with code {code}")
        return int(code or 0)
    except Exception as exc:
        _log(startup_log, f"FATAL: {exc}")
        return 1
    finally:
        try:
            if LOCK_FILE.is_file():
                LOCK_FILE.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
