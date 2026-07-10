#!/usr/bin/env python3
"""Exec NUL-separated argv file — avoids bash 3.2 empty-array + set -u crash."""
from __future__ import annotations

import os
import sys


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: run-argv.py <nul-separated-argv-file>")
    raw = open(sys.argv[1], "rb").read().split(b"\0")
    args = [p.decode() for p in raw if p]
    if not args:
        raise SystemExit("empty argv")
    os.execvp(args[0], args)


if __name__ == "__main__":
    main()
