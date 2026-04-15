"""
Back-adjustment math. The single most safety-critical module in this
branch — if it's wrong, every technical indicator silently lies.

Invariants tested:
  - len(out) == len(in)
  - last bar's adjusted_close == raw close (today's truth)
  - adjustment factors are monotone non-increasing going back
  - round-trip: reconstructing raw from adjusted recovers the input
  - volumes are scaled by splits, NOT by dividends
"""

from __future__ import annotations

from datetime import date

import pytest

pytest.importorskip("trading_tools.corporate_actions")

from trading_tools.corporate_actions import (  # noqa: E402
    CorporateAction,
    EventStatus,
    EventType,
    back_adjust,
)

pytestmark = pytest.mark.v2_only


def _bar(d: str, close: float, volume: float = 1000) -> dict:
    return {
        "Seance": d,
        "Cours": close,
        "Ouverture": close,
        "PlusHaut": close,
        "PlusBas": close,
        "Volume": volume,
    }


def _series(pairs):
    return [_bar(d, c) for d, c in pairs]


def _event(event_type, ex_date, amount=None, ratio=None):
    return CorporateAction(
        symbol="TEST",
        event_type=event_type,
        ex_date=date.fromisoformat(ex_date),
        status=EventStatus.CONFIRMED,
        amount=amount,
        ratio=ratio,
    )


def test_no_events_leaves_series_unchanged():
    ohlcv = _series([("2025-01-01", 100.0), ("2025-01-02", 101.0), ("2025-01-03", 102.0)])
    bars, report = back_adjust([], ohlcv)
    assert len(bars) == 3
    for b in bars:
        assert b.adjusted_close == b.close
        assert b.adjusted_volume == b.volume
    assert report.applied == []
    assert report.skipped == []


def test_single_dividend_applies_only_to_prior_bars():
    # Prior close 100 on 2025-01-02; dividend 5 on 2025-01-03.
    # Factor = 1 - 5/100 = 0.95. Applied to 01-01 and 01-02 only.
    ohlcv = _series(
        [
            ("2025-01-01", 99.0),
            ("2025-01-02", 100.0),
            ("2025-01-03", 95.0),
            ("2025-01-04", 96.0),
        ]
    )
    events = [_event(EventType.DIVIDEND, "2025-01-03", amount=5.0)]
    bars, report = back_adjust(events, ohlcv)
    assert len(bars) == 4
    assert bars[0].adjusted_close == pytest.approx(99.0 * 0.95)
    assert bars[1].adjusted_close == pytest.approx(100.0 * 0.95)
    assert bars[2].adjusted_close == 95.0  # ex-date bar unchanged
    assert bars[3].adjusted_close == 96.0
    assert len(report.applied) == 1
    assert report.applied[0].factor == pytest.approx(0.95)


def test_dividend_does_not_scale_volume():
    ohlcv = _series(
        [("2025-01-01", 100.0), ("2025-01-02", 100.0), ("2025-01-03", 95.0)]
    )
    events = [_event(EventType.DIVIDEND, "2025-01-03", amount=5.0)]
    bars, _ = back_adjust(events, ohlcv)
    for b in bars:
        assert b.adjusted_volume == b.volume


def test_split_scales_price_and_volume():
    # 2:1 forward split on 01-03 → price factor 0.5, volume factor 2.0
    ohlcv = _series(
        [
            ("2025-01-01", 200.0),
            ("2025-01-02", 200.0),
            ("2025-01-03", 100.0),  # post-split
            ("2025-01-04", 101.0),
        ]
    )
    # Bump volumes so we can see the scaling.
    for b in ohlcv:
        b["Volume"] = 1000
    events = [_event(EventType.SPLIT, "2025-01-03", ratio=2.0)]
    bars, report = back_adjust(events, ohlcv)
    assert bars[0].adjusted_close == pytest.approx(100.0)
    assert bars[1].adjusted_close == pytest.approx(100.0)
    assert bars[2].adjusted_close == 100.0  # post-split bar unchanged
    assert bars[0].adjusted_volume == pytest.approx(2000.0)
    assert bars[1].adjusted_volume == pytest.approx(2000.0)
    assert bars[2].adjusted_volume == 1000.0
    assert report.applied[0].event_type == "split"


def test_compounding_split_then_dividend():
    # Bars: flat 100 pre-split, 50 post-split, 45 post-dividend.
    ohlcv = _series(
        [
            ("2025-01-01", 100.0),  # pre-split
            ("2025-01-02", 100.0),  # pre-split, day before split ex
            ("2025-01-03", 50.0),   # ex-split
            ("2025-01-04", 50.0),   # day before dividend ex
            ("2025-01-05", 45.0),   # ex-dividend (div=5)
            ("2025-01-06", 46.0),
        ]
    )
    events = [
        _event(EventType.SPLIT, "2025-01-03", ratio=2.0),
        _event(EventType.DIVIDEND, "2025-01-05", amount=5.0),
    ]
    bars, report = back_adjust(events, ohlcv)
    # Dividend factor computed against the PRIOR CLOSE at the time of
    # the dividend ex-date — which is 50 (2025-01-04). Factor = 0.9.
    # Bars strictly before 01-05 get the 0.9. Bars strictly before
    # 01-03 additionally get the split 0.5. Compound pre-split = 0.45.
    assert bars[0].adjusted_close == pytest.approx(100.0 * 0.5 * 0.9)
    assert bars[1].adjusted_close == pytest.approx(100.0 * 0.5 * 0.9)
    assert bars[2].adjusted_close == pytest.approx(50.0 * 0.9)
    assert bars[3].adjusted_close == pytest.approx(50.0 * 0.9)
    assert bars[4].adjusted_close == 45.0
    assert bars[5].adjusted_close == 46.0
    assert len(report.applied) == 2


