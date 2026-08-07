"""Resolve researcher production host under DHCP (IP can change).

Order:
1. RESEARCHER_HOST env (explicit IP/hostname)
2. Cached file ~/.grok/researcher_host (or RESEARCHER_HOST_CACHE)
3. Stable hostnames (RESEARCHER_HOSTNAME, me-ai.local, me-ai)
4. Optional last-known LAN probe is out of scope — update cache on success
"""

from __future__ import annotations

import os
import socket
from pathlib import Path
from typing import Iterable, List, Optional, Tuple


def host_cache_path() -> Path:
    raw = os.getenv("RESEARCHER_HOST_CACHE", "").strip()
    if raw:
        return Path(raw)
    return Path.home() / ".grok" / "researcher_host"


def read_cached_host() -> str:
    p = host_cache_path()
    try:
        if p.is_file():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # allow "host=me-ai.local" or bare value
                if "=" in line:
                    k, _, v = line.partition("=")
                    if k.strip().lower() in ("host", "hostname", "ip", "researcher_host"):
                        return v.strip()
                    continue
                return line
    except OSError:
        pass
    return ""


def write_cached_host(host: str) -> None:
    host = (host or "").strip()
    if not host:
        return
    p = host_cache_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            "# Auto-updated when researcher sync succeeds. Safe under DHCP.\n"
            f"host={host}\n",
            encoding="utf-8",
        )
    except OSError:
        pass


def default_hostname_candidates() -> List[str]:
    raw = os.getenv("RESEARCHER_HOSTNAME", "").strip()
    names: List[str] = []
    if raw:
        names.append(raw)
    # Known production box hostname from deploy
    names.extend(
        [
            "me-ai.local",
            "me-ai",
            "researcher.local",
        ]
    )
    # de-dupe preserve order
    seen = set()
    out: List[str] = []
    for n in names:
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _tcp_ok(host: str, port: int = 22, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _resolve_a(host: str) -> Optional[str]:
    try:
        infos = socket.getaddrinfo(host, 22, type=socket.SOCK_STREAM)
        for info in infos:
            ip = info[4][0]
            if ip and ":" not in ip:  # prefer IPv4 for LAN scp
                return ip
        if infos:
            return infos[0][4][0]
    except OSError:
        return None
    return None


def candidate_hosts() -> List[str]:
    ordered: List[str] = []
    env = os.getenv("RESEARCHER_HOST", "").strip()
    if env:
        ordered.append(env)
    cached = read_cached_host()
    if cached:
        ordered.append(cached)
    ordered.extend(default_hostname_candidates())
    # last-ditch documented static (may go stale under DHCP)
    fallback = os.getenv("RESEARCHER_HOST_FALLBACK", "10.0.0.52").strip()
    if fallback:
        ordered.append(fallback)
    seen = set()
    out: List[str] = []
    for h in ordered:
        if h and h not in seen:
            seen.add(h)
            out.append(h)
    return out


def resolve_researcher_host(
    *,
    port: int = 22,
    timeout: float = 1.5,
    update_cache: bool = True,
) -> Tuple[str, str]:
    """Return (host_for_ssh, how_resolved).

    ``host_for_ssh`` is a hostname or IP that accepted TCP/22.
    """
    for host in candidate_hosts():
        if _tcp_ok(host, port=port, timeout=timeout):
            if update_cache:
                write_cached_host(host)
            return host, f"reachable:{host}"
        # try resolved IP if hostname
        ip = _resolve_a(host)
        if ip and ip != host and _tcp_ok(ip, port=port, timeout=timeout):
            if update_cache:
                write_cached_host(host)  # prefer stable name in cache
            return host, f"reachable_via_ip:{host}->{ip}"
    raise RuntimeError(
        "Cannot reach researcher host (SSH). Tried: "
        + ", ".join(candidate_hosts())
        + ". Set RESEARCHER_HOST or ~/.grok/researcher_host, or ensure me-ai.local (mDNS) works."
    )


def resolve_researcher_host_safe() -> Tuple[Optional[str], str]:
    try:
        h, how = resolve_researcher_host()
        return h, how
    except RuntimeError as exc:
        return None, str(exc)
