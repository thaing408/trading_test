"""Pure install/config helpers for new-user onboarding.

Platform install scripts (install.ps1 / install.sh) call these functions so
validation and .env rendering stay testable without driving full OS installers.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

# Prep-only default until brokerage is connected.
DEFAULT_UNTIL_PHASE = "preopen"
DEFAULT_CHANNEL_ID = "1510184298442002502"
DEFAULT_TIMEZONE = "America/Los_Angeles"

VALID_PHASES = frozenset(
    {
        "intelligence",
        "research",
        "cio_approval",
        "preopen",
        "intraday",
        "performance",
        "cio_review",
    }
)

DELIVERY_MODES = frozenset({"bot", "webhook", "dry_run", "no_discord"})


@dataclass
class InstallAnswers:
    """Collected answers from the install wizard."""

    delivery_mode: str = "dry_run"
    discord_token: str = ""
    discord_webhook_url: str = ""
    discord_channel_id: str = DEFAULT_CHANNEL_ID
    until_phase: str = DEFAULT_UNTIL_PHASE
    timezone: str = DEFAULT_TIMEZONE
    python_path: str = ""
    enable_automation: bool = False
    run_first_session: bool = True
    portfolio_value: float = 100_000.0
    extra: dict[str, str] = field(default_factory=dict)

    def as_env_map(self) -> dict[str, str]:
        """Flatten answers into .env key/value pairs (non-empty only where relevant)."""
        env: dict[str, str] = {
            "DISCORD_CHANNEL_ID": (self.discord_channel_id or DEFAULT_CHANNEL_ID).strip(),
            "TRADING_AGENT_UNTIL_PHASE": (self.until_phase or DEFAULT_UNTIL_PHASE).strip(),
            "TRADING_AGENT_TIMEZONE": (self.timezone or DEFAULT_TIMEZONE).strip(),
            "TRADING_AGENT_PORTFOLIO_VALUE": str(self.portfolio_value),
        }
        if self.python_path.strip():
            env["TRADING_AGENT_PYTHON"] = self.python_path.strip()

        mode = normalize_delivery_mode(self.delivery_mode)
        if mode in ("dry_run", "no_discord"):
            env["TRADING_AGENT_DRY_RUN"] = "1" if mode == "dry_run" else "0"
            env["TRADING_AGENT_NO_DISCORD"] = "1"
        else:
            env["TRADING_AGENT_DRY_RUN"] = "0"
            env["TRADING_AGENT_NO_DISCORD"] = "0"
            if mode == "webhook" and self.discord_webhook_url.strip():
                env["DISCORD_WEBHOOK_URL"] = self.discord_webhook_url.strip()
            if mode == "bot" and self.discord_token.strip():
                env["DISCORD_TOKEN"] = self.discord_token.strip()
            # Allow both token and webhook to be stored if user provided extras
            if self.discord_webhook_url.strip() and mode != "webhook":
                env["DISCORD_WEBHOOK_URL"] = self.discord_webhook_url.strip()
            if self.discord_token.strip() and mode != "bot":
                env["DISCORD_TOKEN"] = self.discord_token.strip()

        for key, value in self.extra.items():
            if key and value is not None and str(value).strip() != "":
                env[key.strip()] = str(value).strip()
        return env


def normalize_delivery_mode(raw: str | None) -> str:
    text = (raw or "dry_run").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "dryrun": "dry_run",
        "none": "no_discord",
        "skip": "no_discord",
        "off": "no_discord",
        "bot_token": "bot",
        "token": "bot",
        "webhook_url": "webhook",
        "hook": "webhook",
    }
    text = aliases.get(text, text)
    if text not in DELIVERY_MODES:
        raise ValueError(
            f"Invalid delivery mode {raw!r}. Choose one of: {', '.join(sorted(DELIVERY_MODES))}"
        )
    return text


def normalize_phase(raw: str | None) -> str:
    text = (raw or DEFAULT_UNTIL_PHASE).strip().lower()
    if text in ("prep", "prep_only", "preparation", "phases_1_4", "1-4"):
        text = "preopen"
    if text in ("full", "all", "all_phases", "7"):
        # Unset conceptually — caller may omit; use empty to mean full day
        return ""
    if text and text not in VALID_PHASES:
        raise ValueError(
            f"Invalid until-phase {raw!r}. Choose one of: {', '.join(sorted(VALID_PHASES))} or 'full'"
        )
    return text


def validate_answers(answers: InstallAnswers) -> list[str]:
    """Return human-readable validation errors (empty list = OK)."""
    errors: list[str] = []
    try:
        mode = normalize_delivery_mode(answers.delivery_mode)
    except ValueError as exc:
        errors.append(str(exc))
        return errors

    try:
        phase = normalize_phase(answers.until_phase)
        answers.until_phase = phase if phase else answers.until_phase
    except ValueError as exc:
        errors.append(str(exc))

    if mode == "bot":
        if not answers.discord_token.strip():
            errors.append("DISCORD_TOKEN is required for bot delivery mode.")
        if not answers.discord_channel_id.strip():
            errors.append("DISCORD_CHANNEL_ID is required for bot delivery mode.")
    elif mode == "webhook":
        url = answers.discord_webhook_url.strip()
        if not url:
            errors.append("DISCORD_WEBHOOK_URL is required for webhook delivery mode.")
        elif not url.startswith("https://"):
            errors.append("DISCORD_WEBHOOK_URL must start with https://")
    # dry_run / no_discord: no Discord secrets required

    if answers.portfolio_value <= 0:
        errors.append("Portfolio value must be positive.")

    return errors


def discord_ready_from_env(env: Mapping[str, str]) -> tuple[bool, str]:
    """Whether env is sufficient for Discord posts (or explicit opt-out)."""
    no_discord = _truthy(env.get("TRADING_AGENT_NO_DISCORD", ""))
    dry = _truthy(env.get("TRADING_AGENT_DRY_RUN", ""))
    if no_discord or dry:
        return True, "Discord opted out (dry-run / no-discord)"

    webhook = (env.get("DISCORD_WEBHOOK_URL") or "").strip()
    token = (env.get("DISCORD_TOKEN") or "").strip()
    channel = (env.get("DISCORD_CHANNEL_ID") or "").strip()
    if webhook.startswith("https://"):
        return True, "webhook configured"
    if token and channel:
        return True, "bot token + channel configured"
    if token and not channel:
        return False, "DISCORD_CHANNEL_ID missing"
    if channel and not token and not webhook:
        return False, "DISCORD_TOKEN or DISCORD_WEBHOOK_URL missing"
    return False, "no Discord credentials and dry-run not set"


def parse_env_file(text: str) -> dict[str, str]:
    """Parse KEY=VALUE lines; ignore comments and blanks."""
    result: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and (
            (value.startswith('"') and value.endswith('"'))
            or (value.startswith("'") and value.endswith("'"))
        ):
            value = value[1:-1]
        if key:
            result[key] = value
    return result


def render_env_file(
    answers: InstallAnswers,
    *,
    example_text: str | None = None,
    header_comment: str | None = None,
) -> str:
    """Render a complete .env body from answers, optionally seeded from .env.example."""
    values = answers.as_env_map()
    # Normalize phase after full-day selection
    phase = normalize_phase(answers.until_phase)
    if phase == "":
        values.pop("TRADING_AGENT_UNTIL_PHASE", None)
    else:
        values["TRADING_AGENT_UNTIL_PHASE"] = phase

    base: dict[str, str] = {}
    if example_text:
        base = parse_env_file(example_text)
    base.update(values)

    # Drop empty optional secrets that user did not set
    for optional in ("DISCORD_TOKEN", "DISCORD_WEBHOOK_URL", "TRADING_AGENT_PYTHON"):
        if optional in base and not str(base[optional]).strip():
            del base[optional]

    lines: list[str] = []
    lines.append(header_comment or "# Generated by trading_agent install wizard")
    lines.append("# Re-run scripts/install.ps1 or scripts/install.sh to update.")
    lines.append("")

    # Stable key order for readability
    preferred = [
        "DISCORD_WEBHOOK_URL",
        "DISCORD_TOKEN",
        "DISCORD_CHANNEL_ID",
        "TRADING_AGENT_PYTHON",
        "TRADING_AGENT_UNTIL_PHASE",
        "TRADING_AGENT_TIMEZONE",
        "TRADING_AGENT_PORTFOLIO_VALUE",
        "TRADING_AGENT_DRY_RUN",
        "TRADING_AGENT_NO_DISCORD",
        "TRADING_AGENT_ENV_FILE",
        "TRADING_AGENT_POSITIONS_FILE",
    ]
    seen: set[str] = set()
    for key in preferred:
        if key in base:
            lines.append(f"{key}={base[key]}")
            seen.add(key)
    for key in sorted(base.keys()):
        if key not in seen:
            lines.append(f"{key}={base[key]}")
    lines.append("")
    return "\n".join(lines)


def write_env_file(path: Path | str, content: str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def answers_from_mapping(data: Mapping[str, str | bool | float | int | None]) -> InstallAnswers:
    """Build InstallAnswers from a flat mapping (CLI/env vars)."""

    def s(key: str, default: str = "") -> str:
        val = data.get(key, default)
        if val is None:
            return default
        return str(val).strip()

    def b(key: str, default: bool = False) -> bool:
        val = data.get(key, default)
        if isinstance(val, bool):
            return val
        return _truthy(str(val))

    mode = s("delivery_mode") or s("DELIVERY_MODE") or "dry_run"
    raw_pv = data.get("portfolio_value", data.get("TRADING_AGENT_PORTFOLIO_VALUE", 100_000.0))
    try:
        portfolio_value = float(raw_pv) if raw_pv is not None else 100_000.0
    except (TypeError, ValueError):
        portfolio_value = 100_000.0

    return InstallAnswers(
        delivery_mode=mode,
        discord_token=s("discord_token") or s("DISCORD_TOKEN"),
        discord_webhook_url=s("discord_webhook_url") or s("DISCORD_WEBHOOK_URL"),
        discord_channel_id=s("discord_channel_id") or s("DISCORD_CHANNEL_ID") or DEFAULT_CHANNEL_ID,
        until_phase=s("until_phase") or s("TRADING_AGENT_UNTIL_PHASE") or DEFAULT_UNTIL_PHASE,
        timezone=s("timezone") or s("TRADING_AGENT_TIMEZONE") or DEFAULT_TIMEZONE,
        python_path=s("python_path") or s("TRADING_AGENT_PYTHON"),
        enable_automation=b("enable_automation") or b("ENABLE_AUTOMATION"),
        run_first_session=b("run_first_session", True)
        if "run_first_session" in data or "RUN_FIRST_SESSION" in data
        else True,
        portfolio_value=portfolio_value,
    )


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Trading agent install wizard helpers")
    sub = parser.add_subparsers(dest="cmd", required=True)

    write_p = sub.add_parser("write-env", help="Write .env from answers")
    write_p.add_argument("--output", "-o", required=True, help="Path to write (.env)")
    write_p.add_argument("--example", help="Path to .env.example to merge")
    write_p.add_argument("--delivery-mode", default="dry_run")
    write_p.add_argument("--discord-token", default="")
    write_p.add_argument("--discord-webhook-url", default="")
    write_p.add_argument("--discord-channel-id", default=DEFAULT_CHANNEL_ID)
    write_p.add_argument("--until-phase", default=DEFAULT_UNTIL_PHASE)
    write_p.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    write_p.add_argument("--python-path", default="")
    write_p.add_argument("--portfolio-value", type=float, default=100_000.0)
    write_p.add_argument("--strict", action="store_true", help="Fail on validation errors")

    val_p = sub.add_parser("validate-env", help="Validate an existing .env file")
    val_p.add_argument("--env-file", required=True)

    args = parser.parse_args(argv)

    if args.cmd == "write-env":
        answers = InstallAnswers(
            delivery_mode=args.delivery_mode,
            discord_token=args.discord_token,
            discord_webhook_url=args.discord_webhook_url,
            discord_channel_id=args.discord_channel_id,
            until_phase=args.until_phase,
            timezone=args.timezone,
            python_path=args.python_path,
            portfolio_value=args.portfolio_value,
        )
        errors = validate_answers(answers)
        if errors and args.strict:
            for err in errors:
                print(f"ERROR: {err}", file=sys.stderr)
            return 1
        for err in errors:
            print(f"WARN: {err}", file=sys.stderr)
        example = None
        if args.example and Path(args.example).is_file():
            example = Path(args.example).read_text(encoding="utf-8")
        content = render_env_file(answers, example_text=example)
        path = write_env_file(args.output, content)
        print(f"Wrote {path}")
        ok, reason = discord_ready_from_env(parse_env_file(content))
        print(f"Discord readiness: {'OK' if ok else 'FAIL'} — {reason}")
        return 0 if (ok or not args.strict) else 1

    if args.cmd == "validate-env":
        text = Path(args.env_file).read_text(encoding="utf-8")
        env = parse_env_file(text)
        ok, reason = discord_ready_from_env(env)
        print(f"{'READY' if ok else 'NOT READY'} — {reason}")
        return 0 if ok else 1

    return 2


def main() -> None:
    raise SystemExit(_cli())


if __name__ == "__main__":
    main()
