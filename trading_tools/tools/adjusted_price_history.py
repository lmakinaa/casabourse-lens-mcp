import json

from ._context import ToolContext
from ._helpers import parse_as_of, require_ca_service
from ._registry import tool


@tool(
    name="get_adjusted_price_history",
    description=(
        "Return OHLCV history with prices and volumes back-adjusted for "
        "dividends and splits. Use this for ALL technical indicator inputs — "
        "RSI/MACD on unadjusted series across an ex-dividend date are false "
        "signals. Response includes the adjustment factors applied and any "
        "events that were skipped (missing data, etc.)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Stock symbol"},
            "days": {"type": "integer", "description": "Number of recent days to return (default 90)"},
            "as_of": {"type": "string", "description": "ISO datetime; apply only adjustments known on/before this instant"},
            "include_pending": {"type": "boolean", "description": "Apply pending_review events too (default false)"},
        },
        "required": ["symbol"],
    },
)
def handle(ctx: ToolContext, args: dict) -> str:
    err = require_ca_service(ctx)
    if err:
        return err

    symbol = args["symbol"]
    days = int(args.get("days", 90))
    try:
        as_of = parse_as_of(args.get("as_of"))
    except ValueError as exc:
        return f"Error: {exc}"
    include_pending = bool(args.get("include_pending", False))

    raw_history = ctx.provider.get_price_history(symbol)
    if not raw_history:
        return f"Error: No history for {symbol}"

    bars, report, metadata = ctx.corporate_actions.adjust_history(
        symbol,
        raw_history,
        as_of=as_of,
        include_pending=include_pending,
    )
    recent = bars[-days:] if days > 0 else bars

    return json.dumps(
        {
            "symbol": metadata["symbol"],
            "as_of": metadata["as_of"],
            "days": len(recent),
            "coverage": metadata["coverage"],
            "warnings": metadata["warnings"],
            "adjustments_applied": [
                {
                    "ex_date": a.ex_date.isoformat(),
                    "event_type": a.event_type,
                    "factor": round(a.factor, 8),
                    "note": a.note,
                }
                for a in report.applied
            ],
            "adjustments_skipped": report.skipped,
            "data": [b.to_dict() for b in recent],
        },
        indent=2,
    )
