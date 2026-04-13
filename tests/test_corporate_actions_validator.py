"""Hard-fail vs. warn behaviour of the observation validator."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

pytest.importorskip("trading_tools.corporate_actions")

from trading_tools.corporate_actions import (  # noqa: E402
    CandidateObservation,
    Confidence,
    EventType,
    ValidationError,
    validate_observation,
)

pytestmark = pytest.mark.v2_only

TODAY = date(2026, 4, 14)


def _obs(**overrides):
    defaults = {
        "symbol": "ATW",
        "event_type": EventType.DIVIDEND,
        "ex_date": date(2025, 5, 12),
        "payload": {"amount": 16.5},
        "source": "manual",
        "confidence": Confidence.MANUAL,
    }
    defaults.update(overrides)
    return CandidateObservation(**defaults)


def test_accepts_clean_dividend():
    assert validate_observation(_obs(), today=TODAY) == []


def test_rejects_empty_symbol():
    with pytest.raises(ValidationError, match="empty symbol"):
        validate_observation(_obs(symbol=""), today=TODAY)


def test_rejects_lowercase_symbol():
    with pytest.raises(ValidationError, match="uppercase"):
        validate_observation(_obs(symbol="atw"), today=TODAY)


def test_rejects_ancient_ex_date():
    with pytest.raises(ValidationError, match="before"):
        validate_observation(_obs(ex_date=date(1980, 1, 1)), today=TODAY)


def test_warns_on_far_future_ex_date():
    warnings = validate_observation(
        _obs(ex_date=TODAY + timedelta(days=365 * 3)), today=TODAY
    )
    assert any("future" in w for w in warnings)


def test_rejects_non_positive_dividend():
    with pytest.raises(ValidationError, match="> 0"):
        validate_observation(_obs(payload={"amount": 0}), today=TODAY)
    with pytest.raises(ValidationError, match="> 0"):
        validate_observation(_obs(payload={"amount": -1.0}), today=TODAY)


def test_rejects_non_numeric_dividend():
    with pytest.raises(ValidationError, match="numeric"):
        validate_observation(_obs(payload={"amount": "16.5"}), today=TODAY)


def test_warns_on_absurd_dividend():
    warnings = validate_observation(
        _obs(payload={"amount": 50_000.0}), today=TODAY
    )
    assert any("decimal" in w for w in warnings)


def test_rejects_split_of_one():
    with pytest.raises(ValidationError, match="no-op"):
        validate_observation(
            _obs(event_type=EventType.SPLIT, payload={"ratio": 1.0}),
            today=TODAY,
        )


def test_rejects_negative_split():
    with pytest.raises(ValidationError, match="positive"):
        validate_observation(
            _obs(event_type=EventType.SPLIT, payload={"ratio": -2.0}),
            today=TODAY,
        )


def test_capital_increase_warns_in_v1():
    warnings = validate_observation(
        _obs(
            event_type=EventType.CAPITAL_INCREASE,
            payload={"subscription_price": 100.0, "ratio": 0.1},
        ),
        today=TODAY,
    )
    assert any("manual review" in w for w in warnings)
