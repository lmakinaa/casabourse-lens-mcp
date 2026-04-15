"""
Bank Al-Maghrib (BAM) macro data client.

Scrapes the BAM homepage, which embeds the headline indicators — policy
rate, CPI YoY, and USD/EUR spot — as JSON blobs inside inline <script>
tags. Parsing is defensive: any single field that fails to extract is
reported as a warning while the rest still return.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests


log = logging.getLogger(__name__)


BAM_HOMEPAGE_URL = "https://www.bkam.ma/"


_JSON_SERIES_RE = re.compile(
    r"var\s+(?P<name>\w+)_json_data\s*=\s*eval\(\s*'(?P<blob>\[[^']*\])'\s*\)",
    re.S,
)

_POINT_RE = re.compile(r"\{\s*x\s*:\s*(?P<x>\d+)\s*,\s*y\s*:\s*(?P<y>-?\d+(?:\.\d+)?)\s*\}")

_FX_BLOCK_RE = re.compile(
    r'<span\s+class="fl">\s*(?P<as_of>\d{2}/\d{2}/\d{4})[^<]*</span>\s*'
    r'<span\s+class="mod">.*?1\s*USD\s*=\s*(?P<usd>\d+(?:\.\d+)?)\s*MAD'
    r'.*?1\s*EUR\s*=\s*(?P<eur>\d+(?:\.\d+)?)\s*MAD',
    re.S | re.I,
)


def _parse_series(html: str, name: str) -> List[Tuple[datetime, float]]:
    for match in _JSON_SERIES_RE.finditer(html):
        if match.group("name") != name:
            continue
        points: List[Tuple[datetime, float]] = []
        for point in _POINT_RE.finditer(match.group("blob")):
            ms = int(point.group("x"))
            value = float(point.group("y"))
            points.append(
                (datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc), value)
            )
        points.sort(key=lambda p: p[0])
        return points
    return []


def _latest(points: List[Tuple[datetime, float]]) -> Tuple[Optional[float], Optional[str]]:
    if not points:
        return None, None
    when, value = points[-1]
    return value, when.date().isoformat()


def _parse_fx(html: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    match = _FX_BLOCK_RE.search(html)
    if not match:
        return None, None, None
    try:
        usd = float(match.group("usd"))
        eur = float(match.group("eur"))
    except ValueError:
        return None, None, None
    day, month, year = match.group("as_of").split("/")
    try:
        as_of = date(int(year), int(month), int(day)).isoformat()
    except ValueError:
        as_of = None
    return usd, eur, as_of


class BamMacroClient:
    """Fetches and parses the BAM homepage into a macro snapshot dict."""

    def __init__(self, session: requests.Session, timeout: float) -> None:
        self._session = session
        self._timeout = timeout

    def _fetch(self) -> Optional[str]:
        try:
            response = self._session.get(
                BAM_HOMEPAGE_URL,
                headers={"User-Agent": "Mozilla/5.0 (casabourse-lens)"},
                timeout=self._timeout,
            )
            response.raise_for_status()
            return response.text
        except Exception as exc:
            log.warning("bam.fetch_failed", extra={"error": str(exc)})
            return None

    def fetch_snapshot(self) -> Dict[str, Any]:
        warnings: List[str] = []
        html = self._fetch()
        if html is None:
            return {
                "policy_rate_pct": None,
                "policy_rate_as_of": None,
                "cpi_yoy_pct": None,
                "cpi_as_of": None,
                "usd_mad_spot": None,
                "eur_mad_spot": None,
                "fx_as_of": None,
                "warnings": ["bam_homepage_unavailable"],
            }
        return self.parse_snapshot(html, warnings=warnings)

    @staticmethod
    def parse_snapshot(html: str, *, warnings: Optional[List[str]] = None) -> Dict[str, Any]:
        warnings = list(warnings or [])

        policy_rate, policy_as_of = _latest(_parse_series(html, "policy_rate"))
        cpi_yoy, cpi_as_of = _latest(_parse_series(html, "inflation_rate"))
        usd, eur, fx_as_of = _parse_fx(html)

        if policy_rate is None:
            warnings.append("bam_policy_rate_unparsed")
        if cpi_yoy is None:
            warnings.append("bam_cpi_unparsed")
        if usd is None or eur is None:
            warnings.append("bam_fx_unparsed")

        return {
            "policy_rate_pct": policy_rate,
            "policy_rate_as_of": policy_as_of,
            "cpi_yoy_pct": cpi_yoy,
            "cpi_as_of": cpi_as_of,
            "usd_mad_spot": usd,
            "eur_mad_spot": eur,
            "fx_as_of": fx_as_of,
            "warnings": warnings,
        }
