"""
AMMC HTML scraper helpers for earnings/publication calendar data.

AMMC does not expose a clean public JSON endpoint for this use case.
The production path is therefore HTML extraction over the issuer
publications pages, with verified TLS and conservative parsing.

This module is intentionally source-neutral at the call boundary:
callers pass a symbol and get a normalized calendar payload back.
"""

from __future__ import annotations

import html as html_lib
import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import httpx

from ingestion.http.client import _build_ssl_context, _default_extra_ca_files

log = logging.getLogger(__name__)

_AMMC_PAGES: tuple[tuple[str, str], ...] = (
    ("issuer_press_releases", "https://www.ammc.ma/fr/communiques-presse-emetteurs"),
    ("issuer_documents", "https://www.ammc.ma/fr/espace-emetteurs/documents-information"),
)

_AMMC_REGULATORY_PAGES: tuple[tuple[str, str], ...] = (
    ("ammc_news", "https://www.ammc.ma/fr/actualites"),
    ("issuer_press_releases", "https://www.ammc.ma/fr/communiques-presse-emetteurs"),
    ("issuer_documents", "https://www.ammc.ma/fr/espace-emetteurs/documents-information"),
)

_NAME_RE = re.compile(
    r"^(?P<issuer>.+?)\s*(?:[-–—]\s+|\s+–\s+|\s+-\s+)(?P<title>.+?)\s*$"
)
_TIME_BLOCK_RE = re.compile(
    r'<time[^>]*datetime="(?P<published_at>[^"]+)"[^>]*>.*?</time>(?P<body>.*?)(?=<time[^>]*datetime="|$)',
    re.I | re.S,
)
_FIELD_CONTENT_RE = re.compile(
    r'<span[^>]*class="field-content"[^>]*>(?P<text>.*?)</span>',
    re.I | re.S,
)
_ANCHOR_RE = re.compile(r'<a[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<text>.*?)</a>', re.I | re.S)
_DATE_RE = re.compile(
    r"(?P<day>\d{1,2})\s*(?:/|\-|\s)\s*(?P<month>[A-Za-zÀ-ÿ]+|\d{1,2})\s*(?:/|\-|\s)\s*(?P<year>\d{4})",
    re.I,
)

_MONTHS = {
    "janvier": 1,
    "fevrier": 2,
    "février": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "aout": 8,
    "août": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "decembre": 12,
    "décembre": 12,
}

_DEFAULT_MAPPING_PATH = Path(__file__).resolve().parent.parent.parent / "ingestion" / "mappings" / "issuer_symbols.json"

_TENDER_OFFER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bOPA\b", re.I),
    re.compile(r"\bOPR\b", re.I),
    re.compile(r"\bOPE\b", re.I),
    re.compile(r"\boffre\s+publique\b", re.I),
)

_PROFIT_WARNING_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bprofit\s*warning\b", re.I),
    re.compile(r"\bavertissement\b", re.I),
    re.compile(r"\balerte\b", re.I),
    re.compile(r"\bmise\s+en\s+garde\b", re.I),
    re.compile(r"\bwarning\b", re.I),
)

_MATERIAL_DISCLOSURE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bfranchissement\s+de\s+seuil\b", re.I),
    re.compile(r"\bd[ée]claration\s+de\s+franchissement\b", re.I),
    re.compile(r"\bd[ée]claration\s+d[’']intention\b", re.I),
    re.compile(r"\bvisa\b", re.I),
    re.compile(r"\bnote\s+d[’']information\b", re.I),
    re.compile(r"\bcommuniqu[ée]\s+important\b", re.I),
)


@dataclass(frozen=True)
class AmmcCalendarItem:
    symbol: str
    issuer_name: str
    event_kind: str
    title: str
    event_date: str
    published_at: str
    source_page: str
    source_url: str
    pdf_url: Optional[str]
    detail_url: Optional[str]
    date_source: str
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "issuer_name": self.issuer_name,
            "event_kind": self.event_kind,
            "title": self.title,
            "event_date": self.event_date,
            "published_at": self.published_at,
            "source_page": self.source_page,
            "source_url": self.source_url,
            "pdf_url": self.pdf_url,
            "detail_url": self.detail_url,
            "date_source": self.date_source,
            "warnings": list(self.warnings),
        }


def _normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text or "")
    no_marks = "".join(ch for ch in folded if not unicodedata.combining(ch))
    upper = no_marks.upper()
    return re.sub(r"[^A-Z0-9' ]+", " ", upper).strip()


class AmmcScraperError(RuntimeError):
    pass


