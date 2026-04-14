"""
BourseCasaAgent — scrapes the Bourse de Casablanca JSON:API for
dividend corporate actions.

Endpoint: https://api.casablanca-bourse.com/fr/api/emetteurs/dividendes
  - Drupal 10 / JSON:API 1.0, 50 records/page, standard pagination
  - Record shape (attributes):
      name:                "Dividendes (<ISSUER>) - <YEAR>"
      dateDetachement:     "DD/MM/YYYY"         # ex-date
      datePaiement:        "DD/MM/YYYY"         # unused by v1 back_adjust
      montantDividende:    "<float as string>"  # per share, MAD
      drupal_internal__tid: <int>               # stable source_ref

Scope (Phase 1): dividends only. adjuster.py v1 only back-adjusts
DIVIDEND + SPLIT events; CAPITAL_INCREASE / RIGHTS_ISSUE are stored
with a "not adjusted" warning (validator.py). Wiring
/api/emetteurs/augmentation-capital now would populate the store with
events the read path can't act on — half a feature. Add it when
adjuster support lands.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

from trading_tools.corporate_actions import (
    CandidateObservation,
    Confidence,
    EventType,
)

from ..http import PoliteClient
from .base import BaseAgent

log = logging.getLogger(__name__)

_BASE_URL = "https://api.casablanca-bourse.com/fr/api/emetteurs/dividendes"
_PAGE_SIZE = 50

_NAME_RE = re.compile(r"^Dividendes\s*\((?P<issuer>.+?)\)\s*-\s*\d{4}\s*$")
_NON_ALNUM_SPACE = re.compile(r"[^A-Z0-9' ]+")
_WS = re.compile(r"\s+")

_DEFAULT_MAPPING_PATH = Path(__file__).parent.parent / "mappings" / "issuer_symbols.json"


def _normalize_issuer(raw: str) -> str:
    """
    Canonicalize an issuer string for lookup:
      - uppercase
      - strip punctuation except apostrophe (e.g. "D'OULMES")
      - collapse whitespace
    The mapping file's keys are pre-normalized; loader applies
    _normalize_issuer on both sides so minor layout changes in BC's
    name strings don't break the lookup.
    """
    up = raw.upper()
    stripped = _NON_ALNUM_SPACE.sub(" ", up)
    return _WS.sub(" ", stripped).strip()


def load_issuer_map(path: Optional[Path] = None) -> Dict[str, str]:
    """Load and normalize the issuer → symbol mapping file."""
    path = path or _DEFAULT_MAPPING_PATH
    with path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    out: Dict[str, str] = {}
    for key, value in raw.items():
        if key.startswith("_"):
            continue
        out[_normalize_issuer(key)] = value.strip().upper()
    return out


class BourseCasaAgent(BaseAgent):
    """JSON:API agent for Bourse de Casablanca dividends."""

    SOURCE = "bourse_casablanca"
    CONFIDENCE = Confidence.OPERATIONAL

    def __init__(
        self,
        client: PoliteClient,
        issuer_map: Optional[Dict[str, str]] = None,
        *,
        base_url: str = _BASE_URL,
        page_size: int = _PAGE_SIZE,
    ) -> None:
        self._client = client
        self._issuer_map = issuer_map if issuer_map is not None else load_issuer_map()
        self._base_url = base_url
        self._page_size = page_size

    def run(self, since: date, until: date) -> Iterator[CandidateObservation]:
        if since > until:
            raise ValueError(f"since ({since}) must be <= until ({until})")

        next_url: Optional[str] = self._base_url
        first_params: Dict[str, Any] = {
            "page[limit]": self._page_size,
            "page[offset]": 0,
        }

        while next_url:
            params = first_params if next_url == self._base_url else None
            payload = self._client.get_json(next_url, params=params)
            for record in payload.get("data") or []:
                obs = self._to_observation(record, since, until)
                if obs is not None:
                    yield obs
            next_url = _extract_next_link(payload)

    def _to_observation(
        self,
        record: Dict[str, Any],
        since: date,
        until: date,
    ) -> Optional[CandidateObservation]:
        attrs = record.get("attributes") or {}
        name = attrs.get("name") or ""

        match = _NAME_RE.match(name)
        if match is None:
            log.warning("bc.name_unparsed", extra={"name": name})
            return None

        issuer_raw = match.group("issuer")
        key = _normalize_issuer(issuer_raw)
        symbol = self._issuer_map.get(key)
        if symbol is None:
            log.warning(
                "bc.issuer_unknown",
                extra={"issuer": issuer_raw, "normalized": key},
            )
            return None

        ex_date_str = attrs.get("dateDetachement")
        if not ex_date_str:
            log.warning("bc.missing_ex_date", extra={"symbol": symbol, "name": name})
            return None
        try:
            ex_date = datetime.strptime(ex_date_str, "%d/%m/%Y").date()
        except ValueError:
            log.warning(
                "bc.bad_ex_date",
                extra={"symbol": symbol, "ex_date": ex_date_str},
            )
            return None

        if not (since <= ex_date <= until):
            return None

        amount_raw = attrs.get("montantDividende")
        try:
            amount = float(amount_raw)
        except (TypeError, ValueError):
            log.warning(
                "bc.bad_amount",
                extra={"symbol": symbol, "amount": amount_raw, "ex_date": ex_date_str},
            )
            return None

        tid = attrs.get("drupal_internal__tid")
        source_ref = f"bc_tid={tid}" if tid is not None else None
        source_url = f"{self._base_url}/{record.get('id')}" if record.get("id") else None

        return CandidateObservation(
            symbol=symbol,
            event_type=EventType.DIVIDEND,
            ex_date=ex_date,
            payload={"amount": amount, "currency": "MAD"},
            source=self.SOURCE,
            confidence=self.CONFIDENCE,
            source_url=source_url,
            source_ref=source_ref,
        )


def _extract_next_link(payload: Dict[str, Any]) -> Optional[str]:
    """JSON:API 1.0: links.next may be a string or {href: ...} object."""
    nxt = (payload.get("links") or {}).get("next")
    if nxt is None:
        return None
    if isinstance(nxt, dict):
        return nxt.get("href")
    if isinstance(nxt, str):
        return nxt
    return None
