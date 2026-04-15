import json

from ._context import ToolContext
from ._registry import tool


@tool(
    name="get_recent_trades",
    description="Get the most recent executed trades for a stock showing time, price, quantity and trade direction. Essential for understanding real-time price action and detecting large trades.",
    parameters={
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Stock symbol (e.g., 'BCP', 'IAM', 'ATW')"},
            "limit": {"type": "integer", "description": "Maximum number of trades to return (default 20)"},
        },
        "required": ["symbol"],
    },
)
def handle(ctx: ToolContext, args: dict) -> str:
    symbol = args['symbol']
    limit = args.get('limit', 20)

    trades = ctx.provider.get_recent_trades(symbol)

    if not trades:
        return f"Error: Could not fetch recent trades for {symbol}"

    trades = trades[:limit]

    # WafaBourse VALEUR-TRANSACTION returns trades newest-first with no
    # aggressor flag. We apply the Lee-Ready tick rule on a time-ordered
    # series (oldest → newest): uptick = BUY, downtick = SELL, zero-tick
    # inherits the previous classification. Unclassifiable leading
    # zero-ticks are left as UNKNOWN and excluded from flow totals.
    ordered = list(reversed(trades))

    total_buy_volume = 0
    total_sell_volume = 0
    prices = []
    classifications: list[str] = []

    prev_price: float | None = None
    prev_direction: str | None = None
    for trade in ordered:
        price = trade.get('Prix', 0) or 0
        qty = trade.get('Qte', 0) or 0

        if prev_price is None or price > prev_price:
            direction = "BUY" if prev_price is not None else "UNKNOWN"
        elif price < prev_price:
            direction = "SELL"
        else:
            direction = prev_direction or "UNKNOWN"

        if direction == "BUY":
            total_buy_volume += qty
        elif direction == "SELL":
            total_sell_volume += qty

        classifications.append(direction)
        prev_price = price
        if direction in ("BUY", "SELL"):
            prev_direction = direction

    formatted_trades = []
    for trade, direction in zip(trades, reversed(classifications)):
        price = trade.get('Prix', 0) or 0
        qty = trade.get('Qte', 0) or 0
        prices.append(price)
        formatted_trades.append({
            "time": trade.get('Heure', ''),
            "price": price,
            "quantity": qty,
            "direction": direction,
            "value_mad": round(price * qty, 2),
        })

    total_volume = total_buy_volume + total_sell_volume
    buy_pct = (total_buy_volume / total_volume * 100) if total_volume > 0 else 0

    return json.dumps({
        "symbol": symbol,
        "num_trades": len(formatted_trades),
        "trades": formatted_trades,
        "trade_flow_analysis": {
            "total_buy_volume": total_buy_volume,
            "total_sell_volume": total_sell_volume,
            "buy_percentage": round(buy_pct, 2),
            "sell_percentage": round(100 - buy_pct, 2),
            "net_flow": "BUYING_PRESSURE" if buy_pct > 55 else "SELLING_PRESSURE" if buy_pct < 45 else "NEUTRAL"
        },
        "price_range": {
            "high": max(prices) if prices else 0,
            "low": min(prices) if prices else 0,
            "last": prices[0] if prices else 0
        }
    }, indent=2)
