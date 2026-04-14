from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("trading_tools.corporate_actions")

from ingestion import cli

pytestmark = pytest.mark.v2_only


def _load_fixture(name: str) -> dict:
    path = Path(__file__).parent / "fixtures" / "ingestion" / name
    return json.loads(path.read_text(encoding="utf-8"))


def test_cli_scrape_bourse_end_to_end(monkeypatch, tmp_path, capsys):
    page1 = _load_fixture("bc_dividendes_page1.json")
    page2 = _load_fixture("bc_dividendes_page2.json")
    next_url = page1["links"]["next"]["href"]

    def fake_get_json(self, url: str, *, params=None):
        if params and int(params.get("page[offset]", 0)) == 0:
            return page1
        if url == next_url:
            return page2
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr("ingestion.http.client.PoliteClient.get_json", fake_get_json)

    db_path = tmp_path / "ca.sqlite"

    rc1 = cli.main([
        "--db",
        str(db_path),
        "scrape-bourse",
        "--since",
        "2024-01-01",
        "--until",
        "2024-12-31",
    ])
    out1 = json.loads(capsys.readouterr().out)
    assert rc1 == 0
    assert out1["accepted"] == 2
    assert out1["rejected"] == []

    rc_show = cli.main(["--db", str(db_path), "show", "--symbol", "ATW"])
    shown = json.loads(capsys.readouterr().out)
    assert rc_show == 0
    assert len(shown) >= 1
    assert shown[0]["winning_source"] == "bourse_casablanca"

    rc_cov = cli.main(["--db", str(db_path), "coverage", "--symbol", "ATW"])
    cov = json.loads(capsys.readouterr().out)
    assert rc_cov == 0
    assert "bourse_casablanca" in cov
    assert cov["bourse_casablanca"]["count"] >= 1

    rc2 = cli.main([
        "--db",
        str(db_path),
        "scrape-bourse",
        "--since",
        "2024-01-01",
        "--until",
        "2024-12-31",
    ])
    out2 = json.loads(capsys.readouterr().out)
    assert rc2 == 0
    assert out2["accepted"] == 0
    assert out2["rejected"] == []


def test_cli_scrape_bourse_dry_run(monkeypatch, tmp_path, capsys):
    page1 = _load_fixture("bc_dividendes_page1.json")
    page2 = _load_fixture("bc_dividendes_page2.json")
    next_url = page1["links"]["next"]["href"]

    def fake_get_json(self, url: str, *, params=None):
        if params and int(params.get("page[offset]", 0)) == 0:
            return page1
        if url == next_url:
            return page2
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr("ingestion.http.client.PoliteClient.get_json", fake_get_json)

    db_path = tmp_path / "ca.sqlite"
    rc = cli.main(
        [
            "--db",
            str(db_path),
            "scrape-bourse",
            "--since",
            "2024-01-01",
            "--until",
            "2024-12-31",
            "--dry-run",
        ]
    )

    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert len(out) == 2
    assert out[0]["source"] == "bourse_casablanca"

    # Dry-run should not write to DB.
    rc_cov = cli.main(["--db", str(db_path), "coverage", "--symbol", "ATW"])
    cov = json.loads(capsys.readouterr().out)
    assert rc_cov == 0
    assert cov == {}
