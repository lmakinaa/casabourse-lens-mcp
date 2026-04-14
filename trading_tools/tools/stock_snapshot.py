import json

from ._context import ToolContext
from ._registry import tool


@tool(
    name="get_stock_snapshot",
    description="Get current price, volume, and basic info for a specific stock symbol.",
    parameters={
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Stock symbol (e.g., 'BCP', 'IAM', 'ATW')"}
        },
        "required": ["symbol"],
    },
)
def handle(ctx: ToolContext, args: dict) -> str:
    symbol = args['symbol']
    details = ctx.provider.get_stock_details(symbol)

    if not details:
        return f"Error: Could not fetch data for {symbol}"

    return json.dumps({
        "symbol": symbol,
        "current_price": details['Cours'],
        "change_pct": details['VariationP'],
        "open": details['Ouverture'],
        "high": details['PlusHaut'],
        "low": details['PlusBas'],
        "volume_mad": details['Volume'] / 1e6,
        "num_trades": details['NbrTransaction'],
        "ytd_change": details['VariationPDAnnee'],
        "year_high": details['PlusHautDAnnee'],
        "year_low": details['PlusBasDAnnee'],
        "buy_pressure_pct": details['PourcentageAchat'],
        "sell_pressure_pct": details['PourcentageVente']
    }, indent=2)
