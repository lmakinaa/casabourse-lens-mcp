"""
CorporateActionStore — SQLite-backed event log + materialized current view.

Two tables, one purpose: make "what did we believe about ATW dividends
on 2024-06-15?" answerable deterministically.

  ca_observations : append-only raw observations, tagged by source,
                    deduped by observation_hash. The event log.
  ca_events       : reconciled current-truth row per
                    (symbol, event_type, ex_date). Rebuildable from
                    ca_observations at any time.

Point-in-time queries filter ca_observations by observed_at ≤ as_of
and re-run the reconciler on that filtered view. Expensive? Yes, for
deep history. But it's correct — and for an MCP tool handling one
symbol at a time, latency is a non-issue.

Thread-safe: one connection per store instance, guarded by a lock.
Write-heavy workloads should use a dedicated ingestion process.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator, List, Optional, Tuple

from .events import (
    CandidateObservation,
    Confidence,
    CorporateAction,
    EventStatus,
    EventType,
)

log = logging.getLogger(__name__)


_SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS ca_observations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol            TEXT    NOT NULL,
    event_type        TEXT    NOT NULL CHECK (event_type IN
                          ('dividend','split','capital_increase','rights_issue')),
    ex_date           TEXT    NOT NULL,
    payload_json      TEXT    NOT NULL,
    source            TEXT    NOT NULL,
    source_url        TEXT,
    source_ref        TEXT,
    observed_at       TEXT    NOT NULL,
    observed_hash     TEXT    NOT NULL,
    confidence        TEXT    NOT NULL CHECK (confidence IN
                          ('authoritative','operational','aggregator','manual')),
    UNIQUE (source, observed_hash)
);
CREATE INDEX IF NOT EXISTS idx_ca_obs_symbol_date
    ON ca_observations (symbol, ex_date);
CREATE INDEX IF NOT EXISTS idx_ca_obs_observed
    ON ca_observations (observed_at);

CREATE TABLE IF NOT EXISTS ca_events (
    symbol                  TEXT    NOT NULL,
    event_type              TEXT    NOT NULL,
    ex_date                 TEXT    NOT NULL,
    amount                  REAL,
    ratio                   REAL,
    subscription_price      REAL,
    currency                TEXT    NOT NULL DEFAULT 'MAD',
    status                  TEXT    NOT NULL CHECK (status IN
                                ('confirmed','pending_review','disputed','superseded')),
    winning_observation_id  INTEGER REFERENCES ca_observations(id),
    winning_source          TEXT,
    first_seen_at           TEXT,
    confirmed_at            TEXT,
    warnings_json           TEXT    NOT NULL DEFAULT '[]',
    PRIMARY KEY (symbol, event_type, ex_date)
);
CREATE INDEX IF NOT EXISTS idx_ca_events_symbol_date
    ON ca_events (symbol, ex_date);
"""


