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

    total_buy_volume = 0
    total_sell_volume = 0
    prices = []

    formatted_trades = []
    for trade in trades:
        price = trade.get('Cours', 0)
        qty = trade.get('Qte', 0)
        sens = trade.get('Sens', '')

        prices.append(price)

        if sens == 'A':
            total_buy_volume += qty
        elif sens == 'V':
            total_sell_volume += qty

        formatted_trades.append({
            "time": trade.get('Heure', ''),
            "price": price,
            "quantity": qty,
            "direction": "BUY" if sens == 'A' else "SELL" if sens == 'V' else "UNKNOWN",
            "value_mad": price * qty
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
