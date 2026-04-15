"""
DuckDB write-through cache layer.

Decorator pattern over any DataProvider. Tools don't know caching
exists. Every fetch follows: check cache (fresh? return) → upstream
call → persist → return. On upstream failure with a stale row present,
serve stale (stale-while-revalidate) — the resilience primitive the
roadmap explicitly flags.

Schema: one normalised row-per-fetch table. Payload stored as JSON so
schema changes in upstream providers don't force migrations.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import duckdb

from .base import DataClass, DataProvider

log = logging.getLogger(__name__)


DEFAULT_CACHE_PATH = Path(__file__).resolve().parent.parent.parent / "cache.duckdb"


class TTLPolicy:
    """
    Per-data-class freshness budget (seconds).

    Tuned for Casablanca Stock Exchange trading hours — quotes are
    short-lived, fundamentals are effectively static intraday.
    """

    DEFAULTS: Dict[DataClass, int] = {
        DataClass.MARKET_STATUS: 30,
        DataClass.INDEX: 30,
        DataClass.TICKERS: 30,
        DataClass.TOP_MOVERS: 30,
        DataClass.STOCK_QUOTE: 30,
        DataClass.ORDER_BOOK: 10,
        DataClass.PRICE_HISTORY: 3600,
        DataClass.RECENT_TRADES: 30,
        DataClass.COMPANY_PROFILE: 86_400,
        DataClass.SHAREHOLDERS: 86_400,
        DataClass.FINANCIAL_METRICS: 86_400,
        DataClass.MACRO_SNAPSHOT: 21_600,
        DataClass.FX_RATES: 3600,
        DataClass.COMMODITY_PRICES: 21_600,
    }

    def __init__(self, overrides: Optional[Dict[DataClass, int]] = None) -> None:
        self._ttls = dict(self.DEFAULTS)
        if overrides:
            self._ttls.update(overrides)

    def seconds(self, data_class: DataClass) -> int:
        return self._ttls[data_class]


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS cache_entries (
    data_class   VARCHAR NOT NULL,
    cache_key    VARCHAR NOT NULL,
    source       VARCHAR NOT NULL,
    fetched_at   DOUBLE  NOT NULL,
    payload_json VARCHAR NOT NULL,
    PRIMARY KEY (data_class, cache_key, source)
);
CREATE INDEX IF NOT EXISTS idx_cache_fetched
    ON cache_entries (data_class, cache_key, fetched_at);
"""


