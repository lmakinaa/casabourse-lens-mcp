import json

from ._context import ToolContext
from ._registry import tool


@tool(
    name="get_news",
    description=(
        "Get recent ticker-linked Moroccan financial news items from configured RSS sources. "
        "Returns machine-readable article facts (title, URL, timestamp, source, mention symbols)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Casablanca ticker symbol"},
            "limit": {"type": "integer", "description": "Maximum number of articles to return (default 20)"},
            "days": {"type": "integer", "description": "Lookback window in days (default 7, max 30)"},
        },
        "required": ["symbol"],
    },
)
def handle(ctx: ToolContext, args: dict) -> str:
    symbol = str(args.get("symbol", "")).strip().upper()
    if not symbol:
        return "Error: symbol is required"

    limit = int(args.get("limit", 20))
    days = int(args.get("days", 7))

    raw = ctx.provider.get_news(symbol, limit=limit, days=days)
    if not raw:
        return f"Error: Could not fetch news for {symbol}"

    return json.dumps(
        {
            "symbol": raw.get("symbol", symbol),
            "window_days": raw.get("window_days", days),
            "as_of": raw.get("as_of"),
            "source": raw.get("source") or getattr(ctx.provider, "name", "unknown"),
            "sources_covered": raw.get("sources_covered") or [],
            "article_count": raw.get("article_count", 0),
            "warnings": raw.get("warnings") or [],
            "articles": raw.get("articles") or [],
        },
        indent=2,
    )
