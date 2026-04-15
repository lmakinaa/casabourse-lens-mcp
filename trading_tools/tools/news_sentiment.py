import json

from ._context import ToolContext
from ._registry import tool


@tool(
    name="get_news_sentiment",
    description=(
        "Compute a rolling ticker sentiment snapshot from recent news mentions, "
        "including mention-volume delta versus a 7-day baseline."
    ),
    parameters={
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Casablanca ticker symbol"},
            "window_days": {
                "type": "integer",
                "description": "Current observation window in days (default 7, max 30)",
            },
        },
        "required": ["symbol"],
    },
)
def handle(ctx: ToolContext, args: dict) -> str:
    symbol = str(args.get("symbol", "")).strip().upper()
    if not symbol:
        return "Error: symbol is required"

    window_days = int(args.get("window_days", 7))

    raw = ctx.provider.get_news_sentiment(symbol, window_days=window_days)
    if not raw:
        return f"Error: Could not fetch news sentiment for {symbol}"

    return json.dumps(
        {
            "symbol": raw.get("symbol", symbol),
            "window_days": raw.get("window_days", window_days),
            "as_of": raw.get("as_of"),
            "source": raw.get("source") or getattr(ctx.provider, "name", "unknown"),
            "mentions_current": raw.get("mentions_current", 0),
            "mentions_baseline_avg": raw.get("mentions_baseline_avg", 0.0),
            "mention_volume_delta_pct": raw.get("mention_volume_delta_pct"),
            "sentiment_score": raw.get("sentiment_score", 0.0),
            "sentiment_label": raw.get("sentiment_label", "neutral"),
            "sample_size": raw.get("sample_size", 0),
            "sources_covered": raw.get("sources_covered") or [],
            "warnings": raw.get("warnings") or [],
        },
        indent=2,
    )
