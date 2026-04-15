from pathlib import Path

from trading_tools.providers.bam import BamMacroClient


FIXTURE = Path(__file__).parent / "fixtures" / "bam" / "homepage.html"


def _html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_parse_snapshot_extracts_all_fields():
    snapshot = BamMacroClient.parse_snapshot(_html())

    assert snapshot["policy_rate_pct"] == 2.25
    assert snapshot["policy_rate_as_of"].startswith("2026-")

    assert snapshot["cpi_yoy_pct"] == -0.6
    assert snapshot["cpi_as_of"] == "2026-01-31"

    assert snapshot["usd_mad_spot"] == 9.236
    assert snapshot["eur_mad_spot"] == 10.887
    assert snapshot["fx_as_of"] == "2026-04-15"

    assert snapshot["warnings"] == []


def test_parse_snapshot_warns_when_all_missing():
    snapshot = BamMacroClient.parse_snapshot("<html><body>nothing here</body></html>")

    assert snapshot["policy_rate_pct"] is None
    assert snapshot["cpi_yoy_pct"] is None
    assert snapshot["usd_mad_spot"] is None
    assert snapshot["eur_mad_spot"] is None
    assert "bam_policy_rate_unparsed" in snapshot["warnings"]
    assert "bam_cpi_unparsed" in snapshot["warnings"]
    assert "bam_fx_unparsed" in snapshot["warnings"]


def test_parse_snapshot_partial_missing_fx_still_returns_rate_and_cpi():
    html = _html()
    # Strip the FX block so it fails to parse.
    stripped = html.replace('class="mod">', 'class="mod-off">', 1)
    snapshot = BamMacroClient.parse_snapshot(stripped)

    assert snapshot["policy_rate_pct"] == 2.25
    assert snapshot["cpi_yoy_pct"] == -0.6
    assert snapshot["usd_mad_spot"] is None
    assert snapshot["eur_mad_spot"] is None
    assert "bam_fx_unparsed" in snapshot["warnings"]
