from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

import requests


log = logging.getLogger(__name__)


class YahooMarketDataClient:
    """Tiny Yahoo Finance chart API wrapper for daily close series."""

    def __init__(self, session: requests.Session, timeout: float) -> None:
        self._session = session
        self._timeout = timeout

    def daily_close_points(self, symbol: str, *, range_: str = "3mo") -> List[tuple[date, float]]:
        try:
            response = self._session.get(
                f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}",
                params={"interval": "1d", "range": range_},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=self._timeout,
            )
            response.raise_for_status()
            payload = response.json()
            result = ((payload.get("chart") or {}).get("result") or [None])[0] or {}
            timestamps = result.get("timestamp") or []
            quotes = (((result.get("indicators") or {}).get("quote") or [None])[0] or {})
            closes = quotes.get("close") or []

            points: List[tuple[date, float]] = []
            for ts, close in zip(timestamps, closes):
                if close is None:
                    continue
                points.append(
                    (
                        datetime.fromtimestamp(int(ts), tz=timezone.utc).date(),
                        float(close),
                    )
                )
            points.sort(key=lambda x: x[0])
            return points
        except Exception as exc:
            log.warning(
                "yahoo.request_failed",
                extra={"symbol": symbol, "error": str(exc)},
            )
            return []


def latest_and_change(
    points: List[tuple[date, float]],
    lookback_days: int,
) -> tuple[Optional[float], Optional[float], Optional[str]]:
    if not points:
        return None, None, None
    latest_date, latest_value = points[-1]
    target = latest_date - timedelta(days=lookback_days)
    prior_candidates = [v for d, v in points if d <= target]
    prior = prior_candidates[-1] if prior_candidates else points[0][1]
    if prior == 0:
        return latest_value, None, latest_date.isoformat()
    change = ((latest_value / prior) - 1) * 100
    return latest_value, round(change, 4), latest_date.isoformat()
