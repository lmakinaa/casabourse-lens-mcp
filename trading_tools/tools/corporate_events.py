import json

from ..corporate_actions import EventType
from ._context import ToolContext
from ._helpers import parse_as_of, parse_iso_date, require_ca_service
from ._registry import tool


@tool(
    name="get_corporate_actions",
    description=(
        "Return dividend, split, capital-increase, and rights-issue events "
        "for a stock with full provenance (source, confidence, status). "
        "Supports point-in-time queries via `as_of` so backtests never see "
        "future-back-dated data. Always check the `warnings` and `coverage` "
        "fields before acting on the data."
    ),
    parameters={
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Stock symbol"},
            "from_date": {"type": "string", "description": "ISO date; include events with ex_date >= from_date"},
            "to_date": {"type": "string", "description": "ISO date; include events with ex_date <= to_date"},
            "as_of": {"type": "string", "description": "ISO datetime; only consider observations seen on/before this instant (point-in-time)"},
            "event_types": {
                "type": "array",
                "items": {"type": "string", "enum": ["dividend", "split", "capital_increase", "rights_issue"]},
                "description": "Filter to these event types; omit for all",
            },
            "include_pending": {"type": "boolean", "description": "Include pending_review and disputed events (default false)"},
        },
        "required": ["symbol"],
    },
)
def handle(ctx: ToolContext, args: dict) -> str:
    err = require_ca_service(ctx)
    if err:
        return err

    symbol = args["symbol"]
    try:
        from_date = parse_iso_date(args.get("from_date"))
        to_date = parse_iso_date(args.get("to_date"))
        as_of = parse_as_of(args.get("as_of"))
    except ValueError as exc:
        return f"Error: {exc}"

    event_types = None
    raw_types = args.get("event_types")
    if raw_types:
        try:
            event_types = [EventType(t) for t in raw_types]
        except ValueError as exc:
            return f"Error: invalid event_type — {exc}"

    include_pending = bool(args.get("include_pending", False))

    events, metadata = ctx.corporate_actions.get_events(
        symbol,
        from_date=from_date,
        to_date=to_date,
        event_types=event_types,
        as_of=as_of,
        include_pending=include_pending,
    )

    return json.dumps(
        {
            "symbol": metadata["symbol"],
            "as_of": metadata["as_of"],
            "coverage": metadata["coverage"],
            "warnings": metadata["warnings"],
            "event_count": metadata["event_count"],
            "events": [e.to_dict() for e in events],
        },
        indent=2,
    )
