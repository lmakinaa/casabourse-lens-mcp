import json

from ._context import ToolContext
from ._registry import tool


@tool(
    name="screen_stocks",
    description="Screen stocks based on criteria like minimum volume, price change, and sector. Useful for finding trading opportunities and filtering the universe of stocks.",
    parameters={
        "type": "object",
        "properties": {
            "min_volume_mad": {"type": "number", "description": "Minimum trading volume in MAD (millions)"},
            "min_change_pct": {"type": "number", "description": "Minimum price change percentage"},
            "max_change_pct": {"type": "number", "description": "Maximum price change percentage"},
            "direction": {"type": "string", "description": "Filter by direction: 'up', 'down', or 'all'", "enum": ["up", "down", "all"]},
            "limit": {"type": "integer", "description": "Maximum number of results (default 10)"},
        },
        "required": [],
    },
)
def handle(ctx: ToolContext, args: dict) -> str:
    min_volume = args.get('min_volume_mad', 0) * 1e6
    min_change = args.get('min_change_pct')
    max_change = args.get('max_change_pct')
    direction = args.get('direction', 'all')
    limit = args.get('limit', 10)

    all_tickers = ctx.provider.get_all_tickers()

    if not all_tickers:
        return "Error: Could not fetch stocks for screening"

    filtered = []
    for stock in all_tickers:
        volume = stock.get('Volume', 0)
        change_pct = stock.get('VariationP', 0)

        if volume < min_volume:
            continue

        if min_change is not None and change_pct < min_change:
            continue
        if max_change is not None and change_pct > max_change:
            continue

        if direction == 'up' and change_pct <= 0:
            continue
        if direction == 'down' and change_pct >= 0:
            continue

        filtered.append({
            "symbol": stock.get('Symbol'),
            "name": stock.get('Libelle'),
            "price": stock.get('Cours', 0),
            "change_pct": change_pct,
            "volume_mad": volume / 1e6,
            "high": stock.get('PlusHaut', 0),
            "low": stock.get('PlusBas', 0)
        })

    filtered.sort(key=lambda x: abs(x['change_pct']), reverse=True)

    return json.dumps({
        "total_matches": len(filtered),
        "showing": min(limit, len(filtered)),
        "filters_applied": {
            "min_volume_mad": min_volume / 1e6 if min_volume else None,
            "min_change_pct": min_change,
            "max_change_pct": max_change,
            "direction": direction
        },
        "stocks": filtered[:limit]
    }, indent=2)
