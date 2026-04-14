import json

from ._context import ToolContext
from ._registry import tool


@tool(
    name="get_order_book",
    description="Get order book depth (bid/ask levels) to assess liquidity and buying/selling pressure.",
    parameters={
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Stock symbol"}
        },
        "required": ["symbol"],
    },
)
def handle(ctx: ToolContext, args: dict) -> str:
    symbol = args['symbol']
    order_book = ctx.provider.get_order_book(symbol, 5)

    if not order_book:
        return f"Error: No order book data for {symbol}"

    best_bid = order_book[0]['Achat']
    best_ask = order_book[0]['Vente']
    spread = best_ask - best_bid
    spread_pct = (spread / best_bid) * 100

    total_bid_vol = sum(level['QteAchat'] for level in order_book)
    total_ask_vol = sum(level['QteVente'] for level in order_book)
    imbalance = (total_bid_vol - total_ask_vol) / (total_bid_vol + total_ask_vol) * 100

    return json.dumps({
        "symbol": symbol,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread_mad": spread,
        "spread_pct": spread_pct,
        "order_imbalance_pct": imbalance,
        "total_bid_volume": total_bid_vol,
        "total_ask_volume": total_ask_vol,
        "bid_levels": [{"price": l['Achat'], "qty": l['QteAchat']} for l in order_book],
        "ask_levels": [{"price": l['Vente'], "qty": l['QteVente']} for l in order_book]
    }, indent=2)