class CachingDataProvider(DataProvider):
    """
    Write-through DuckDB cache wrapping another DataProvider.

    Thread-safe via a single lock over the duckdb connection (DuckDB's
    own connection is not thread-safe for writes). If the cache file
    cannot be opened, the decorator transparently delegates to the
    upstream provider — cache failures must never take the app down.
    """

    def __init__(
        self,
        upstream: DataProvider,
        cache_path: Path = DEFAULT_CACHE_PATH,
        ttl_policy: Optional[TTLPolicy] = None,
    ) -> None:
        self._upstream = upstream
        self.name = f"cached({upstream.name})"
        self._ttl = ttl_policy or TTLPolicy()
        self._lock = threading.Lock()
        self._conn: Optional[duckdb.DuckDBPyConnection] = None
        self._cache_path = cache_path
        self._open_cache()

    def _open_cache(self) -> None:
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = duckdb.connect(str(self._cache_path))
            self._conn.execute(_SCHEMA_SQL)
        except Exception as exc:
            log.error(
                "cache.open_failed",
                extra={"path": str(self._cache_path), "error": str(exc)},
            )
            self._conn = None

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def _read(self, data_class: DataClass, cache_key: str) -> Optional[Dict[str, Any]]:
        if self._conn is None:
            return None
        with self._lock:
            try:
                row = self._conn.execute(
                    """
                    SELECT fetched_at, payload_json
                    FROM cache_entries
                    WHERE data_class = ? AND cache_key = ? AND source = ?
                    """,
                    [data_class.value, cache_key, self._upstream.name],
                ).fetchone()
            except Exception as exc:
                log.error("cache.read_failed", extra={"error": str(exc)})
                return None
        if row is None:
            return None
        return {"fetched_at": row[0], "payload": json.loads(row[1])}

    def _write(
        self,
        data_class: DataClass,
        cache_key: str,
        payload: Any,
    ) -> None:
        if self._conn is None:
            return
        with self._lock:
            try:
                self._conn.execute(
                    """
                    INSERT OR REPLACE INTO cache_entries
                        (data_class, cache_key, source, fetched_at, payload_json)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        data_class.value,
                        cache_key,
                        self._upstream.name,
                        time.time(),
                        json.dumps(payload),
                    ],
                )
            except Exception as exc:
                log.error("cache.write_failed", extra={"error": str(exc)})

    def _fetch(
        self,
        data_class: DataClass,
        cache_key: str,
        upstream_call: Callable[[], Any],
    ) -> Any:
        """
        Orchestrate cache read → upstream call → cache write.

        Returns upstream data on fresh hit or successful fetch. Serves
        stale data if upstream fails and a stale row exists (logged).
        """
        trace_id = uuid.uuid4().hex[:8]
        ttl = self._ttl.seconds(data_class)
        cached = self._read(data_class, cache_key)

        if cached is not None:
            age = time.time() - cached["fetched_at"]
            if age <= ttl:
                log.debug(
                    "cache.hit",
                    extra={
                        "trace_id": trace_id,
                        "data_class": data_class.value,
                        "key": cache_key,
                        "age_s": round(age, 2),
                    },
                )
                return cached["payload"]

        try:
            payload = upstream_call()
        except Exception as exc:
            log.error(
                "cache.upstream_error",
                extra={
                    "trace_id": trace_id,
                    "data_class": data_class.value,
                    "key": cache_key,
                    "error": str(exc),
                },
            )
            payload = None

        if payload is None and cached is not None:
            log.warning(
                "cache.stale_served",
                extra={
                    "trace_id": trace_id,
                    "data_class": data_class.value,
                    "key": cache_key,
                    "age_s": round(time.time() - cached["fetched_at"], 2),
                },
            )
            return cached["payload"]

        if payload is not None:
            self._write(data_class, cache_key, payload)
            log.debug(
                "cache.miss_write",
                extra={
                    "trace_id": trace_id,
                    "data_class": data_class.value,
                    "key": cache_key,
                },
            )
        return payload

    def get_market_status(self) -> Optional[Dict[str, Any]]:
        return self._fetch(DataClass.MARKET_STATUS, "_", self._upstream.get_market_status)

    def get_all_tickers(self) -> Optional[List[Dict[str, Any]]]:
        return self._fetch(DataClass.TICKERS, "_", self._upstream.get_all_tickers)

    def get_market_index(self) -> Optional[Dict[str, Any]]:
        return self._fetch(DataClass.INDEX, "MASI", self._upstream.get_market_index)

    def get_top_movers(self, type_: str) -> Optional[List[Dict[str, Any]]]:
        return self._fetch(
            DataClass.TOP_MOVERS,
            type_,
            lambda: self._upstream.get_top_movers(type_),
        )

    def get_stock_details(self, symbol: str) -> Optional[Dict[str, Any]]:
        return self._fetch(
            DataClass.STOCK_QUOTE,
            symbol,
            lambda: self._upstream.get_stock_details(symbol),
        )

    def get_order_book(self, symbol: str, depth: int = 5) -> Optional[List[Dict[str, Any]]]:
        return self._fetch(
            DataClass.ORDER_BOOK,
            f"{symbol}:{depth}",
            lambda: self._upstream.get_order_book(symbol, depth),
        )

    def get_price_history(self, symbol: str) -> Optional[List[Dict[str, Any]]]:
        return self._fetch(
            DataClass.PRICE_HISTORY,
            symbol,
            lambda: self._upstream.get_price_history(symbol),
        )

    def get_recent_trades(self, symbol: str) -> Optional[List[Dict[str, Any]]]:
        return self._fetch(
            DataClass.RECENT_TRADES,
            symbol,
            lambda: self._upstream.get_recent_trades(symbol),
        )

    def get_company_profile(self, symbol: str) -> Optional[Dict[str, Any]]:
        return self._fetch(
            DataClass.COMPANY_PROFILE,
            symbol,
            lambda: self._upstream.get_company_profile(symbol),
        )

    def get_shareholders(self, symbol: str) -> Optional[List[Dict[str, Any]]]:
        return self._fetch(
            DataClass.SHAREHOLDERS,
            symbol,
            lambda: self._upstream.get_shareholders(symbol),
        )

    def get_financial_metrics(self, symbol: str) -> Optional[List[Dict[str, Any]]]:
        return self._fetch(
            DataClass.FINANCIAL_METRICS,
            symbol,
            lambda: self._upstream.get_financial_metrics(symbol),
        )

    def get_macro_snapshot(self) -> Optional[Dict[str, Any]]:
        return self._fetch(
            DataClass.MACRO_SNAPSHOT,
            "_",
            self._upstream.get_macro_snapshot,
        )

    def get_fx_rates(self) -> Optional[Dict[str, Any]]:
        return self._fetch(
            DataClass.FX_RATES,
            "_",
            self._upstream.get_fx_rates,
        )

    def get_commodity_prices(self) -> Optional[Dict[str, Any]]:
        return self._fetch(
            DataClass.COMMODITY_PRICES,
            "_",
            self._upstream.get_commodity_prices,
        )
