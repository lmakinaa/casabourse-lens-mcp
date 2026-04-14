import json

from ._context import ToolContext
from ._registry import tool


@tool(
    name="get_intraday_momentum",
    description="Analyze intraday momentum by examining price relative to open, high, low, VWAP proximity, and buying/selling pressure. Key for timing entries during the trading day.",
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

    details = ctx.provider.get_stock_details(symbol)
    order_book = ctx.provider.get_order_book(symbol, 5)

    if not details:
        return f"Error: Could not fetch data for {symbol}"

    current = details.get('Cours', 0)
    open_price = details.get('Ouverture', 0)
    high = details.get('PlusHaut', 0)
    low = details.get('PlusBas', 0)
    buy_pressure = details.get('PourcentageAchat', 0)
    sell_pressure = details.get('PourcentageVente', 0)

    day_range = high - low
    if day_range > 0:
        position_in_range = (current - low) / day_range * 100
    else:
        position_in_range = 50

    if open_price > 0:
        change_from_open = (current - open_price) / open_price * 100
    else:
        change_from_open = 0

    if order_book:
        total_bid = sum(level.get('QteAchat', 0) for level in order_book)
        total_ask = sum(level.get('QteVente', 0) for level in order_book)
        if total_bid + total_ask > 0:
            book_imbalance = (total_bid - total_ask) / (total_bid + total_ask) * 100
        else:
            book_imbalance = 0
    else:
        book_imbalance = 0
        total_bid = total_ask = 0

    momentum_signals = []

    if position_in_range > 80:
        momentum_signals.append("NEAR_HIGH")
    elif position_in_range < 20:
        momentum_signals.append("NEAR_LOW")

    if change_from_open > 1:
        momentum_signals.append("BULLISH_TREND")
    elif change_from_open < -1:
        momentum_signals.append("BEARISH_TREND")

    if book_imbalance > 20:
        momentum_signals.append("BID_SUPPORT")
    elif book_imbalance < -20:
        momentum_signals.append("ASK_PRESSURE")

    bullish_count = sum(1 for s in momentum_signals if s in ['NEAR_HIGH', 'BULLISH_TREND', 'BID_SUPPORT'])
    bearish_count = sum(1 for s in momentum_signals if s in ['NEAR_LOW', 'BEARISH_TREND', 'ASK_PRESSURE'])

    if bullish_count > bearish_count:
        overall = "BULLISH"
    elif bearish_count > bullish_count:
        overall = "BEARISH"
    else:
        overall = "NEUTRAL"

    return json.dumps({
        "symbol": symbol,
        "price_action": {
            "current": current,
            "open": open_price,
            "high": high,
            "low": low,
            "change_from_open_pct": round(change_from_open, 2),
            "position_in_day_range_pct": round(position_in_range, 1)
        },
        "pressure_analysis": {
            "buy_pressure_pct": buy_pressure,
            "sell_pressure_pct": sell_pressure,
            "order_book_imbalance_pct": round(book_imbalance, 1),
            "bid_volume": total_bid,
            "ask_volume": total_ask
        },
        "momentum_signals": momentum_signals,
        "overall_momentum": overall,
        "interpretation": f"{'Buyers in control' if overall == 'BULLISH' else 'Sellers in control' if overall == 'BEARISH' else 'Balanced'} - price at {position_in_range:.0f}% of day range"
    }, indent=2)
