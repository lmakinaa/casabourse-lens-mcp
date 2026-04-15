from __future__ import annotations

from dataclasses import dataclass

import pytest

from trading_tools.providers import ammc_calendar


SAMPLE_PRESS_RELEASES = """
<html>
  <body>
    <time datetime="2026-04-15T10:37:26Z">15/04/2026</time>
    <span class="field-content">AtlantaSanad - Avis de convocation à l'AGO du 15 mai 2026</span>
    <a href="/sites/default/files/Avis_AtlantaSanad_AGO_19_05_26.pdf">Avis_AtlantaSanad_AGO_19_05_26.pdf</a>
    <time datetime="2026-04-15T10:36:00Z">15/04/2026</time>
    <span class="field-content">Immorente Invest - CP relatif au paiement des 1er et 2e rendements trimestriels de l'année 2026</span>
    <a href="/sites/default/files/CP_Immorente_paiement_1er_2e_rendement_trimestriel_2026.pdf">CP_Immorente_paiement_1er_2e_rendement_trimestriel_2026.pdf</a>
  </body>
</html>
"""

SAMPLE_DOCS = """
<html>
  <body>
    <time datetime="2026-04-03T16:55:08Z">03/04/2026</time>
        <span class="field-content">AtlantaSanad – L’AMMC vise la mise à jour annuelle du dossier d'information relatif à un programme d'émission</span>
        <a href="/sites/default/files/PEG_ATL_007_2026.pdf">PEG_ATL_007_2026.pdf</a>
  </body>
</html>
"""

SAMPLE_REGULATORY = """
<html>
    <body>
        <time datetime="2026-04-10T09:15:00Z">10/04/2026</time>
        <span class="field-content">AtlantaSanad - Projet d'offre publique de retrait (OPR)</span>
        <a href="/sites/default/files/OPR_ATL_2026.pdf">OPR_ATL_2026.pdf</a>
        <time datetime="2026-04-08T12:00:00Z">08/04/2026</time>
        <span class="field-content">AtlantaSanad - Avertissement sur résultats annuels 2026</span>
        <a href="/sites/default/files/Warning_ATL_2026.pdf">Warning_ATL_2026.pdf</a>
        <time datetime="2026-04-07T11:00:00Z">07/04/2026</time>
        <span class="field-content">AtlantaSanad - Déclaration de franchissement de seuil de participation</span>
        <a href="/sites/default/files/Franchissement_ATL_2026.pdf">Franchissement_ATL_2026.pdf</a>
    </body>
</html>
"""


@dataclass
class _Response:
    text: str

    def raise_for_status(self) -> None:
        return None


class _Client:
    def __init__(self, *args, **kwargs):
        return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def get(self, url: str):
        if "actualites" in url:
            return _Response(SAMPLE_REGULATORY)
        if "communiques-presse-emetteurs" in url:
            return _Response(SAMPLE_PRESS_RELEASES)
        if "documents-information" in url:
            return _Response(SAMPLE_DOCS)
        return _Response("<html><body></body></html>")


def test_fetch_earnings_calendar_uses_title_date_and_fallback(monkeypatch):
    issuer_map = {
        "ATLANTASANAD": "ATL",
        "IMMORENTE INVEST": "IMO",
    }
    monkeypatch.setattr(ammc_calendar.httpx, "Client", _Client)

    out = ammc_calendar.fetch_earnings_calendar("ATL", issuer_map=issuer_map)

    assert out["symbol"] == "ATL"
    assert out["source"] == "ammc_html"
    assert out["next_event_date"] == "2026-05-15"
    assert out["next_event_kind"] == "meeting"
    assert out["next_event_title"] == "Avis de convocation à l'AGO du 15 mai 2026"
    assert out["coverage"]["matched_items"] == 2
    assert out["events"][0]["date_source"] == "title"
    assert out["events"][1]["date_source"] == "published_at"


def test_parse_html_page_extracts_items():
    items = ammc_calendar._parse_html_page(
        "issuer_press_releases",
        SAMPLE_PRESS_RELEASES,
        "https://www.ammc.ma/fr/communiques-presse-emetteurs",
    )
    assert len(items) == 2
    assert items[0]["issuer_raw"] == "AtlantaSanad"
    assert items[0]["title"] == "Avis de convocation à l'AGO du 15 mai 2026"
    assert items[0]["pdf_url"] == "/sites/default/files/Avis_AtlantaSanad_AGO_19_05_26.pdf"
    assert items[1]["issuer_raw"] == "Immorente Invest"


def test_parse_date_fragment_supports_french_months():
    assert ammc_calendar._parse_date_fragment("du 15 mai 2026") == ammc_calendar.date(2026, 5, 15)
    assert ammc_calendar._parse_date_fragment("15/05/2026") == ammc_calendar.date(2026, 5, 15)


def test_classify_regulatory_filing_categories():
    assert ammc_calendar._classify_regulatory_filing("Projet d'offre publique de retrait (OPR)") == "tender_offer"
    assert ammc_calendar._classify_regulatory_filing("Avertissement sur résultats") == "profit_warning"
    assert (
        ammc_calendar._classify_regulatory_filing("Déclaration de franchissement de seuil de participation")
        == "material_disclosure"
    )


def test_fetch_regulatory_filings_extracts_event_risk_items(monkeypatch):
    issuer_map = {
        "ATLANTASANAD": "ATL",
    }
    monkeypatch.setattr(ammc_calendar.httpx, "Client", _Client)

    out = ammc_calendar.fetch_regulatory_filings(
        "ATL",
        lookback_days=365,
        limit=10,
        issuer_map=issuer_map,
    )

    assert out["symbol"] == "ATL"
    assert out["source"] == "ammc_html"
    assert out["filing_count"] >= 3
    assert out["latest_filing_date"] == "2026-04-10"
    assert {row["filing_type"] for row in out["filings"]} >= {
        "tender_offer",
        "profit_warning",
        "material_disclosure",
    }
