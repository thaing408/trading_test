"""Product identity for this repository clone.

``trading_test`` = multi-method lab (no CIO decision desk).
``trading_agent`` (sibling repo) = live CIO desk that consumes scan lists.

This file is the permanent fork marker so env is optional.
"""

from __future__ import annotations

import os

# Permanent product id for this repo (do not copy back to trading_agent main as default)
PRODUCT_ID = "trading_test"
PRODUCT_NAME = "Trading Test (methods lab)"
# methods | desk
DEFAULT_PRODUCT_MODE = "methods"
# CIO approval/review off by default in this repo
DEFAULT_INCLUDE_CIO = False
# Remote for this fork (set by separation; informational)
DEFAULT_GIT_REMOTE = "https://github.com/thaing408/trading_test.git"


def product_mode() -> str:
    """Return ``methods`` or ``desk`` (env overrides product default)."""
    raw = (os.getenv("TRADING_AGENT_PRODUCT_MODE") or os.getenv("TRADING_TEST_MODE") or "").strip().lower()
    if raw in ("methods", "method", "lab", "test", "multi", "multi_method"):
        return "methods"
    if raw in ("desk", "cio", "live", "agent"):
        return "desk"
    return DEFAULT_PRODUCT_MODE


def include_cio_default() -> bool:
    if os.getenv("TRADING_AGENT_INCLUDE_CIO", "").strip():
        return os.getenv("TRADING_AGENT_INCLUDE_CIO", "").lower() in ("1", "true", "yes")
    if product_mode() == "methods":
        return DEFAULT_INCLUDE_CIO
    return True


def is_methods_lab() -> bool:
    return product_mode() == "methods"
