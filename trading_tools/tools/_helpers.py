"""Shared helpers for tool handlers (parse dates, guard CA service)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from ._context import ToolContext


def require_ca_service(ctx: ToolContext) -> Optional[str]:
    if ctx.corporate_actions is None:
        return (
            "Error: corporate-action service not configured. "
            "Initialise server with a CorporateActionStore to enable this tool."
        )
    return None


def parse_as_of(raw: Optional[str]) -> Optional[datetime]:
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid as_of {raw!r}: {exc}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def parse_iso_date(raw: Optional[str]) -> Optional[date]:
    if not raw:
        return None
    return date.fromisoformat(raw[:10])
