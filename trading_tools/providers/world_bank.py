"""
World Bank Pink Sheet commodity data client.

The Pink Sheet publishes monthly commodity prices as an XLSX workbook.
Phosphate rock has no Yahoo Finance ticker; the Pink Sheet is the
canonical public source. Cadence is monthly, so change metrics are
month-over-month rather than true 30-day.
"""

from __future__ import annotations

import io
import logging
import re
import threading
from datetime import date
from typing import List, Optional, Tuple

import requests


log = logging.getLogger(__name__)


# The Pink Sheet URL rotates yearly (path contains the current year's doc id).
# Resolve dynamically off the commodity-markets landing page to avoid bit-rot.
_LANDING_URL = "https://www.worldbank.org/en/research/commodity-markets"
_PINK_SHEET_HREF_RE = re.compile(
    r"https://thedocs\.worldbank\.org/[^\"'<> ]+/CMO-Historical-Data-Monthly\.xlsx",
    re.I,
)

_SHEET_NAME = "Monthly Prices"
_HEADER_ROW_INDEX = 4  # 0-based — the row containing commodity names.
_DATA_START_ROW_INDEX = 6
_MONTH_RE = re.compile(r"^(?P<year>\d{4})M(?P<month>\d{1,2})$")


def _month_label_to_date(label: str) -> Optional[date]:
    match = _MONTH_RE.match(label.strip())
    if not match:
        return None
    year = int(match.group("year"))
    month = int(match.group("month"))
    try:
        # Use the last day of the month as a deterministic as_of anchor.
        if month == 12:
            return date(year, 12, 31)
        next_month_first = date(year + (1 if month == 12 else 0), (month % 12) + 1, 1)
        return date.fromordinal(next_month_first.toordinal() - 1)
    except ValueError:
        return None


def parse_phosphate_series(xlsx_bytes: bytes) -> List[Tuple[date, float]]:
    """
    Extract the Phosphate rock monthly series from a Pink Sheet XLSX blob.

    Returns an ascending list of (end-of-month date, usd_per_mt).
    """
    import openpyxl  # imported lazily — dependency is only needed here.

    workbook = openpyxl.load_workbook(
        io.BytesIO(xlsx_bytes),
        data_only=True,
        read_only=True,
    )
    try:
        sheet = workbook[_SHEET_NAME]
    except KeyError:
        log.warning("world_bank.sheet_missing", extra={"sheet": _SHEET_NAME})
        return []

    header: Optional[tuple] = None
    points: List[Tuple[date, float]] = []
    column_index: Optional[int] = None

    for row_index, row in enumerate(sheet.iter_rows(values_only=True)):
        if row_index == _HEADER_ROW_INDEX:
            header = row
            for idx, cell in enumerate(header):
                if cell and "phosphate" in str(cell).lower():
                    column_index = idx
                    break
            if column_index is None:
                log.warning("world_bank.phosphate_column_missing")
                return []
            continue

        if row_index < _DATA_START_ROW_INDEX:
            continue

        label = row[0]
        if not label:
            continue
        when = _month_label_to_date(str(label))
        if when is None:
            continue

        value = row[column_index]
        if isinstance(value, (int, float)):
            points.append((when, float(value)))

    points.sort(key=lambda p: p[0])
    return points


class WorldBankCommodityClient:
    """Fetches and caches the Pink Sheet phosphate series in-memory."""

    def __init__(self, session: requests.Session, timeout: float) -> None:
        self._session = session
        self._timeout = timeout
        self._lock = threading.Lock()
        self._cached: Optional[List[Tuple[date, float]]] = None

    def _resolve_pink_sheet_url(self) -> Optional[str]:
        try:
            response = self._session.get(
                _LANDING_URL,
                headers={"User-Agent": "Mozilla/5.0 (casabourse-lens)"},
                timeout=self._timeout,
            )
            response.raise_for_status()
        except Exception as exc:
            log.warning("world_bank.landing_fetch_failed", extra={"error": str(exc)})
            return None

        match = _PINK_SHEET_HREF_RE.search(response.text)
        return match.group(0) if match else None

    def _fetch_series(self) -> List[Tuple[date, float]]:
        url = self._resolve_pink_sheet_url()
        if not url:
            return []
        try:
            response = self._session.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (casabourse-lens)"},
                timeout=self._timeout * 3,  # xlsx is ~800KB
            )
            response.raise_for_status()
        except Exception as exc:
            log.warning("world_bank.xlsx_fetch_failed", extra={"url": url, "error": str(exc)})
            return []

        return parse_phosphate_series(response.content)

    def phosphate_rock_latest(self) -> Tuple[Optional[float], Optional[float], Optional[str]]:
        """
        Return (latest_usd_per_mt, month_over_month_change_pct, as_of_iso).

        Series is monthly — MoM change is the honest interpretation of
        "30-day change". Callers should surface that caveat.
        """
        with self._lock:
            if self._cached is None:
                self._cached = self._fetch_series()

        points = self._cached
        if not points:
            return None, None, None

        when, value = points[-1]
        change_pct: Optional[float] = None
        if len(points) >= 2:
            _, prior = points[-2]
            if prior:
                change_pct = round(((value / prior) - 1) * 100.0, 4)

        return value, change_pct, when.isoformat()