def load_issuer_map(path: Optional[Path] = None) -> Dict[str, str]:
    path = path or _DEFAULT_MAPPING_PATH
    with path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    out: Dict[str, str] = {}
    for key, value in raw.items():
        if key.startswith("_"):
            continue
        out[_normalize(key)] = str(value).strip().upper()
    return out


_LEGAL_SUFFIXES: tuple[str, ...] = (
    " SA",
    " S A",
    " S.A.",
    " S.A",
    " GROUP",
    " GROUPE",
    " HOLDING",
)


def build_runtime_issuer_map(
    static_map: Dict[str, str],
    tickers: Optional[Iterable[Dict[str, Any]]],
) -> Dict[str, str]:
    """
    Expand the static issuer map with live ticker/libellé pairs.

    Static entries take precedence — hand-curated variants win over
    autogenerated ones — so this is purely additive. Safe to call with
    tickers=None (falls back to static map).
    """
    merged: Dict[str, str] = dict(static_map)

    if not tickers:
        return merged

    for row in tickers:
        symbol_raw = row.get("Symbol") if isinstance(row, dict) else None
        libelle_raw = row.get("Libelle") if isinstance(row, dict) else None
        if not symbol_raw or not libelle_raw:
            continue
        symbol = str(symbol_raw).strip().upper()
        libelle = str(libelle_raw).strip()
        if not symbol or not libelle:
            continue

        variants = {libelle}
        upper = libelle.upper()
        for suffix in _LEGAL_SUFFIXES:
            if upper.endswith(suffix):
                variants.add(libelle[: len(libelle) - len(suffix)].strip())

        for variant in variants:
            normalized = _normalize(variant)
            if not normalized:
                continue
            merged.setdefault(normalized, symbol)

    return merged


