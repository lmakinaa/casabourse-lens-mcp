from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Dict, List, Optional, Set
from xml.etree import ElementTree

import requests

log = logging.getLogger(__name__)


# Curl-validated RSS feeds (HTTP 200, application/rss+xml) covering Moroccan
# financial/business press. Sites named in the roadmap that do NOT publish RSS
# — leconomiste.com, fnh.ma, boursenews.ma, lematin.ma — are deliberately
# omitted: probing returned 404 or the site homepage. Re-verify with curl
# before adding.
_FEEDS: tuple[tuple[str, str], ...] = (
    ("medias24", "https://medias24.com/feed/"),
    ("lavieeco", "https://www.lavieeco.com/feed/"),
    ("leseco", "https://leseco.ma/feed/"),
    ("lesiteinfo", "https://www.lesiteinfo.com/feed/"),
    ("aujourdhui", "https://aujourdhui.ma/feed"),
    ("mapnews", "https://www.mapnews.ma/fr/rss.xml"),
)


_POSITIVE_WORDS = {
    "hausse",
    "croissance",
    "amélioration",
    "amelioration",
    "record",
    "solide",
    "profit",
    "résultat",
    "resultat",
    "bénéfice",
    "benefice",
    "surperformance",
    "gains",
    "rebond",
    "bullish",
}

_NEGATIVE_WORDS = {
    "baisse",
    "recul",
    "chute",
    "perte",
    "faible",
    "risque",
    "alerte",
    "dette",
    "déficit",
    "deficit",
    "warning",
    "bearish",
    "difficulté",
    "difficulte",
    "sanction",
}


@dataclass(frozen=True)
class NewsArticle:
    article_id: str
    source: str
    title: str
    url: str
    published_at: str
    summary: str
    symbols: tuple[str, ...]
    sentiment_score: float

    def to_dict(self) -> Dict[str, object]:
        return {
            "id": self.article_id,
            "source": self.source,
            "title": self.title,
            "url": self.url,
            "published_at": self.published_at,
            "summary": self.summary,
            "symbols": list(self.symbols),
            "sentiment_score": self.sentiment_score,
        }


def _normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text or "")
    no_marks = "".join(ch for ch in folded if not unicodedata.combining(ch))
    upper = no_marks.upper()
    return re.sub(r"[^A-Z0-9]+", " ", upper).strip()


def _split_words(text: str) -> List[str]:
    return [w for w in _normalize(text).split(" ") if w]


def _article_id(source: str, link: str, title: str, published_at: str) -> str:
    base = f"{source}|{link}|{title}|{published_at}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


def _parse_pubdate(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _word_boundary_contains(haystack: str, needle: str) -> bool:
    pattern = rf"(^| )" + re.escape(needle) + rf"( |$)"
    return re.search(pattern, haystack) is not None


_INGESTION_MAP_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "ingestion"
    / "mappings"
    / "issuer_symbols.json"
)
_NEWS_ALIASES_PATH = (
    Path(__file__).resolve().parent.parent / "mappings" / "news_aliases.json"
)


