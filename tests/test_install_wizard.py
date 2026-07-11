"""Unit tests for install wizard pure helpers (real shipped module)."""

from __future__ import annotations

from pathlib import Path

import pytest

from trading_agent.install_wizard import (
    DEFAULT_CHANNEL_ID,
    DEFAULT_UNTIL_PHASE,
    InstallAnswers,
    answers_from_mapping,
    checklist_ok,
    discord_ready_from_env,
    normalize_delivery_mode,
    normalize_phase,
    parse_env_file,
    render_env_file,
    required_env_checklist,
    validate_answers,
    write_env_file,
    _cli,
)


def test_install_shell_scripts_use_unix_lf_line_endings():
    """bash rejects CRLF ($'\\r': command not found). Keep install entrypoints LF-only."""
    repo = Path(__file__).resolve().parents[1]
    scripts = [
        repo / "scripts" / "install.sh",
        repo / "scripts" / "macos" / "install-trading-agent-launchd.sh",
    ]
    for path in scripts:
        assert path.is_file(), f"missing {path}"
        data = path.read_bytes()
        assert b"\r" not in data, f"{path.name} must use LF line endings (found CR)"
        assert data.startswith(b"#!/"), f"{path.name} missing shebang"


def test_normalize_delivery_mode_aliases():
    assert normalize_delivery_mode("dry-run") == "dry_run"
    assert normalize_delivery_mode("token") == "bot"
    assert normalize_delivery_mode("hook") == "webhook"
    assert normalize_delivery_mode("skip") == "no_discord"
    with pytest.raises(ValueError):
        normalize_delivery_mode("carrier_pigeon")


def test_normalize_phase_prep_and_full():
    assert normalize_phase("prep") == "preopen"
    assert normalize_phase("preopen") == "preopen"
    assert normalize_phase("full") == ""
    with pytest.raises(ValueError):
        normalize_phase("not_a_phase")


def test_validate_bot_requires_token_and_channel():
    answers = InstallAnswers(delivery_mode="bot", discord_token="", discord_channel_id="")
    errors = validate_answers(answers)
    assert any("DISCORD_TOKEN" in e for e in errors)
    assert any("DISCORD_CHANNEL_ID" in e for e in errors)

    answers = InstallAnswers(
        delivery_mode="bot",
        discord_token="abc.def.ghi",
        discord_channel_id=DEFAULT_CHANNEL_ID,
    )
    assert validate_answers(answers) == []


def test_validate_webhook_requires_https():
    answers = InstallAnswers(delivery_mode="webhook", discord_webhook_url="http://bad.example")
    errors = validate_answers(answers)
    assert any("https://" in e for e in errors)

    answers = InstallAnswers(
        delivery_mode="webhook",
        discord_webhook_url="https://discord.com/api/webhooks/1/2",
    )
    assert validate_answers(answers) == []


def test_dry_run_does_not_require_discord_secrets():
    answers = InstallAnswers(delivery_mode="dry_run")
    assert validate_answers(answers) == []
    env = answers.as_env_map()
    ok, reason = discord_ready_from_env(env)
    assert ok
    assert "opted out" in reason.lower() or "dry" in reason.lower()
    assert env.get("TRADING_AGENT_NO_DISCORD") == "1"


def test_render_env_file_writes_collected_values(tmp_path: Path):
    example = "DISCORD_CHANNEL_ID=old\nTRADING_AGENT_UNTIL_PHASE=preopen\nTRADING_AGENT_PYTHON=\n"
    answers = InstallAnswers(
        delivery_mode="bot",
        discord_token="secret-token",
        discord_channel_id="999888777",
        until_phase="preopen",
        python_path=r"C:\Python\python.exe",
    )
    content = render_env_file(answers, example_text=example)
    parsed = parse_env_file(content)
    assert parsed["DISCORD_TOKEN"] == "secret-token"
    assert parsed["DISCORD_CHANNEL_ID"] == "999888777"
    assert parsed["TRADING_AGENT_UNTIL_PHASE"] == DEFAULT_UNTIL_PHASE
    assert parsed["TRADING_AGENT_PYTHON"] == r"C:\Python\python.exe"
    assert parsed.get("TRADING_AGENT_NO_DISCORD") == "0"

    out = write_env_file(tmp_path / ".env", content)
    assert out.is_file()
    assert "secret-token" in out.read_text(encoding="utf-8")


