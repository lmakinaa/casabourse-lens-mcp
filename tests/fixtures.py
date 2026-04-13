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
    return [
        {"Heure": "10:00:00", "Cours": 110.0, "Qte": 100, "Sens": "A"},
        {"Heure": "10:01:00", "Cours": 110.2, "Qte": 150, "Sens": "A"},
        {"Heure": "10:02:00", "Cours": 110.1, "Qte": 80, "Sens": "V"},
        {"Heure": "10:03:00", "Cours": 110.3, "Qte": 120, "Sens": "A"},
        {"Heure": "10:04:00", "Cours": 110.0, "Qte": 90, "Sens": "V"},
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