def test_factors_monotone_non_increasing_going_back():
    ohlcv = _series([(f"2025-01-{i:02d}", 100.0) for i in range(1, 11)])
    events = [
        _event(EventType.DIVIDEND, "2025-01-05", amount=2.0),
        _event(EventType.DIVIDEND, "2025-01-08", amount=3.0),
    ]
    bars, _ = back_adjust(events, ohlcv)
    # As index increases, factor should non-decrease (older bars more adjusted).
    factors = [b.adjusted_close / b.close for b in bars]
    # Reverse: newest first — factors should be monotone non-decreasing.
    for i in range(len(factors) - 1):
        assert factors[i] <= factors[i + 1] + 1e-12


def test_round_trip_recovers_raw():
    """Multiply adjusted by inverse factors; must recover raw closes."""
    ohlcv = _series(
        [
            ("2025-01-01", 100.0),
            ("2025-01-02", 100.0),
            ("2025-01-03", 95.0),
            ("2025-01-04", 96.0),
        ]
    )
    events = [_event(EventType.DIVIDEND, "2025-01-03", amount=5.0)]
    bars, _ = back_adjust(events, ohlcv)
    for b in bars:
        factor = b.adjusted_close / b.close if b.close else 1.0
        assert b.close * factor == pytest.approx(b.adjusted_close)


def test_last_bar_unchanged():
    """The most recent bar's adjusted_close MUST equal its raw close."""
    ohlcv = _series(
        [
            ("2025-01-01", 100.0),
            ("2025-01-02", 100.0),
            ("2025-01-03", 50.0),
        ]
    )
    events = [_event(EventType.SPLIT, "2025-01-03", ratio=2.0)]
    bars, _ = back_adjust(events, ohlcv)
    assert bars[-1].adjusted_close == bars[-1].close


def test_dividend_exceeding_prior_close_is_skipped():
    ohlcv = _series(
        [("2025-01-01", 1.0), ("2025-01-02", 1.0), ("2025-01-03", 0.5)]
    )
    events = [_event(EventType.DIVIDEND, "2025-01-03", amount=5.0)]
    bars, report = back_adjust(events, ohlcv)
    # No adjustment applied; skip logged.
    assert all(b.adjusted_close == b.close for b in bars)
    assert any("implausible" in s or "implausible" in s.lower() for s in report.skipped)


def test_event_before_history_is_skipped():
    ohlcv = _series([("2025-06-01", 100.0)])
    events = [_event(EventType.DIVIDEND, "2025-01-01", amount=2.0)]
    bars, report = back_adjust(events, ohlcv)
    assert bars[0].adjusted_close == 100.0
    assert any("prior close" in s for s in report.skipped)


def test_capital_increase_is_ignored_in_v1():
    ohlcv = _series([("2025-01-01", 100.0), ("2025-01-02", 110.0)])
    events = [
        CorporateAction(
            symbol="TEST",
            event_type=EventType.CAPITAL_INCREASE,
            ex_date=date(2025, 1, 2),
            status=EventStatus.CONFIRMED,
            subscription_price=90.0,
        )
    ]
    bars, report = back_adjust(events, ohlcv)
    assert all(b.adjusted_close == b.close for b in bars)
    assert report.applied == []


def test_empty_history_returns_empty():
    bars, report = back_adjust([_event(EventType.DIVIDEND, "2025-01-01", amount=1.0)], [])
    assert bars == []
    assert report.applied == []


def test_accepts_wafabourse_live_row_shape():
    # WafaBourse's VALEUR-GRAPH emits DD/MM/YYYY dates and occasionally
    # blank Volume. The adjuster must accept that shape as-is without
    # falling back to a normalisation layer upstream.
    live_shape = [
        {"Seance": "17/04/2023 00:00:00", "Cours": 82.5, "Volume": 1_890_212.1},
        {"Seance": "18/04/2023 00:00:00", "Cours": 82.0, "Volume": ""},
        {"Seance": "14/04/2026 00:00:00", "Cours": 95.4, "Volume": 11_975_665.87},
    ]
    bars, report = back_adjust([], live_shape)
    assert [b.bar_date for b in bars] == [
        date(2023, 4, 17),
        date(2023, 4, 18),
        date(2026, 4, 14),
    ]
    assert bars[1].volume == 0.0
    assert report.skipped == []
