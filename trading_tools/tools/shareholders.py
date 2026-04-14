import json

from ._context import ToolContext
from ._registry import tool


@tool(
    name="get_shareholders",
    description="Get shareholder structure showing major shareholders and their ownership percentages. Important for understanding ownership concentration and float.",
    parameters={
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Stock symbol (e.g., 'ADH', 'BCP', 'IAM')"}
        },
        "required": ["symbol"],
    },
)
def handle(ctx: ToolContext, args: dict) -> str:
    symbol = args['symbol']
    shareholders = ctx.provider.get_shareholders(symbol)

    if not shareholders:
        return f"Error: Could not fetch shareholders for {symbol}"

    float_pct = 0
    major_holders = []

    for holder in shareholders:
        name = holder.get('Libelle', '').strip()
        pct = holder.get('Pourcentage', 0)

        if 'flottant' in name.lower() or 'float' in name.lower():
            float_pct = pct
        else:
            major_holders.append({
                "name": name,
                "percentage": pct
            })

    return json.dumps({
        "symbol": symbol,
        "shareholders": [{
            "name": h.get('Libelle', '').strip(),
            "percentage": h.get('Pourcentage', 0)
        } for h in shareholders],
        "major_holders": major_holders,
        "float_percentage": float_pct,
        "ownership_concentration": sum(h['percentage'] for h in major_holders)
    }, indent=2)
