"""
Deterministic fixtures + a fake upstream client that satisfies the
duck-typed data-source contract on BOTH main (WafaBourseAPI) and v2
(DataProvider). Tests target the MCP-facing behaviour of TradingTools
via execute_tool(), which is stable across branches.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional


def _synth_history(n: int = 60, start: float = 100.0) -> List[Dict[str, Any]]:
    """Deterministic OHLCV series: sinusoidal drift, no randomness."""
    history = []
    for i in range(n):
        close = start + 5 * math.sin(i / 3.0) + i * 0.1
        high = close + 0.8
        low = close - 0.8
        history.append(
            {
                "Seance": f"2026-01-{(i % 28) + 1:02d}",
                "Cours": round(close, 4),
                "Ouverture": round(close - 0.2, 4),
                "PlusHaut": round(high, 4),
                "PlusBas": round(low, 4),
                "Volume": 1_000_000 + i * 1000,
            }
        )
    return history


def stock_details(symbol: str = "TEST", price: float = 110.0) -> Dict[str, Any]:
    return {
        "Symbol": symbol,
        "Libelle": f"{symbol} Co",
        "Cours": price,
        "Variation": 1.1,
        "VariationP": 1.0,
        "Ouverture": 109.0,
        "PlusHaut": 111.5,
        "PlusBas": 108.5,
        "Volume": 5_000_000,
        "NbrTransaction": 250,
        "VariationPDAnnee": 12.5,
        "PlusHautDAnnee": 120.0,
        "PlusBasDAnnee": 95.0,
        "PourcentageAchat": 55.0,
        "PourcentageVente": 45.0,
        "Capitalisation": 5_000_000_000,
    }


def market_index() -> Dict[str, Any]:
    return {
        "Cours": 13_500.0,
        "VariationP": 0.42,
        "Volume": 250_000_000,
        "NbrHausse": 40,
        "NbrBaisse": 25,
    }


def top_movers(kind: str) -> List[Dict[str, Any]]:
    base = [
        {"Symbol": "AAA", "Cours": 100.0, "Variation": 2.0, "Qte": 10_000},
        {"Symbol": "BBB", "Cours": 50.0, "Variation": 1.5, "Qte": 8_000},
        {"Symbol": "CCC", "Cours": 75.0, "Variation": 1.0, "Qte": 5_000},
    ]
    if kind == "B":
        for s in base:
            s["Variation"] = -s["Variation"]
    return base


def order_book() -> List[Dict[str, Any]]:
    return [
        {"Achat": 109.5, "Vente": 110.5, "QteAchat": 1000, "QteVente": 800},
        {"Achat": 109.0, "Vente": 111.0, "QteAchat": 500, "QteVente": 600},
        {"Achat": 108.5, "Vente": 111.5, "QteAchat": 300, "QteVente": 400},
        {"Achat": 108.0, "Vente": 112.0, "QteAchat": 200, "QteVente": 250},
        {"Achat": 107.5, "Vente": 112.5, "QteAchat": 150, "QteVente": 200},
    ]


def recent_trades() -> List[Dict[str, Any]]:
    # WafaBourse returns trades newest-first, with fields Prix/Qte/Heure/
    # IdLigne/Variation. No Sens (aggressor) field is exposed.
    return [
        {"IdLigne": 5, "Heure": "10:04:00", "Prix": 110.0, "Qte": 90, "Variation": 0.0},
        {"IdLigne": 4, "Heure": "10:03:00", "Prix": 110.3, "Qte": 120, "Variation": 0.27},
        {"IdLigne": 3, "Heure": "10:02:00", "Prix": 110.1, "Qte": 80, "Variation": -0.09},
        {"IdLigne": 2, "Heure": "10:01:00", "Prix": 110.2, "Qte": 150, "Variation": 0.18},
        {"IdLigne": 1, "Heure": "10:00:00", "Prix": 110.0, "Qte": 100, "Variation": 0.0},
    ]


def all_tickers() -> List[Dict[str, Any]]:
    return [
        {
            "Symbol": "AAA",
            "Libelle": "Alpha",
            "Cours": 100.0,
            "VariationP": 2.0,
            "Variation": 2.0,
            "Volume": 10_000_000,
            "PlusHaut": 101,
            "PlusBas": 99,
            "Ouverture": 100,
            "PlusHautDAnnee": 120,
            "PlusBasDAnnee": 80,
        },
        {
            "Symbol": "BBB",
            "Libelle": "Beta",
            "Cours": 50.0,
            "VariationP": -1.5,
            "Variation": -0.75,
            "Volume": 5_000_000,
            "PlusHaut": 51,
            "PlusBas": 49,
            "Ouverture": 50.5,
            "PlusHautDAnnee": 60,
            "PlusBasDAnnee": 45,
        },
        {
            "Symbol": "CCC",
            "Libelle": "Gamma",
            "Cours": 75.0,
            "VariationP": 0.0,
            "Variation": 0.0,
            "Volume": 1_000_000,
            "PlusHaut": 75,
            "PlusBas": 75,
            "Ouverture": 75,
            "PlusHautDAnnee": 90,
            "PlusBasDAnnee": 60,
        },
    ]


def company_profile(symbol: str = "TEST") -> Dict[str, Any]:
    return {
        "Symbol": symbol,
        "Libelle": f"{symbol} Co",
        "Ising": "MA0000000001",
        "Secteur": "Banks",
        "Presentation": "Line 1$$Line 2||Disclaimer",
        "DateIntroduction": "2010-01-01 00:00:00",
        "NbrTitres": 10_000_000,
        "Capitalisation": 1_100_000_000,
        "SiteInternet": " https://example.ma ",
    }


def shareholders() -> List[Dict[str, Any]]:
    return [
        {"Libelle": "Holding A", "Pourcentage": 40.0},
        {"Libelle": "Holding B", "Pourcentage": 25.0},
        {"Libelle": "Flottant", "Pourcentage": 35.0},
    ]


def financial_metrics() -> List[Dict[str, Any]]:
    return [
        {"Libelle": "P/E Ratio (earnings)", "IdGroupe": 1, "2023": 12.0, "2022": 14.0},
        {"Libelle": "Dividend Yield", "IdGroupe": 1, "2023": 4.5, "2022": 4.0},
        {"Libelle": "Price to Book", "IdGroupe": 1, "2023": 1.8, "2022": 2.0},
        {"Libelle": "Bénéfice par action", "IdGroupe": 2, "2023": 9.0, "2022": 8.0},
        {"Libelle": "Dividende par action", "IdGroupe": 2, "2023": 4.0, "2022": 3.5},
        {"Libelle": "Actif net par action", "IdGroupe": 2, "2023": 60.0, "2022": 55.0},
        {"Libelle": "Marge opérationnelle", "IdGroupe": 3, "2023": 25.0, "2022": 23.0},
        {"Libelle": "Marge nette", "IdGroupe": 3, "2023": 18.0, "2022": 16.0},
        {"Libelle": "Chiffre d'affaires", "IdGroupe": 4, "2023": 10000, "2022": 9500},
        {"Libelle": "Résultat exploitation", "IdGroupe": 4, "2023": 2500, "2022": 2300},
        {"Libelle": "Résultat net", "IdGroupe": 4, "2023": 1800, "2022": 1600},
    ]


def macro_snapshot() -> Dict[str, Any]:
    return {
        "policy_rate_pct": 3.0,
        "t_bill_13w_pct": 2.85,
        "t_bill_52w_pct": 3.1,
        "cpi_yoy_pct": 1.7,
        "masi_dividend_yield_pct": 3.9,
        "equity_risk_premium_pct": 0.8,
        "as_of": "2026-04-14",
        "warnings": [],
        "source": "fake_macro",
    }


def fx_rates() -> Dict[str, Any]:
    return {
        "usd_mad_spot": 9.98,
        "eur_mad_spot": 10.82,
        "usd_mad_20d_change_pct": 0.45,
        "eur_mad_20d_change_pct": -0.22,
        "as_of": "2026-04-15",
        "warnings": [],
        "source": "fake_fx",
    }


def commodity_prices() -> Dict[str, Any]:
    return {
        "brent_usd_per_bbl": 84.2,
        "brent_30d_change_pct": 3.2,
        "gold_usd_per_oz": 2310.0,
        "gold_30d_change_pct": 1.1,
        "phosphate_usd_per_mt": 152.0,
        "phosphate_30d_change_pct": 0.0,
        "as_of": "2026-04-15",
        "warnings": [],
        "source": "fake_commodities",
    }


def news(symbol: str) -> Dict[str, Any]:
    symbol = symbol.upper()
    return {
        "symbol": symbol,
        "window_days": 7,
        "as_of": "2026-04-15T10:00:00+00:00",
        "source": "fake_news",
        "sources_covered": ["medias24", "lavieeco"],
        "article_count": 2,
        "warnings": [],
        "articles": [
            {
                "id": "n1",
                "source": "medias24",
                "title": "Cosumar annonce une croissance du chiffre d'affaires",
                "url": "https://example.com/n1",
                "published_at": "2026-04-15T08:00:00+00:00",
                "summary": "COSUMAR améliore ses marges au T1.",
                "symbols": [symbol],
                "sentiment_score": 0.6,
            },
            {
                "id": "n2",
                "source": "lavieeco",
                "title": "Le secteur sucrier sous pression des coûts",
                "url": "https://example.com/n2",
                "published_at": "2026-04-14T09:00:00+00:00",
                "summary": "Le titre reste surveillé par le marché.",
                "symbols": [symbol],
                "sentiment_score": -0.2,
            },
        ],
    }


def news_sentiment(symbol: str, window_days: int = 7) -> Dict[str, Any]:
    symbol = symbol.upper()
    return {
        "symbol": symbol,
        "window_days": window_days,
        "as_of": "2026-04-15T10:00:00+00:00",
        "source": "fake_news",
        "mentions_current": 4,
        "mentions_baseline_avg": 1.5,
        "mention_volume_delta_pct": 166.6667,
        "sentiment_score": 0.2,
        "sentiment_label": "positive",
        "sample_size": 4,
        "sources_covered": ["medias24", "lavieeco"],
        "warnings": [],
    }


def earnings_calendar(symbol: str, lookahead_days: int = 365) -> Dict[str, Any]:
    symbol = symbol.upper()
    return {
        "symbol": symbol,
        "as_of": "2026-04-15T12:00:00+00:00",
        "source": "ammc_html",
        "lookahead_days": lookahead_days,
        "next_event_date": "2026-05-15",
        "next_event_kind": "meeting",
        "next_event_title": "Avis de convocation à l'AGO du 15 mai 2026",
        "coverage": {
            "pages_checked": [
                "issuer_press_releases",
                "issuer_documents",
                "issuer_financial_statements",
            ],
            "pages_retrieved": {
                "issuer_press_releases": 1,
                "issuer_documents": 1,
                "issuer_financial_statements": 1,
            },
            "matched_items": 2,
        },
        "warnings": [],
        "events": [
            {
                "symbol": symbol,
                "issuer_name": "ATLANTASANAD",
                "event_kind": "meeting",
                "title": "Avis de convocation à l'AGO du 15 mai 2026",
                "event_date": "2026-05-15",
                "published_at": "2026-04-15T10:37:26+00:00",
                "source_page": "issuer_press_releases",
                "source_url": "https://www.ammc.ma/fr/communiques-presse-emetteurs",
                "pdf_url": "https://www.ammc.ma/sites/default/files/Avis_AtlantaSanad_AGO_19_05_26.pdf",
                "detail_url": "/fr/actualites/lammc-met-sur-son-site-internet-les-publications-realisees-par-les-emetteurs-en-date-973",
                "date_source": "title",
                "warnings": [],
            },
            {
                "symbol": symbol,
                "issuer_name": "IMMORENTE INVEST",
                "event_kind": "publication",
                "title": "CP relatif au paiement des 1er et 2e rendements trimestriels de l'année 2026",
                "event_date": "2026-04-15",
                "published_at": "2026-04-15T10:36:00+00:00",
                "source_page": "issuer_documents",
                "source_url": "https://www.ammc.ma/fr/espace-emetteurs/documents-information",
                "pdf_url": "https://www.ammc.ma/sites/default/files/CP_Immorente_paiement_1er_2e_rendement_trimestriel_2026.pdf",
                "detail_url": None,
                "date_source": "published_at",
                "warnings": [],
            },
        ],
    }


class FakeUpstream:
    """
    Duck-typed upstream client. Satisfies:
      - WafaBourseAPI (main branch — no ABC, duck-typed)
      - DataProvider  (v2 branch — ABC happens to match)
    """

    name = "fake"

    def __init__(self) -> None:
        self.history = _synth_history(60)
        self.calls: Dict[str, int] = {}

    def _tick(self, key: str) -> None:
        self.calls[key] = self.calls.get(key, 0) + 1

    def get_market_status(self) -> Optional[Dict[str, Any]]:
        self._tick("market_status")
        return {"Statut": "OPEN"}

    def get_all_tickers(self) -> Optional[List[Dict[str, Any]]]:
        self._tick("all_tickers")
        return all_tickers()

    def get_market_index(self) -> Optional[Dict[str, Any]]:
        self._tick("market_index")
        return market_index()

    def get_top_movers(self, type_: str) -> Optional[List[Dict[str, Any]]]:
        self._tick(f"top_movers:{type_}")
        return top_movers(type_)

    def get_stock_details(self, symbol: str) -> Optional[Dict[str, Any]]:
        self._tick(f"stock_details:{symbol}")
        return stock_details(symbol)

    def get_order_book(
        self, symbol: str, depth: int = 5
    ) -> Optional[List[Dict[str, Any]]]:
        self._tick(f"order_book:{symbol}")
        return order_book()[:depth]

    def get_price_history(self, symbol: str) -> Optional[List[Dict[str, Any]]]:
        self._tick(f"price_history:{symbol}")
        return list(self.history)

    def get_recent_trades(self, symbol: str) -> Optional[List[Dict[str, Any]]]:
        self._tick(f"recent_trades:{symbol}")
        return recent_trades()

    def get_company_profile(self, symbol: str) -> Optional[Dict[str, Any]]:
        self._tick(f"company_profile:{symbol}")
        return company_profile(symbol)

    def get_shareholders(self, symbol: str) -> Optional[List[Dict[str, Any]]]:
        self._tick(f"shareholders:{symbol}")
        return shareholders()

    def get_financial_metrics(
        self, symbol: str
    ) -> Optional[List[Dict[str, Any]]]:
        self._tick(f"financial_metrics:{symbol}")
        return financial_metrics()

    def get_macro_snapshot(self) -> Optional[Dict[str, Any]]:
        self._tick("macro_snapshot")
        return macro_snapshot()

    def get_fx_rates(self) -> Optional[Dict[str, Any]]:
        self._tick("fx_rates")
        return fx_rates()

    def get_commodity_prices(self) -> Optional[Dict[str, Any]]:
        self._tick("commodity_prices")
        return commodity_prices()

    def get_news(
        self,
        symbol: str,
        *,
        limit: int = 20,
        days: int = 7,
    ) -> Optional[Dict[str, Any]]:
        self._tick(f"news:{symbol}:{limit}:{days}")
        payload = news(symbol)
        payload["window_days"] = days
        payload["article_count"] = min(limit, payload["article_count"])
        payload["articles"] = payload["articles"][:limit]
        return payload

    def get_news_sentiment(
        self,
        symbol: str,
        *,
        window_days: int = 7,
    ) -> Optional[Dict[str, Any]]:
        self._tick(f"news_sentiment:{symbol}:{window_days}")
        return news_sentiment(symbol, window_days)

    def get_earnings_calendar(
        self,
        symbol: str,
        *,
        lookahead_days: int = 365,
    ) -> Optional[Dict[str, Any]]:
        self._tick(f"earnings_calendar:{symbol}:{lookahead_days}")
        return earnings_calendar(symbol, lookahead_days)