def test_discord_ready_from_env_bot_and_missing():
    ok, _ = discord_ready_from_env(
        {"DISCORD_TOKEN": "t", "DISCORD_CHANNEL_ID": "1", "TRADING_AGENT_NO_DISCORD": "0"}
    )
    assert ok
    ok, reason = discord_ready_from_env({"DISCORD_CHANNEL_ID": "1"})
    assert not ok
    assert "TOKEN" in reason or "WEBHOOK" in reason or "missing" in reason.lower()


def test_answers_from_mapping_and_cli_write(tmp_path: Path):
    answers = answers_from_mapping(
        {
            "delivery_mode": "no_discord",
            "TRADING_AGENT_UNTIL_PHASE": "prep",
            "python_path": "/usr/bin/python3",
        }
    )
    assert normalize_delivery_mode(answers.delivery_mode) == "no_discord"
    # until_phase normalized when validating/rendering
    content = render_env_file(answers)
    parsed = parse_env_file(content)
    assert parsed["TRADING_AGENT_UNTIL_PHASE"] == "preopen"
    assert parsed["TRADING_AGENT_PYTHON"] == "/usr/bin/python3"

    out = tmp_path / "generated.env"
    code = _cli(
        [
            "write-env",
            "-o",
            str(out),
            "--delivery-mode",
            "dry_run",
            "--until-phase",
            "preopen",
            "--python-path",
            "py",
            "--strict",
        ]
    )
    assert code == 0
    assert out.is_file()
    assert "TRADING_AGENT_DRY_RUN=1" in out.read_text(encoding="utf-8")


def test_cli_validate_env_ready(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text("TRADING_AGENT_DRY_RUN=1\nTRADING_AGENT_NO_DISCORD=1\n", encoding="utf-8")
    assert _cli(["validate-env", "--env-file", str(env_path)]) == 0

    env_path.write_text("DISCORD_CHANNEL_ID=1\n", encoding="utf-8")
    assert _cli(["validate-env", "--env-file", str(env_path)]) == 1


def test_required_env_checklist_fails_without_discord_when_live_required():
    items = required_env_checklist(
        {"TRADING_AGENT_TIMEZONE": "America/Los_Angeles"},
        require_live_discord=True,
    )
    assert not checklist_ok(items)
    names = {i.name: i for i in items}
    assert names["discord_live"].ok is False


def test_required_env_checklist_passes_dry_run_opt_out():
    items = required_env_checklist(
        {
            "TRADING_AGENT_DRY_RUN": "1",
            "TRADING_AGENT_NO_DISCORD": "1",
            "TRADING_AGENT_TIMEZONE": "America/Los_Angeles",
            "DISCORD_CHANNEL_ID": DEFAULT_CHANNEL_ID,
        },
        require_live_discord=False,
    )
    assert checklist_ok(items)


def test_checklist_cli_exit_codes():
    # missing live discord -> fail
    code = _cli(["checklist", "--require-live-discord"])
    assert code == 1


def test_desk_production_env_checks_full_day():
    from trading_agent.install_wizard import desk_production_env_checks, checklist_ok

    assert checklist_ok(desk_production_env_checks({}))
    assert checklist_ok(desk_production_env_checks({"TRADING_AGENT_UNTIL_PHASE": "full"}))
    assert not checklist_ok(desk_production_env_checks({"TRADING_AGENT_UNTIL_PHASE": "preopen"}))
    assert not checklist_ok(desk_production_env_checks({"TRADING_AGENT_DRY_RUN": "1"}))
    assert not checklist_ok(desk_production_env_checks({"TRADING_AGENT_NO_DISCORD": "true"}))
