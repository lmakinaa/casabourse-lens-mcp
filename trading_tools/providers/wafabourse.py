"""
WafaBourse concrete DataProvider.

Wraps the WafaBourse JSON-over-POST endpoint. All HTTP concerns,
payload shaping, and vendor field names are contained here — nothing
above this layer should import requests or reference WafaBourse.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional

import requests

from ..config import DEFAULT_HEADERS, REQUEST_TIMEOUT, WAFABOURSE_API
from .ammc_calendar import (
    fetch_earnings_calendar,
    fetch_regulatory_filings,
    load_issuer_map,
)
from .base import DataProvider
from .news_rss import build_sentiment_snapshot, fetch_news_articles
from .yahoo import YahooMarketDataClient, latest_and_change

log = logging.getLogger(__name__)


class WafaBourseProvider(DataProvider):
    """WafaBourse implementation of the DataProvider contract."""

    name = "wafabourse"

    def __init__(self) -> None:
        self.session = requests.Session()
        self.headers = DEFAULT_HEADERS.copy()
        self._yahoo = YahooMarketDataClient(self.session, REQUEST_TIMEOUT)
        self._issuer_map = load_issuer_map()

    def _request(
        self,
        action_name: str,
        params: List[Dict[str, Any]],
        action_type: str = "SELECT",
    ) -> Optional[Any]:
        """Generic WafaBourse action envelope."""
        payload = {
            "ACTIONS": [
                {
                    "ACTION": {"NAME": action_name, "TYPE": action_type, "VALUE": action_name},
                    "PARAMS": params,
                }
            ]
        }
        try:
            response = self.session.post(
                WAFABOURSE_API,
                headers=self.headers,
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )
            data = response.json()
            if data and action_name in data[0] and data[0][action_name].get("Valid"):
                return data[0][action_name]["Data"]
            log.warning("wafabourse.invalid_response", extra={"action": action_name})
        except Exception as exc:
            log.error(
                "wafabourse.request_failed",
                extra={"action": action_name, "error": str(exc)},
            )
        return None

    def get_market_status(self) -> Optional[Dict[str, Any]]:
        data = self._request(
            "MARKET-STATUS",
            [
                {"NAME": "Espace", "TYPE": "I", "VALUE": "1"},
                {"NAME": "Numseq_", "TYPE": "I", "VALUE": "0"},
            ],
        )
        return data[0] if data else None

    def get_all_tickers(self) -> Optional[List[Dict[str, Any]]]:
        return self._request(
            "TICKER",
            [
                {"NAME": "NumseqMin_", "TYPE": "I", "VALUE": "0"},
                {"NAME": "NumseqMax_", "TYPE": "I", "VALUE": "0"},
            ],
        )

    def get_market_index(self) -> Optional[Dict[str, Any]]:
        data = self._request(
            "INDICE-SYNTHESE",
            [{"NAME": "Indice_", "TYPE": "S", "VALUE": "MASI"}],
        )
        return data[0] if data else None

    def get_top_movers(self, type_: str) -> Optional[List[Dict[str, Any]]]:
        """type_: H=gainers, B=losers, V=most active."""
        return self._request(
            "INDICE-TOPS",
            [
                {"NAME": "Indice_", "TYPE": "S", "VALUE": "MASI"},
                {"NAME": "TypePalmares_", "TYPE": "S", "VALUE": type_},
            ],
        )

    def get_stock_details(self, symbol: str) -> Optional[Dict[str, Any]]:
        data = self._request(
            "VALEUR-INFOS",
            [{"NAME": "Symbol_", "TYPE": "S", "VALUE": symbol}],
        )
        return data[0] if data else None

    def get_order_book(self, symbol: str, depth: int = 5) -> Optional[List[Dict[str, Any]]]:
        return self._request(
            "VALEUR-PROFONDEUR",
            [
                {"NAME": "Symbol_", "TYPE": "S", "VALUE": symbol},
                {"NAME": "Top_", "TYPE": "I", "VALUE": str(depth)},
                {"NAME": "NumSeq_", "TYPE": "I", "VALUE": "0"},
            ],
        )

    def get_price_history(self, symbol: str) -> Optional[List[Dict[str, Any]]]:
        return self._request(
            "VALEUR-GRAPH",
            [{"NAME": "Symbol_", "TYPE": "S", "VALUE": symbol}],
        )

    def get_recent_trades(self, symbol: str) -> Optional[List[Dict[str, Any]]]:
        return self._request(
            "VALEUR-TRANSACTION",
            [
                {"NAME": "Symbol_", "TYPE": "S", "VALUE": symbol},
                {"NAME": "Top_", "TYPE": "I", "VALUE": "-1"},
            ],
        )

    def get_company_profile(self, symbol: str) -> Optional[Dict[str, Any]]:
        data = self._request(
            "VALEUR-FICHE",
            [
                {"NAME": "Espace_", "TYPE": "S", "VALUE": "1"},
                {"NAME": "Symbol_", "TYPE": "S", "VALUE": symbol},
            ],
        )
        return data[0] if data else None

    def get_shareholders(self, symbol: str) -> Optional[List[Dict[str, Any]]]:
        return self._request(
            "VALEUR-ACTIONNAIRES",
            [
                {"NAME": "Espace_", "TYPE": "S", "VALUE": "1"},
                {"NAME": "Symbol_", "TYPE": "S", "VALUE": symbol},
            ],
        )

    def get_financial_metrics(self, symbol: str) -> Optional[List[Dict[str, Any]]]:
        return self._request(
            "VALEUR-MFS",
            [
                {"NAME": "Espace_", "TYPE": "S", "VALUE": "1"},
                {"NAME": "Symbol_", "TYPE": "S", "VALUE": symbol},
            ],
            action_type="PROCSELECT",
        )

    def get_macro_snapshot(self) -> Optional[Dict[str, Any]]:
        """
        Macro series are not exposed by WafaBourse endpoints used by this provider.

        Return a structured placeholder so upper layers can surface a clean
        warning instead of hard-failing while dedicated BAM/HCP/market-data
        sources are wired.
        """
        return {
            "policy_rate_pct": None,
            "t_bill_13w_pct": None,
            "t_bill_52w_pct": None,
            "cpi_yoy_pct": None,
            "masi_dividend_yield_pct": None,
            "equity_risk_premium_pct": None,
            "as_of": None,
            "warnings": ["macro snapshot source not configured for wafabourse provider"],
            "source": "wafabourse",
        }

    def get_fx_rates(self) -> Optional[Dict[str, Any]]:
        usd_points = self._yahoo.daily_close_points("USDMAD=X")
        eur_points = self._yahoo.daily_close_points("EURMAD=X")

        usd_spot, usd_change, usd_as_of = latest_and_change(usd_points, 20)
        eur_spot, eur_change, eur_as_of = latest_and_change(eur_points, 20)

        warnings: List[str] = []
        if usd_spot is None:
            warnings.append("missing USD/MAD spot")
        if eur_spot is None:
            warnings.append("missing EUR/MAD spot")
        if usd_change is None:
            warnings.append("missing USD/MAD lookback")
        if eur_change is None:
            warnings.append("missing EUR/MAD lookback")

        return {
            "usd_mad_spot": usd_spot,
            "eur_mad_spot": eur_spot,
            "usd_mad_20d_change_pct": usd_change,
            "eur_mad_20d_change_pct": eur_change,
            "as_of": max([d for d in [usd_as_of, eur_as_of] if d], default=None),
            "warnings": warnings,
            "source": "yahoo_finance",
        }

    def get_commodity_prices(self) -> Optional[Dict[str, Any]]:
        brent_series = self._yahoo.daily_close_points("BZ=F")
        gold_series = self._yahoo.daily_close_points("GC=F")

        brent, brent_chg, brent_as_of = latest_and_change(brent_series, 30)
        gold, gold_chg, gold_as_of = latest_and_change(gold_series, 30)
        phosphate = None
        phosphate_chg = None
        phosphate_as_of = None

        warnings: List[str] = []
        if brent is None:
            warnings.append("missing Brent series")
        if gold is None:
            warnings.append("missing Gold series")
        warnings.append("missing phosphate rock direct Yahoo symbol; field left null")

        return {
            "brent_usd_per_bbl": brent,
            "brent_30d_change_pct": brent_chg,
            "gold_usd_per_oz": gold,
            "gold_30d_change_pct": gold_chg,
            "phosphate_usd_per_mt": phosphate,
            "phosphate_30d_change_pct": phosphate_chg,
            "as_of": max(
                [d for d in [brent_as_of, gold_as_of, phosphate_as_of] if d],
                default=None,
            ),
            "warnings": warnings,
            "source": "yahoo_finance",
        }

    def get_news(
        self,
        symbol: str,
        *,
        limit: int = 20,
        days: int = 7,
    ) -> Optional[Dict[str, Any]]:
        return fetch_news_articles(
            self.session,
            timeout=REQUEST_TIMEOUT,
            symbol=symbol,
            limit=limit,
            days=days,
        )

    def get_news_sentiment(
        self,
        symbol: str,
        *,
        window_days: int = 7,
    ) -> Optional[Dict[str, Any]]:
        # Pull a wider window so the baseline has enough observations.
        lookback_days = max(window_days + 7, 14)
        news_payload = self.get_news(symbol, limit=200, days=lookback_days)
        if news_payload is None:
            return None
        return build_sentiment_snapshot(symbol, window_days, news_payload)

    def get_earnings_calendar(
        self,
        symbol: str,
        *,
        lookahead_days: int = 365,
    ) -> Optional[Dict[str, Any]]:
        return fetch_earnings_calendar(
            symbol,
            lookahead_days=lookahead_days,
            issuer_map=self._issuer_map,
        )

    def get_regulatory_filings(
        self,
        symbol: str,
        *,
        lookback_days: int = 365,
        limit: int = 20,
    ) -> Optional[Dict[str, Any]]:
        return fetch_regulatory_filings(
            symbol,
            lookback_days=lookback_days,
            limit=limit,
            issuer_map=self._issuer_map,
        )
