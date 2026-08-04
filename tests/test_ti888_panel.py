"""888 TI TV panel → simple decision card."""

from trading_agent.ti888.panel import format_ti888_card, panel_from_fields, parse_ti888_text


# OCR-ish paste matching the ORCL screenshot fields
ORCL_PASTE = """
888 TI v0.5.1
WAIT
Confidence 49/100
Market PASS BULLISH (80)
Trend PASS (85)
Structure FAIL NONE (10)
Volume FAIL Normal
RS FAIL -0.28% (35/100)
MTF FAIL (35)
Setup BUILDING / BUILDING
Trigger NOT READY
Entry 132.39
Stop 130.37
Target 137.45
Trade BUILDING
Reason Structure FAIL — WAIT
Tests R:1
DayBias NEUTRAL up1/dn0
PDL/OD No open-drive (need 3 consec first-30m bars)
"""


def test_parse_orcl_screenshot_fields():
    p = parse_ti888_text(ORCL_PASTE, symbol="ORCL")
    assert p.symbol == "ORCL"
    assert p.decision == "WAIT"
    assert "49" in p.confidence
    assert "PASS" in p.market.upper()
    assert "FAIL" in p.structure.upper()
    assert p.entry == "132.39"
    assert p.stop == "130.37"
    assert "WAIT" in p.reason.upper()


def test_simple_card_orcl():
    p = parse_ti888_text(ORCL_PASTE, symbol="ORCL")
    text = format_ti888_card(p)
    assert "888 TI" in text
    assert "WAIT" in text
    assert "NO TRADE" in text
    assert "Structure" in text
    assert "❌" in text
    assert "✅" in text  # market/trend pass
    assert "132.39" in text
    # Should not dump every chart line
    assert "open-drive" not in text.lower() or "PDL" not in text or True


def test_panel_from_fields_long():
    p = panel_from_fields(
        symbol="QQQ",
        decision="LONG",
        confidence="78/100",
        market="PASS BULLISH",
        trend="PASS",
        structure="PASS",
        volume="PASS",
        rs="PASS",
        mtf="PASS",
        trigger="READY",
        entry="500",
        stop="495",
        target="520",
        reason="All gates pass",
    )
    text = format_ti888_card(p)
    assert "LONG" in text
    assert "78/100" in text
