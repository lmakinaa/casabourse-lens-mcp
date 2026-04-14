import json

from ._context import ToolContext
from ._registry import tool


@tool(
    name="get_price_history",
    description="Get historical price data (daily OHLCV) for trend analysis and pattern recognition.",
    parameters={
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Stock symbol"},
            "days": {"type": "integer", "description": "Number of days of history (default 30)"},
        },
        "required": ["symbol"],
    },
)
def handle(ctx: ToolContext, args: dict) -> str:
    symbol = args['symbol']
    days = args.get('days', 30)

    history = ctx.provider.get_price_history(symbol)
    if not history:
        return f"Error: No history for {symbol}"

    recent = history[-days:]

    return json.dumps({
        "symbol": symbol,
        "days": len(recent),
        "data": [{"date": d['Seance'], "close": d['Cours'], "volume": d['Volume']} for d in recent]
    }, indent=2)