class CorporateActionStore:
    """
    Read + write API for the corporate-action event log.

    Usage:
        store = CorporateActionStore(Path("data/corporate_actions.sqlite"))
        obs_id = store.record_observation(candidate)
        events = store.get_events("ATW", as_of=date(2024, 6, 15))
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        self._open()

    # ── lifecycle ──────────────────────────────────────────────

    def _open(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False — we guard with our own lock. Python's
        # built-in check blocks legitimate cross-thread reads that our
        # lock already serialises.
        self._conn = sqlite3.connect(
            str(self._db_path),
            isolation_level=None,       # autocommit; we manage transactions explicitly
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA_SQL)

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        """Serialised transaction. Lock held for the whole tx."""
        assert self._conn is not None, "store closed"
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                yield self._conn
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    # ── write path ─────────────────────────────────────────────

    def record_observation(self, obs: CandidateObservation) -> int:
        """
        Append an observation. Idempotent: repeated inserts of the
        same (source, observation_hash) return the existing row id.
        Returns the row id of the observation (new or pre-existing).
        """
        obs_id, _created = self.record_observation_with_status(obs)
        return obs_id

    def record_observation_with_status(self, obs: CandidateObservation) -> tuple[int, bool]:
        """
        Append an observation and return (id, created).

        `created` is True only when a new row is inserted; False when
        the observation already existed (same source + hash).
        """
        obs_hash = obs.observation_hash()
        with self._tx() as conn:
            existing = conn.execute(
                "SELECT id FROM ca_observations WHERE source = ? AND observed_hash = ?",
                (obs.source, obs_hash),
            ).fetchone()
            if existing is not None:
                log.debug(
                    "ca.obs.idempotent_skip",
                    extra={"source": obs.source, "hash": obs_hash[:12]},
                )
                return int(existing["id"]), False

            cur = conn.execute(
                """
                INSERT INTO ca_observations
                    (symbol, event_type, ex_date, payload_json, source,
                     source_url, source_ref, observed_at, observed_hash, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    obs.symbol,
                    obs.event_type.value,
                    obs.ex_date.isoformat(),
                    json.dumps(obs.payload, sort_keys=True),
                    obs.source,
                    obs.source_url,
                    obs.source_ref,
                    obs.observed_at,
                    obs_hash,
                    obs.confidence.value,
                ),
            )
            return int(cur.lastrowid), True

    def upsert_event(self, event: CorporateAction) -> None:
        """
        Write or replace the reconciled event for
        (symbol, event_type, ex_date). Called by the Reconciler only —
        not a public write path.
        """
        with self._tx() as conn:
            conn.execute(
                """
                INSERT INTO ca_events
                    (symbol, event_type, ex_date, amount, ratio, subscription_price,
                     currency, status, winning_observation_id, winning_source,
                     first_seen_at, confirmed_at, warnings_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (symbol, event_type, ex_date) DO UPDATE SET
                    amount = excluded.amount,
                    ratio = excluded.ratio,
                    subscription_price = excluded.subscription_price,
                    currency = excluded.currency,
                    status = excluded.status,
                    winning_observation_id = excluded.winning_observation_id,
                    winning_source = excluded.winning_source,
                    first_seen_at = excluded.first_seen_at,
                    confirmed_at = excluded.confirmed_at,
                    warnings_json = excluded.warnings_json
                """,
                (
                    event.symbol,
                    event.event_type.value,
                    event.ex_date.isoformat(),
                    event.amount,
                    event.ratio,
                    event.subscription_price,
                    event.currency,
                    event.status.value,
                    event.winning_observation_id,
                    event.winning_source,
                    event.first_seen_at,
                    event.confirmed_at,
                    json.dumps(list(event.warnings)),
                ),
            )

    # ── read path ──────────────────────────────────────────────

    def get_observations(
        self,
        symbol: str,
        as_of: Optional[datetime] = None,
        event_types: Optional[Iterable[EventType]] = None,
    ) -> List[Tuple[int, CandidateObservation]]:
        """
        Read raw observations, optionally filtered to only those
        observed on or before `as_of`. Returns (id, observation) pairs
        so the reconciler can record winning_observation_id.
        """
        assert self._conn is not None
        clauses = ["symbol = ?"]
        args: List = [symbol]
        if as_of is not None:
            clauses.append("observed_at <= ?")
            args.append(_iso(as_of))
        if event_types is not None:
            types = list(event_types)
            placeholders = ",".join("?" * len(types))
            clauses.append(f"event_type IN ({placeholders})")
            args.extend(t.value for t in types)

        sql = f"""
            SELECT id, symbol, event_type, ex_date, payload_json, source,
                   source_url, source_ref, observed_at, confidence
            FROM ca_observations
            WHERE {' AND '.join(clauses)}
            ORDER BY ex_date, observed_at
        """
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()

        result: List[Tuple[int, CandidateObservation]] = []
        for row in rows:
            obs = CandidateObservation(
                symbol=row["symbol"],
                event_type=EventType(row["event_type"]),
                ex_date=date.fromisoformat(row["ex_date"]),
                payload=json.loads(row["payload_json"]),
                source=row["source"],
                source_url=row["source_url"],
                source_ref=row["source_ref"],
                observed_at=row["observed_at"],
                confidence=Confidence(row["confidence"]),
            )
            result.append((int(row["id"]), obs))
        return result

    def get_events(
        self,
        symbol: str,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        event_types: Optional[Iterable[EventType]] = None,
        include_pending: bool = False,
    ) -> List[CorporateAction]:
        """
        Read the materialized current-truth view. Does NOT re-run
        reconciliation — call Reconciler.reconcile_symbol() for that.

        `include_pending=False` hides pending_review and disputed events.
        """
        assert self._conn is not None
        clauses = ["symbol = ?"]
        args: List = [symbol]
        if from_date is not None:
            clauses.append("ex_date >= ?")
            args.append(from_date.isoformat())
        if to_date is not None:
            clauses.append("ex_date <= ?")
            args.append(to_date.isoformat())
        if event_types is not None:
            types = list(event_types)
            placeholders = ",".join("?" * len(types))
            clauses.append(f"event_type IN ({placeholders})")
            args.extend(t.value for t in types)
        if not include_pending:
            clauses.append("status = 'confirmed'")

        sql = f"""
            SELECT * FROM ca_events
            WHERE {' AND '.join(clauses)}
            ORDER BY ex_date
        """
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()

        return [_row_to_event(r) for r in rows]

    def coverage(self, symbol: str) -> dict:
        """Summary of which sources have contributed observations for a symbol."""
        assert self._conn is not None
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT source, COUNT(*) AS n, MAX(observed_at) AS last_observed
                FROM ca_observations
                WHERE symbol = ?
                GROUP BY source
                """,
                (symbol,),
            ).fetchall()
        return {r["source"]: {"count": r["n"], "last_observed": r["last_observed"]} for r in rows}


# ── helpers ────────────────────────────────────────────────────


def _row_to_event(row: sqlite3.Row) -> CorporateAction:
    return CorporateAction(
        symbol=row["symbol"],
        event_type=EventType(row["event_type"]),
        ex_date=date.fromisoformat(row["ex_date"]),
        status=EventStatus(row["status"]),
        amount=row["amount"],
        ratio=row["ratio"],
        subscription_price=row["subscription_price"],
        currency=row["currency"] or "MAD",
        winning_observation_id=row["winning_observation_id"],
        winning_source=row["winning_source"],
        first_seen_at=row["first_seen_at"],
        confirmed_at=row["confirmed_at"],
        warnings=tuple(json.loads(row["warnings_json"] or "[]")),
    )


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.replace(microsecond=0).isoformat()
