from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

pytest.importorskip("trading_tools.corporate_actions")

from ingestion.agents.bourse_casa import BourseCasaAgent
from trading_tools.corporate_actions import Confidence, EventType

pytestmark = pytest.mark.v2_only


class FakeClient:
    def __init__(self, pages_by_url: dict[str, dict]):
        self._pages_by_url = pages_by_url
        self.calls: list[tuple[str, dict | None]] = []

    def get_json(self, url: str, *, params=None):
        self.calls.append((url, params))
        if params and int(params.get("page[offset]", 0)) == 0:
            return self._pages_by_url["page1"]
        return self._pages_by_url[url]


def _load_fixture(name: str) -> dict:
    path = Path(__file__).parent / "fixtures" / "ingestion" / name
    return json.loads(path.read_text(encoding="utf-8"))


def _issuer_map() -> dict[str, str]:
    return {
        "ATTIJARIWAFA BANK": "ATW",
        "ITISSALAT AL MAGHRIB": "IAM",
    }


def test_agent_parses_known_issuer_and_paginates():
    page1 = _load_fixture("bc_dividendes_page1.json")
    page2 = _load_fixture("bc_dividendes_page2.json")
    next_url = page1["links"]["next"]["href"]

    client = FakeClient({"page1": page1, next_url: page2})
    agent = BourseCasaAgent(client, issuer_map=_issuer_map())

    out = list(agent.run(date(2024, 1, 1), date(2024, 12, 31)))

    assert len(out) == 2
    first = out[0]
    assert first.symbol == "ATW"
    assert first.event_type is EventType.DIVIDEND
    assert first.ex_date == date(2024, 3, 15)
    assert first.payload["amount"] == 19.0
    assert first.source == "bourse_casablanca"
    assert first.confidence is Confidence.OPERATIONAL
    assert first.source_ref == "bc_tid=1001"

    second = out[1]
    assert second.symbol == "IAM"
    assert second.ex_date == date(2024, 5, 20)
    assert second.payload["amount"] == 4.2

    assert len(client.calls) == 2


def test_agent_skips_unknown_outside_window_and_bad_amount(caplog):
    page1 = _load_fixture("bc_dividendes_page1.json")
    page2 = _load_fixture("bc_dividendes_page2.json")
    next_url = page1["links"]["next"]["href"]

    client = FakeClient({"page1": page1, next_url: page2})
    agent = BourseCasaAgent(client, issuer_map=_issuer_map())

    with caplog.at_level("WARNING"):
        out = list(agent.run(date(2024, 1, 1), date(2024, 4, 30)))

    # 2024-03-15 ATW survives; unknown + bad amount are skipped;
    # 2019 record skipped by date window.
    assert [(o.symbol, o.ex_date.isoformat()) for o in out] == [("ATW", "2024-03-15")]

    messages = [r.message for r in caplog.records]
    assert "bc.issuer_unknown" in messages
    assert "bc.bad_amount" in messages


def test_observation_hash_is_stable_across_runs():
    page1 = _load_fixture("bc_dividendes_page1.json")
    page2 = _load_fixture("bc_dividendes_page2.json")
    next_url = page1["links"]["next"]["href"]

    client = FakeClient({"page1": page1, next_url: page2})
    agent = BourseCasaAgent(client, issuer_map=_issuer_map())

    run1 = list(agent.run(date(2024, 1, 1), date(2024, 12, 31)))
    run2 = list(agent.run(date(2024, 1, 1), date(2024, 12, 31)))

    assert [o.observation_hash() for o in run1] == [o.observation_hash() for o in run2]