def _clean_text(raw: str) -> str:
    text = html_lib.unescape(raw or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_date_fragment(raw: str) -> Optional[date]:
    if not raw:
        return None
    fragment = _clean_text(raw)
    match = _DATE_RE.search(fragment)
    if not match:
        return None
    day = int(match.group("day"))
    month_raw = match.group("month").strip().lower()
    month_raw = unicodedata.normalize("NFKD", month_raw)
    month_raw = "".join(ch for ch in month_raw if not unicodedata.combining(ch))
    if month_raw.isdigit():
        month = int(month_raw)
    else:
        month = _MONTHS.get(month_raw)
    if month is None:
        return None
    year = int(match.group("year"))
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _split_issuer_title(raw: str) -> tuple[str, str]:
    text = _clean_text(raw)
    match = _NAME_RE.match(text)
    if match:
        return match.group("issuer").strip(), match.group("title").strip()
    return text, text


def _event_kind(title: str) -> str:
    normalized = _normalize(title)
    if any(token in normalized for token in ("AGO", "AG", "CONVOCATION", "ASSEMBLEE", "REUNION", "RÉUNION")):
        return "meeting"
    if any(
        token in normalized
        for token in (
            "RESULTAT",
            "RESULTATS",
            "RAPPORT",
            "ETATS FINANCIERS",
            "RFS",
            "RFA",
            "PUBLICATION",
            "COMMUNIQUE",
            "DOSSIER D INFORMATION",
            "NOTICE D INFORMATION",
            "BILLET DE TRESORERIE",
            "AUGMENTATION DE CAPITAL",
            "PAIEMENT",
            "RENDEMENT",
        )
    ):
        return "publication"
    return "filing"


def _extract_first_pdf_href(body: str) -> Optional[str]:
    for match in _ANCHOR_RE.finditer(body):
        href = html_lib.unescape(match.group("href"))
        if href.lower().endswith(".pdf"):
            return href
    return None


def _extract_detail_href(body: str) -> Optional[str]:
    for match in _ANCHOR_RE.finditer(body):
        href = html_lib.unescape(match.group("href"))
        if href.lower().endswith(".pdf"):
            continue
        if href.startswith("javascript:"):
            continue
        return href
    return None


def _extract_title(body: str) -> Optional[str]:
    match = _FIELD_CONTENT_RE.search(body)
    if match:
        return _clean_text(match.group("text"))
    for match in _ANCHOR_RE.finditer(body):
        href = html_lib.unescape(match.group("href"))
        if href.lower().endswith(".pdf"):
            continue
        title = _clean_text(match.group("text"))
        if title:
            return title
    return None


def _parse_html_page(page_key: str, html: str, source_url: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for block in _TIME_BLOCK_RE.finditer(html):
        published_at_raw = block.group("published_at")
        body = block.group("body")
        title = _extract_title(body)
        if not title:
            continue
        issuer_raw, title_text = _split_issuer_title(title)
        items.append(
            {
                "page_key": page_key,
                "published_at": published_at_raw,
                "issuer_raw": issuer_raw,
                "title": title_text,
                "event_kind": _event_kind(title_text),
                "pdf_url": _extract_first_pdf_href(body),
                "detail_url": _extract_detail_href(body),
                "source_url": source_url,
            }
        )
    return items


def _parse_published_at(raw: str) -> datetime:
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _extract_symbol(issuer_raw: str, issuer_map: Dict[str, str]) -> Optional[str]:
    normalized = _normalize(issuer_raw)
    if normalized in issuer_map:
        return issuer_map[normalized]
    for issuer_name, symbol in issuer_map.items():
        if normalized.startswith(issuer_name) or issuer_name.startswith(normalized):
            return symbol
    return None


def _extract_symbol_from_text(text: str, issuer_map: Dict[str, str]) -> Optional[str]:
    normalized = _normalize(text)
    if not normalized:
        return None
    for issuer_name, symbol in issuer_map.items():
        if issuer_name in normalized:
            return symbol
    return None


def _classify_regulatory_filing(title: str) -> Optional[str]:
    clean = _clean_text(title)
    for pattern in _TENDER_OFFER_PATTERNS:
        if pattern.search(clean):
            return "tender_offer"
    for pattern in _PROFIT_WARNING_PATTERNS:
        if pattern.search(clean):
            return "profit_warning"
    for pattern in _MATERIAL_DISCLOSURE_PATTERNS:
        if pattern.search(clean):
            return "material_disclosure"
    return None


def fetch_earnings_calendar(
    symbol: str,
    *,
    lookahead_days: int = 365,
    limit: int = 5,
    timeout: float = 20.0,
    issuer_map: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Pull AMMC issuer-publication listings and return the next known
    calendar items for a symbol.

    The source is HTML-rendered and not a clean API, so parsing is
    conservative and warnings are surfaced to the caller.
    """
    symbol_u = symbol.strip().upper()
    lookahead_days = max(1, min(int(lookahead_days), 730))
    limit = max(1, min(int(limit), 20))
    issuer_map = issuer_map or load_issuer_map()

    warnings: list[str] = []
    today = date.today()

    pages = list(_AMMC_PAGES)
    # The financial-statements listing is particularly useful for calendar events.
    pages.append(("issuer_financial_statements", "https://www.ammc.ma/fr/liste-etats-financiers-emetteurs"))

    all_items: list[AmmcCalendarItem] = []
    source_counts: Dict[str, int] = {}

    ssl_context = _build_ssl_context(_default_extra_ca_files())
    with httpx.Client(
        verify=ssl_context,
        follow_redirects=True,
        timeout=timeout,
        headers={
            "User-Agent": "casabourse-lens/0.1 (+https://github.com/ijaija/casabourse-lens)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    ) as client:
        for page_key, url in pages:
            try:
                response = client.get(url)
                response.raise_for_status()
            except Exception as exc:
                warnings.append(f"source_unavailable:{page_key}")
                log.warning(
                    "ammc.fetch_failed",
                    extra={"page": page_key, "url": url, "error": str(exc)},
                )
                continue

            source_counts[page_key] = source_counts.get(page_key, 0) + 1
            page_items = _parse_html_page(page_key, response.text, url)
            for raw_item in page_items:
                issuer_symbol = _extract_symbol(raw_item["issuer_raw"], issuer_map)
                if issuer_symbol is None:
                    warnings.append(f"unmapped_issuer:{raw_item['issuer_raw']}")
                    continue

                published_at = _parse_published_at(raw_item["published_at"])
                event_date = _parse_date_fragment(raw_item["title"]) or published_at.date()
                if (event_date - today).days > lookahead_days:
                    continue

                date_source = "title" if _parse_date_fragment(raw_item["title"]) else "published_at"
                all_items.append(
                    AmmcCalendarItem(
                        symbol=issuer_symbol,
                        issuer_name=raw_item["issuer_raw"],
                        event_kind=raw_item["event_kind"],
                        title=raw_item["title"],
                        event_date=event_date.isoformat(),
                        published_at=published_at.isoformat(),
                        source_page=page_key,
                        source_url=raw_item["source_url"],
                        pdf_url=raw_item["pdf_url"],
                        detail_url=raw_item["detail_url"],
                        date_source=date_source,
                    )
                )

    matching = [item for item in all_items if item.symbol == symbol_u]
    matching.sort(key=lambda item: (item.event_date, item.published_at, item.title))

    future = [item for item in matching if item.event_date >= today.isoformat()]
    next_items = future[:limit]
    if len(next_items) < limit:
        past = [item for item in matching if item.event_date < today.isoformat()]
        past.sort(key=lambda item: (item.event_date, item.published_at, item.title), reverse=True)
        for item in past:
            if len(next_items) >= limit:
                break
            next_items.append(item)

    next_event = next_items[0] if next_items else None

    return {
        "symbol": symbol_u,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "source": "ammc_html",
        "lookahead_days": lookahead_days,
        "next_event_date": next_event.event_date if next_event else None,
        "next_event_kind": next_event.event_kind if next_event else None,
        "next_event_title": next_event.title if next_event else None,
        "coverage": {
            "pages_checked": [page for page, _ in pages],
            "pages_retrieved": source_counts,
            "matched_items": len(matching),
        },
        "warnings": warnings,
        "events": [item.to_dict() for item in next_items],
    }


def fetch_regulatory_filings(
    symbol: str,
    *,
    lookback_days: int = 365,
    limit: int = 20,
    timeout: float = 20.0,
    issuer_map: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Pull AMMC pages and return regulatory filing notices for a symbol.

    Scope targets event-risk categories:
      - tender_offer (OPA/OPR/OPE / offre publique)
      - profit_warning
      - material_disclosure (franchissement, visa, note d'information...)
    """
    symbol_u = symbol.strip().upper()
    lookback_days = max(1, min(int(lookback_days), 730))
    limit = max(1, min(int(limit), 100))
    issuer_map = issuer_map or load_issuer_map()

    warnings: list[str] = []
    today = date.today()
    oldest = today.fromordinal(today.toordinal() - lookback_days)

    source_counts: Dict[str, int] = {}
    filings: list[dict[str, Any]] = []
    seen: set[tuple[str, str, Optional[str]]] = set()

    ssl_context = _build_ssl_context(_default_extra_ca_files())
    with httpx.Client(
        verify=ssl_context,
        follow_redirects=True,
        timeout=timeout,
        headers={
            "User-Agent": "casabourse-lens/0.1 (+https://github.com/ijaija/casabourse-lens)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    ) as client:
        for page_key, url in _AMMC_REGULATORY_PAGES:
            try:
                response = client.get(url)
                response.raise_for_status()
            except Exception as exc:
                warnings.append(f"source_unavailable:{page_key}")
                log.warning(
                    "ammc.fetch_failed",
                    extra={"page": page_key, "url": url, "error": str(exc)},
                )
                continue

            source_counts[page_key] = source_counts.get(page_key, 0) + 1
            for raw_item in _parse_html_page(page_key, response.text, url):
                filing_type = _classify_regulatory_filing(raw_item["title"])
                if filing_type is None:
                    continue

                item_symbol = _extract_symbol(raw_item["issuer_raw"], issuer_map)
                if item_symbol is None:
                    item_symbol = _extract_symbol_from_text(raw_item["title"], issuer_map)
                if item_symbol is None:
                    warnings.append(f"unmapped_issuer:{raw_item['issuer_raw']}")
                    continue
                if item_symbol != symbol_u:
                    continue

                published_at = _parse_published_at(raw_item["published_at"])
                published_date = published_at.date()
                if published_date < oldest:
                    continue

                dedupe_key = (raw_item["title"], published_at.isoformat(), raw_item["pdf_url"])
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)

                filings.append(
                    {
                        "symbol": item_symbol,
                        "issuer_name": raw_item["issuer_raw"],
                        "filing_type": filing_type,
                        "title": raw_item["title"],
                        "published_at": published_at.isoformat(),
                        "published_date": published_date.isoformat(),
                        "source_page": raw_item["page_key"],
                        "source_url": raw_item["source_url"],
                        "pdf_url": raw_item["pdf_url"],
                        "detail_url": raw_item["detail_url"],
                        "warnings": [],
                    }
                )

    filings.sort(key=lambda row: row["published_at"], reverse=True)
    filings = filings[:limit]

    return {
        "symbol": symbol_u,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "source": "ammc_html",
        "lookback_days": lookback_days,
        "filing_count": len(filings),
        "latest_filing_date": filings[0]["published_date"] if filings else None,
        "coverage": {
            "pages_checked": [page for page, _ in _AMMC_REGULATORY_PAGES],
            "pages_retrieved": source_counts,
            "matched_items": len(filings),
        },
        "warnings": warnings,
        "filings": filings,
    }
