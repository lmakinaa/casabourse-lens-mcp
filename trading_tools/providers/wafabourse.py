"""
WafaBourse concrete DataProvider.

Wraps the WafaBourse JSON-over-POST endpoint. All HTTP concerns,
payload shaping, and vendor field names are contained here — nothing
above this layer should import requests or reference WafaBourse.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import requests

from ..config import DEFAULT_HEADERS, REQUEST_TIMEOUT, WAFABOURSE_API
from .base import DataProvider

log = logging.getLogger(__name__)


class WafaBourseProvider(DataProvider):
    """WafaBourse implementation of the DataProvider contract."""

    name = "wafabourse"

    def __init__(self) -> None:
        self.session = requests.Session()
        self.headers = DEFAULT_HEADERS.copy()

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
