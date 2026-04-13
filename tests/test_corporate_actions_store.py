"""
CorporateActionStore — the event log must be idempotent,
point-in-time queryable, and honest about what it holds.

Invariants tested:
  - record_observation is idempotent on (source, observation_hash)
  - get_observations(as_of=T) returns strictly the observations with
    observed_at <= T (the point-in-time guarantee)
  - get_events hides pending_review/disputed by default
  - coverage() reports per-source counts and last_observed
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

pytest.importorskip("trading_tools.corporate_actions")

from trading_tools.corporate_actions import (  # noqa: E402
    CandidateObservation,
    Confidence,
    CorporateAction,
    CorporateActionStore,
    EventStatus,
    EventType,
)

pytestmark = pytest.mark.v2_only


@pytest.fixture
def store(tmp_path):
    s = CorporateActionStore(tmp_path / "ca.sqlite")
    yield s
    s.close()


def _obs(
    source: str,
    ex_date: str = "2025-05-12",
    amount: float = 16.5,
    event_type: EventType = EventType.DIVIDEND,
    observed_at: str = "2025-05-01T00:00:00+00:00",
    source_ref: str | None = None,
) -> CandidateObservation:
    payload = {"amount": amount} if event_type is EventType.DIVIDEND else {"ratio": amount}
    return CandidateObservation(
        symbol="ATW",
        event_type=event_type,
        ex_date=date.fromisoformat(ex_date),
        payload=payload,
        source=source,
        confidence=Confidence.OPERATIONAL,
        source_ref=source_ref,
        observed_at=observed_at,
    )


def test_record_observation_assigns_id(store):
    obs_id = store.record_observation(_obs("ammc"))
    assert isinstance(obs_id, int) and obs_id > 0


def test_record_observation_is_idempotent(store):
    a = store.record_observation(_obs("ammc"))
    b = store.record_observation(_obs("ammc"))  # same source + hash
    assert a == b
    rows = store.get_observations("ATW")
    assert len(rows) == 1


def test_different_source_same_payload_stored_separately(store):
    store.record_observation(_obs("ammc"))
    store.record_observation(_obs("bourse_casablanca"))
    rows = store.get_observations("ATW")
    assert len(rows) == 2


def test_get_observations_filters_event_type(store):
    store.record_observation(_obs("ammc", event_type=EventType.DIVIDEND, amount=16.5))
    store.record_observation(
        _obs("ammc", event_type=EventType.SPLIT, amount=2.0, source_ref="split-ref")
    )
    divs = store.get_observations("ATW", event_types=[EventType.DIVIDEND])
    assert len(divs) == 1
    assert divs[0][1].event_type is EventType.DIVIDEND


def test_point_in_time_as_of_excludes_later_observations(store):
    store.record_observation(_obs("ammc", observed_at="2025-04-01T00:00:00+00:00"))
    store.record_observation(
        _obs("bourse_casablanca", observed_at="2025-06-01T00:00:00+00:00")
    )

    # As of 2025-05-01 — only the April observation exists
    cutoff = datetime(2025, 5, 1, tzinfo=timezone.utc)
    snapshot = store.get_observations("ATW", as_of=cutoff)
    assert len(snapshot) == 1
    assert snapshot[0][1].source == "ammc"

    # Now is both
    current = store.get_observations("ATW")
    assert len(current) == 2


def test_upsert_event_replaces_existing_row(store):
    ev1 = CorporateAction(
        symbol="ATW",
        event_type=EventType.DIVIDEND,
        ex_date=date(2025, 5, 12),
        status=EventStatus.PENDING_REVIEW,
        amount=16.0,
        winning_source="wafabourse",
    )
    store.upsert_event(ev1)

    ev2 = CorporateAction(
        symbol="ATW",
        event_type=EventType.DIVIDEND,
        ex_date=date(2025, 5, 12),
        status=EventStatus.CONFIRMED,
        amount=16.5,
        winning_source="ammc",
    )
    store.upsert_event(ev2)

    events = store.get_events("ATW")
    assert len(events) == 1
    assert events[0].amount == 16.5
    assert events[0].status is EventStatus.CONFIRMED
    assert events[0].winning_source == "ammc"


def test_get_events_hides_pending_by_default(store):
    store.upsert_event(
        CorporateAction(
            symbol="ATW",
            event_type=EventType.SPLIT,
            ex_date=date(2025, 6, 1),
            status=EventStatus.PENDING_REVIEW,
            ratio=2.0,
        )
    )
    store.upsert_event(
        CorporateAction(
            symbol="ATW",
            event_type=EventType.DIVIDEND,
            ex_date=date(2025, 5, 12),
            status=EventStatus.CONFIRMED,
            amount=16.5,
        )
    )
    confirmed_only = store.get_events("ATW")
    assert [e.event_type for e in confirmed_only] == [EventType.DIVIDEND]

    both = store.get_events("ATW", include_pending=True)
    assert len(both) == 2


def test_get_events_filters_by_date_range(store):
    for ex_date in ("2024-05-12", "2025-05-12", "2026-05-12"):
        store.upsert_event(
            CorporateAction(
                symbol="ATW",
                event_type=EventType.DIVIDEND,
                ex_date=date.fromisoformat(ex_date),
                status=EventStatus.CONFIRMED,
                amount=16.0,
            )
        )
    events = store.get_events(
        "ATW", from_date=date(2025, 1, 1), to_date=date(2025, 12, 31)
    )
    assert len(events) == 1
    assert events[0].ex_date.year == 2025


def test_coverage_reports_per_source(store):
    store.record_observation(_obs("ammc", observed_at="2025-04-01T00:00:00+00:00"))
    store.record_observation(
        _obs(
            "ammc",
            ex_date="2024-05-12",
            observed_at="2024-05-10T00:00:00+00:00",
            source_ref="prior-year",
        )
    )
    store.record_observation(_obs("wafabourse", observed_at="2025-05-10T00:00:00+00:00"))
    cov = store.coverage("ATW")
    assert cov["ammc"]["count"] == 2
    assert cov["ammc"]["last_observed"] == "2025-04-01T00:00:00+00:00"
    assert cov["wafabourse"]["count"] == 1


def test_reopen_recovers_data(tmp_path):
    path = tmp_path / "reopen.sqlite"
    s1 = CorporateActionStore(path)
    s1.record_observation(_obs("ammc"))
    s1.close()

    s2 = CorporateActionStore(path)
    rows = s2.get_observations("ATW")
    assert len(rows) == 1
    s2.close()
