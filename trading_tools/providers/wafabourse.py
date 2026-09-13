"""
WafaBourse concrete DataProvider.

Wraps the WafaBourse JSON-over-POST endpoint. All HTTP concerns,
payload shaping, and vendor field names are contained here — nothing
above this layer should import requests or reference WafaBourse.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import date
from typing import Any, Dict, List, Optional

import requests

from ..config import (
    DEFAULT_HEADERS,
    REQUEST_TIMEOUT,
    WAFABOURSE_API,
    WAFABOURSE_TOKEN_API,
    WAFABOURSE_TOKEN_REFRESH_MARGIN_SEC,
)
from .ammc_calendar import (
    build_runtime_issuer_map,
    build_runtime_slug_map,
    fetch_earnings_calendar,
    fetch_regulatory_filings,
    load_issuer_map,
    load_issuer_slug_map,
)
from .bam import BamMacroClient
from .base import DataProvider
from .news_rss import build_sentiment_snapshot, fetch_news_articles
from .world_bank import WorldBankCommodityClient
from .yahoo import YahooMarketDataClient, latest_and_change

log = logging.getLogger(__name__)


class WafaBourseProvider(DataProvider):
    """WafaBourse implementation of the DataProvider contract."""

    name = "wafabourse"

    def __init__(self) -> None:
        self.session = requests.Session()
        self.headers = DEFAULT_HEADERS.copy()
        self._yahoo = YahooMarketDataClient(self.session, REQUEST_TIMEOUT)
        self._bam = BamMacroClient(self.session, REQUEST_TIMEOUT)
        self._world_bank = WorldBankCommodityClient(self.session, REQUEST_TIMEOUT)
        self._static_issuer_map = load_issuer_map()
        self._static_issuer_slug_map = load_issuer_slug_map()
        self._issuer_map = self._static_issuer_map
        self._issuer_slug_map = self._static_issuer_slug_map
        self._issuer_map_built = False
        self._proxy_token: Optional[str] = None
        self._proxy_token_expires_at: float = 0.0
        self._proxy_token_lock = threading.Lock()

    def _get_proxy_token(self, *, force_refresh: bool = False) -> Optional[str]:
        now = time.monotonic()
        if not force_refresh and self._proxy_token and now < self._proxy_token_expires_at:
            return self._proxy_token
        with self._proxy_token_lock:
            now = time.monotonic()
            if not force_refresh and self._proxy_token and now < self._proxy_token_expires_at:
                return self._proxy_token
            try:
                response = self.session.get(
                    WAFABOURSE_TOKEN_API,
                    headers=self.headers,
                    timeout=REQUEST_TIMEOUT,
                )
                payload = response.json()
                token = payload.get("token") if isinstance(payload, dict) else None
                expires_in = payload.get("expiresIn") if isinstance(payload, dict) else None
                if not token or not isinstance(expires_in, (int, float)):
                    log.warning(
                        "wafabourse.token_invalid_response",
                        extra={"payload_keys": list(payload.keys()) if isinstance(payload, dict) else type(payload).__name__},
                    )
                    return None
                ttl = max(1.0, float(expires_in) - WAFABOURSE_TOKEN_REFRESH_MARGIN_SEC)
                self._proxy_token = token
                self._proxy_token_expires_at = time.monotonic() + ttl
                return self._proxy_token
            except Exception as exc:
                log.error(
                    "wafabourse.token_fetch_failed",
                    extra={"error": str(exc)},
                )
                return None

    def _request(
        self,
        action_name: str,
        params: List[Dict[str, Any]],
        action_type: str = "SELECT",
        _retried: bool = False,
    ) -> Optional[Any]:
        """Generic WafaBourse action envelope."""
        token = self._get_proxy_token(force_refresh=_retried)
        if not token:
            return None
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
                headers={**self.headers, "x-proxy-token": token},
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )
            data = response.json()
            if isinstance(data, dict) and "error" in data:
                err_msg = str(data.get("error", ""))
                is_token_error = response.status_code == 403 or "token" in err_msg.lower()
                if is_token_error and not _retried:
                    return self._request(action_name, params, action_type, _retried=True)
                log.warning(
                    "wafabourse.error_envelope",
                    extra={"action": action_name, "status": response.status_code, "error": err_msg},
                )
                return None
            if (
                isinstance(data, list)
                and data
                and action_name in data[0]
                and data[0][action_name].get("Valid")
            ):
                return data[0][action_name]["Data"]
            shape = type(data).__name__
            first_keys = list(data[0].keys()) if isinstance(data, list) and data and isinstance(data[0], dict) else (
                list(data.keys()) if isinstance(data, dict) else None
            )
            log.warning(
                "wafabourse.invalid_response",
                extra={"action": action_name, "shape": shape, "first_keys": first_keys},
            )
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
        bam = self._bam.fetch_snapshot()
        warnings: List[str] = list(bam.get("warnings") or [])

        # T-bill yields live on a separate BAM secondary-market page that
        # times out intermittently. Flag and leave null rather than fake.
        warnings.append(
            "t_bill_yields source not yet wired; use /Marche-secondaire/Taux-de-reference"
        )
        # WafaBourse MASI payload does not expose dividend yield.
        warnings.append("masi_dividend_yield source not exposed by wafabourse index payload")

        policy_rate = bam.get("policy_rate_pct")
        cpi = bam.get("cpi_yoy_pct")

        # ERP proxied against the policy rate until T-bill wiring lands.
        # Surfaced null here because MASI DY is unavailable from the current provider.
        erp = None

        as_of_candidates = [
            bam.get("policy_rate_as_of"),
            bam.get("cpi_as_of"),
            bam.get("fx_as_of"),
        ]
        as_of = max((d for d in as_of_candidates if d), default=None)

        return {
            "policy_rate_pct": policy_rate,
            "t_bill_13w_pct": None,
            "t_bill_52w_pct": None,
            "cpi_yoy_pct": cpi,
            "masi_dividend_yield_pct": None,
            "equity_risk_premium_pct": erp,
            "as_of": as_of,
            "warnings": warnings,
            "source": "bam_scrape",
        }

    def get_fx_rates(self) -> Optional[Dict[str, Any]]:
        usd_points = self._yahoo.daily_close_points("USDMAD=X")
        eur_points = self._yahoo.daily_close_points("EURMAD=X")

        usd_spot, usd_change, usd_as_of = latest_and_change(usd_points, 20)
        eur_spot, eur_change, eur_as_of = latest_and_change(eur_points, 20)

        warnings: List[str] = []
        source = "yahoo_finance"

        # BAM fallback for spot only — keeps the tool useful when Yahoo is blocked
        # or returns nothing. 20-day change remains null in that case; we do not
        # fabricate it from a BAM spot alone.
        if usd_spot is None or eur_spot is None:
            bam = self._bam.fetch_snapshot()
            if usd_spot is None and bam.get("usd_mad_spot") is not None:
                usd_spot = bam.get("usd_mad_spot")
                usd_as_of = bam.get("fx_as_of")
                source = "yahoo_finance+bam_scrape"
            if eur_spot is None and bam.get("eur_mad_spot") is not None:
                eur_spot = bam.get("eur_mad_spot")
                eur_as_of = bam.get("fx_as_of")
                source = "yahoo_finance+bam_scrape"

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
            "source": source,
        }

    def get_commodity_prices(self) -> Optional[Dict[str, Any]]:
        brent_series = self._yahoo.daily_close_points("BZ=F")
        gold_series = self._yahoo.daily_close_points("GC=F")

        brent, brent_chg, brent_as_of = latest_and_change(brent_series, 30)
        gold, gold_chg, gold_as_of = latest_and_change(gold_series, 30)
        phosphate, phosphate_chg, phosphate_as_of = self._world_bank.phosphate_rock_latest()

        warnings: List[str] = []
        if brent is None:
            warnings.append("missing Brent series")
        if gold is None:
            warnings.append("missing Gold series")
        if phosphate is None:
            warnings.append("missing phosphate series (world bank pink sheet unavailable)")
        else:
            warnings.append(
                "phosphate cadence is monthly; 30d_change_pct is month-over-month"
            )

        source = "yahoo_finance+world_bank" if phosphate is not None else "yahoo_finance"

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
            "source": source,
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

    def _ensure_issuer_map(self) -> None:
        """
        Lazily expand the static issuer map with the live WafaBourse ticker
        list on first AMMC-facing call. Done lazily because get_all_tickers()
        is a network call and the provider is constructed at import time.
        """
        if self._issuer_map_built:
            return
        self._issuer_map_built = True
        try:
            tickers = self.get_all_tickers()
        except Exception as exc:  # defensive — never block AMMC on this
            log.warning("issuer_map.tickers_fetch_failed", extra={"error": str(exc)})
            return
        if not tickers:
            return
        self._issuer_map = build_runtime_issuer_map(self._static_issuer_map, tickers)
        self._issuer_slug_map = build_runtime_slug_map(self._static_issuer_slug_map, tickers)

    def get_earnings_calendar(
        self,
        symbol: str,
        *,
        lookahead_days: int = 365,
    ) -> Optional[Dict[str, Any]]:
        self._ensure_issuer_map()
        return fetch_earnings_calendar(
            symbol,
            lookahead_days=lookahead_days,
            issuer_map=self._issuer_map,
            issuer_slug_map=self._issuer_slug_map,
        )

    def get_regulatory_filings(
        self,
        symbol: str,
        *,
        lookback_days: int = 365,
        limit: int = 20,
    ) -> Optional[Dict[str, Any]]:
        self._ensure_issuer_map()
        return fetch_regulatory_filings(
            symbol,
            lookback_days=lookback_days,
            limit=limit,
            issuer_map=self._issuer_map,
            issuer_slug_map=self._issuer_slug_map,
        )
