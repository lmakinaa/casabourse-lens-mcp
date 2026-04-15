import json

from ._context import ToolContext
from ._registry import tool


@tool(
    name="get_earnings_calendar",
    description=(
        "Get the next known AMMC earnings/publication calendar entry for a ticker. "
        "Returns the next event date, the publication title, and warnings when the issuer mapping is incomplete."
    ),
    parameters={
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Casablanca ticker symbol"},
            "lookahead_days": {
                "type": "integer",
                "description": "How far ahead to search AMMC listings (default 365, capped at 730)",
            },
        },
        "required": ["symbol"],
    },
)
def handle(ctx: ToolContext, args: dict) -> str:
    symbol = str(args.get("symbol", "")).strip().upper()
    if not symbol:
        return "Error: symbol is required"

    lookahead_days = int(args.get("lookahead_days", 365))
    raw = ctx.provider.get_earnings_calendar(symbol, lookahead_days=lookahead_days)
    if not raw:
        return f"Error: Could not fetch earnings calendar for {symbol}"

    return json.dumps(
        {
            "symbol": raw.get("symbol", symbol),
            "as_of": raw.get("as_of"),
            "source": raw.get("source") or getattr(ctx.provider, "name", "unknown"),
            "lookahead_days": raw.get("lookahead_days", lookahead_days),
            "next_event_date": raw.get("next_event_date"),
            "next_event_kind": raw.get("next_event_kind"),
            "next_event_title": raw.get("next_event_title"),
            "coverage": raw.get("coverage") or {},
            "warnings": raw.get("warnings") or [],
            "events": raw.get("events") or [],
        },
        indent=2,
    )
