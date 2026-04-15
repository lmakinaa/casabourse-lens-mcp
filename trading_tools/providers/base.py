"""
DataProvider contract.

Every data source (WafaBourse today; AMMC, BAM, FX, news tomorrow) must
implement this interface. Tools consume DataProvider — they never see a
concrete client. This is the seam that makes roadmap items #1-#20 cheap
to add instead of requiring shotgun surgery across tools.py.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional


class DataClass(str, Enum):
    """
    Categorisation of data by cache/freshness semantics.

    The cache layer keys its TTL policy off these classes — adding a new
    provider method means picking the right DataClass, nothing more.
    """

    MARKET_STATUS = "market_status"
    INDEX = "index"
    TICKERS = "tickers"
    TOP_MOVERS = "top_movers"
    STOCK_QUOTE = "stock_quote"
    ORDER_BOOK = "order_book"
    PRICE_HISTORY = "price_history"
    RECENT_TRADES = "recent_trades"
    COMPANY_PROFILE = "company_profile"
    SHAREHOLDERS = "shareholders"
    FINANCIAL_METRICS = "financial_metrics"
    MACRO_SNAPSHOT = "macro_snapshot"
    FX_RATES = "fx_rates"
    COMMODITY_PRICES = "commodity_prices"
    NEWS = "news"
    NEWS_SENTIMENT = "news_sentiment"
    EARNINGS_CALENDAR = "earnings_calendar"


class ProviderError(RuntimeError):
    """Raised when a provider cannot satisfy a request and has no fallback."""


class DataProvider(ABC):
    """
    Abstract data source for Moroccan equities.

    Methods return raw, source-neutral dicts/lists. Callers must not
    assume any specific backend. Return None signals "no data available"
    (not an error); raise ProviderError for hard failures.
    """

    name: str = "abstract"

    @abstractmethod
    def get_market_status(self) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    def get_all_tickers(self) -> Optional[List[Dict[str, Any]]]: ...

    @abstractmethod
    def get_market_index(self) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    def get_top_movers(self, type_: str) -> Optional[List[Dict[str, Any]]]: ...

    @abstractmethod
    def get_stock_details(self, symbol: str) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    def get_order_book(self, symbol: str, depth: int = 5) -> Optional[List[Dict[str, Any]]]: ...

    @abstractmethod
    def get_price_history(self, symbol: str) -> Optional[List[Dict[str, Any]]]: ...

    @abstractmethod
    def get_recent_trades(self, symbol: str) -> Optional[List[Dict[str, Any]]]: ...

    @abstractmethod
    def get_company_profile(self, symbol: str) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    def get_shareholders(self, symbol: str) -> Optional[List[Dict[str, Any]]]: ...

    @abstractmethod
    def get_financial_metrics(self, symbol: str) -> Optional[List[Dict[str, Any]]]: ...

    @abstractmethod
    def get_macro_snapshot(self) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    def get_fx_rates(self) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    def get_commodity_prices(self) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    def get_news(
        self,
        symbol: str,
        *,
        limit: int = 20,
        days: int = 7,
    ) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    def get_news_sentiment(
        self,
        symbol: str,
        *,
        window_days: int = 7,
    ) -> Optional[Dict[str, Any]]: ...

    @abstractmethod
    def get_earnings_calendar(
        self,
        symbol: str,
        *,
        lookahead_days: int = 365,
    ) -> Optional[Dict[str, Any]]: ...
