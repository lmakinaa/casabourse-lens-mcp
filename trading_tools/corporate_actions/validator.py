"""
Sanity checks applied before an observation is written to the log.

A validation failure does NOT block writing — it downgrades the
observation's effective confidence and tags it for human review.
The rule: raw sources can lie; the pipeline must not accept lies
silently, but it also must not lose them.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import List

from .events import CandidateObservation, EventType


class ValidationError(ValueError):
    """Raised when an observation fails a hard sanity check."""


# Hard bounds chosen to catch clearly broken data (typos, parse errors),
# not to second-guess issuers. An issuer CAN legitimately pay 0.01 MAD
# or 500 MAD per share — these limits just reject negative/nonsensical.
_DIVIDEND_MIN = 0.0            # exclusive
_DIVIDEND_MAX = 10_000.0       # per share, MAD. Protects against decimal-point slips.
_SPLIT_RATIO_MIN = 0.01        # reverse splits: 1:100 → 0.01
_SPLIT_RATIO_MAX = 100.0       # 100:1 forward split
_EX_DATE_FLOOR = date(1990, 1, 1)
_EX_DATE_CEIL_SLACK = timedelta(days=365 * 2)  # events more than 2y in the future are suspicious


def validate_observation(obs: CandidateObservation, today: date) -> List[str]:
    """
    Return a list of warnings. Empty list == clean.

    Raises ValidationError for hard failures (malformed payload,
    negative ratios, etc.) that must not enter the store even as a
    pending observation — those are bugs upstream, not disputed data.
    """
    warnings: List[str] = []

    if not obs.symbol or not obs.symbol.strip():
        raise ValidationError("empty symbol")
    if obs.symbol != obs.symbol.strip().upper():
        raise ValidationError(f"symbol must be uppercase+trimmed, got {obs.symbol!r}")

    if obs.ex_date < _EX_DATE_FLOOR:
        raise ValidationError(f"ex_date {obs.ex_date} before {_EX_DATE_FLOOR}")
    if obs.ex_date > today + _EX_DATE_CEIL_SLACK:
        warnings.append(f"ex_date {obs.ex_date} is more than 2 years in the future")

    if obs.event_type is EventType.DIVIDEND:
        amount = obs.payload.get("amount")
        if amount is None:
            raise ValidationError("dividend observation missing 'amount'")
        if not isinstance(amount, (int, float)):
            raise ValidationError(f"dividend amount must be numeric, got {type(amount).__name__}")
        if amount <= _DIVIDEND_MIN:
            raise ValidationError(f"dividend amount must be > 0, got {amount}")
        if amount > _DIVIDEND_MAX:
            warnings.append(f"dividend amount {amount} is unusually large — check decimal point")

    elif obs.event_type is EventType.SPLIT:
        ratio = obs.payload.get("ratio")
        if ratio is None:
            raise ValidationError("split observation missing 'ratio'")
        if not isinstance(ratio, (int, float)):
            raise ValidationError(f"split ratio must be numeric, got {type(ratio).__name__}")
        if ratio <= 0:
            raise ValidationError(f"split ratio must be positive, got {ratio}")
        if not (_SPLIT_RATIO_MIN <= ratio <= _SPLIT_RATIO_MAX):
            warnings.append(f"split ratio {ratio} outside [0.01, 100] — review")
        if ratio == 1.0:
            raise ValidationError("split ratio of 1.0 is a no-op")

    elif obs.event_type in (EventType.CAPITAL_INCREASE, EventType.RIGHTS_ISSUE):
        # These are not fully modelled in v1 — store them but flag.
        warnings.append(f"{obs.event_type.value} not adjusted by v1 back_adjust — manual review required")

    return warnings