def _load_symbol_aliases() -> Dict[str, Set[str]]:
    aliases_by_symbol: Dict[str, Set[str]] = {}

    # Ingestion map: issuer-name -> symbol (legal-entity names).
    try:
        raw = json.loads(_INGESTION_MAP_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning(
            "news.aliases_load_failed",
            extra={"error": str(exc), "path": str(_INGESTION_MAP_PATH)},
        )
        raw = {}

    for issuer_name, symbol in raw.items():
        if issuer_name.startswith("_"):
            continue
        sym = str(symbol).strip().upper()
        if not sym:
            continue
        aliases_by_symbol.setdefault(sym, set()).add(_normalize(issuer_name))
        aliases_by_symbol[sym].add(_normalize(sym))

    # News aliases: symbol -> [press-short-names]. Additive.
    try:
        news_raw = json.loads(_NEWS_ALIASES_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning(
            "news.aliases_news_load_failed",
            extra={"error": str(exc), "path": str(_NEWS_ALIASES_PATH)},
        )
        news_raw = {}

    for symbol, names in news_raw.items():
        if symbol.startswith("_"):
            continue
        sym = str(symbol).strip().upper()
        if not sym or not isinstance(names, list):
            continue
        bucket = aliases_by_symbol.setdefault(sym, set())
        bucket.add(_normalize(sym))
        for name in names:
            normalized = _normalize(str(name))
            if normalized:
                bucket.add(normalized)

    return aliases_by_symbol


def _extract_symbols(text: str, aliases_by_symbol: Dict[str, Set[str]]) -> List[str]:
    normalized = _normalize(text)
    found: List[str] = []

    for symbol, aliases in aliases_by_symbol.items():
        for alias in aliases:
            if not alias:
                continue
            if len(alias) <= 3 and alias == symbol:
                # Guard against noisy false positives for short tickers.
                if _word_boundary_contains(text.upper(), symbol):
                    found.append(symbol)
                    break
                continue
            if _word_boundary_contains(normalized, alias):
                found.append(symbol)
                break

    return sorted(set(found))


def _sentiment_score(text: str) -> float:
    words = _split_words(text)
    if not words:
        return 0.0

    pos = sum(1 for w in words if w.lower() in _POSITIVE_WORDS)
    neg = sum(1 for w in words if w.lower() in _NEGATIVE_WORDS)
    hits = pos + neg
    if hits == 0:
        return 0.0
    score = (pos - neg) / hits
    return round(max(min(score, 1.0), -1.0), 4)


def fetch_news_articles(
    session: requests.Session,
    *,
    timeout: float,
    symbol: str,
    limit: int,
    days: int,
) -> Dict[str, object]:
    symbol_u = symbol.strip().upper()
    days_clamped = max(1, min(days, 30))
    limit_clamped = max(1, min(limit, 200))

    aliases_by_symbol = _load_symbol_aliases()
    now = datetime.now(timezone.utc)
    min_dt = now - timedelta(days=days_clamped)

    warnings: List[str] = []
    articles: List[NewsArticle] = []

    # Feeds vary 0.5s..3s in practice; give them headroom beyond the default
    # 10s provider budget since one slow feed would otherwise drop the whole
    # article (connect timeout is separate and kept tight).
    feed_timeout = (5.0, max(float(timeout), 15.0))

    for source, url in _FEEDS:
        try:
            response = session.get(
                url,
                headers={"User-Agent": "Mozilla/5.0", "Accept": "application/rss+xml, application/xml"},
                timeout=feed_timeout,
            )
            response.raise_for_status()
            root = ElementTree.fromstring(response.content)
        except Exception as exc:
            warnings.append(f"source_unavailable:{source}")
            log.warning("news.feed_unavailable", extra={"source": source, "url": url, "error": str(exc)})
            continue

        for item in root.findall("./channel/item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            summary = (item.findtext("description") or "").strip()
            pub_raw = item.findtext("pubDate")
            pub_dt = _parse_pubdate(pub_raw) or now
            if pub_dt < min_dt:
                continue

            full_text = f"{title} {summary}"
            symbols = _extract_symbols(full_text, aliases_by_symbol)
            if symbol_u not in symbols:
                continue

            article_id = _article_id(source, link, title, pub_dt.isoformat())
            sentiment = _sentiment_score(full_text)
            articles.append(
                NewsArticle(
                    article_id=article_id,
                    source=source,
                    title=title,
                    url=link,
                    published_at=pub_dt.isoformat(),
                    summary=summary,
                    symbols=tuple(symbols),
                    sentiment_score=sentiment,
                )
            )

    dedup: Dict[str, NewsArticle] = {}
    for a in sorted(articles, key=lambda x: x.published_at, reverse=True):
        dedup[a.url or a.article_id] = a

    ranked = list(dedup.values())
    ranked.sort(key=lambda x: x.published_at, reverse=True)
    ranked = ranked[:limit_clamped]

    return {
        "symbol": symbol_u,
        "window_days": days_clamped,
        "as_of": now.isoformat(),
        "source": "rss_v1",
        "sources_covered": sorted({a.source for a in ranked}),
        "article_count": len(ranked),
        "warnings": warnings,
        "articles": [a.to_dict() for a in ranked],
    }


def build_sentiment_snapshot(
    symbol: str,
    window_days: int,
    news_payload: Dict[str, object],
) -> Dict[str, object]:
    symbol_u = symbol.strip().upper()
    window = max(1, min(int(window_days), 30))
    now = datetime.now(timezone.utc)

    articles_raw = news_payload.get("articles") or []
    typed_articles: List[Dict[str, object]] = [a for a in articles_raw if isinstance(a, dict)]

    def as_dt(article: Dict[str, object]) -> datetime:
        raw = str(article.get("published_at") or "")
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return now

    current_start = now - timedelta(days=window)
    baseline_start = current_start - timedelta(days=7)

    current = [a for a in typed_articles if as_dt(a) >= current_start]
    baseline = [a for a in typed_articles if baseline_start <= as_dt(a) < current_start]

    current_mentions = len(current)
    baseline_mentions = len(baseline)
    baseline_daily_avg = round(baseline_mentions / 7.0, 4)
    current_daily_avg = round(current_mentions / float(window), 4)

    mention_delta = None
    if baseline_daily_avg > 0:
        mention_delta = round(((current_daily_avg - baseline_daily_avg) / baseline_daily_avg) * 100.0, 4)

    scores = [float(a.get("sentiment_score") or 0.0) for a in current]
    sentiment_score = round(sum(scores) / len(scores), 4) if scores else 0.0
    if sentiment_score > 0.15:
        label = "positive"
    elif sentiment_score < -0.15:
        label = "negative"
    else:
        label = "neutral"

    warnings = list(news_payload.get("warnings") or [])
    if baseline_daily_avg == 0:
        warnings.append("baseline_mentions_zero")

    return {
        "symbol": symbol_u,
        "window_days": window,
        "as_of": now.isoformat(),
        "source": "rss_v1",
        "mentions_current": current_mentions,
        "mentions_baseline_avg": baseline_daily_avg,
        "mention_volume_delta_pct": mention_delta,
        "sentiment_score": sentiment_score,
        "sentiment_label": label,
        "sample_size": len(scores),
        "sources_covered": sorted({str(a.get("source") or "") for a in current if a.get("source")}),
        "warnings": warnings,
    }
