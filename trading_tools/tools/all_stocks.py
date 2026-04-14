import json

from ._context import ToolContext
from ._registry import tool


@tool(
    name="get_all_stocks",
    description="Get complete list of all stocks trading on the exchange with current prices, changes, and volumes.",
    parameters={
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "description": "Maximum number of stocks to return (default: all)"}
        },
        "required": [],
    },
)
def handle(ctx: ToolContext, args: dict) -> str:
    limit = args.get('limit', None)
    all_tickers = ctx.provider.get_all_tickers()

    if not all_tickers:
        return "Error: Could not fetch all stocks"

    if limit:
        all_tickers = all_tickers[:limit]

    stocks = []
    for stock in all_tickers:
        stocks.append({
            "symbol": stock.get('Symbol', 'N/A'),
            "name": stock.get('Libelle', 'N/A'),
            "price": stock.get('Cours', 0),
            "change_pct": stock.get('VariationP', 0),
            "change_mad": stock.get('Variation', 0),
            "volume_mad": stock.get('Volume', 0) / 1e6 if stock.get('Volume') else 0,
            "high": stock.get('PlusHaut', 0),
            "low": stock.get('PlusBas', 0),
            "open": stock.get('Ouverture', 0)
        })

    return json.dumps({
        "total_stocks": len(stocks),
        "stocks": stocks
    }, indent=2)
