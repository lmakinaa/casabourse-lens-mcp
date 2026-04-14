import json

from ._context import ToolContext
from ._registry import tool


@tool(
    name="get_technical_analysis",
    description="Calculate technical indicators (SMA, EMA, RSI, MACD, Bollinger Bands) for a stock. Requires historical data.",
    parameters={
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Stock symbol"},
            "indicators": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of indicators: 'sma20', 'sma50', 'ema12', 'rsi', 'macd', 'bollinger'",
            },
        },
        "required": ["symbol", "indicators"],
    },
)
def handle(ctx: ToolContext, args: dict) -> str:
    symbol = args['symbol']
    indicators = args.get('indicators', [])

    history = ctx.provider.get_price_history(symbol)
    if not history:
        return f"Error: No historical data for {symbol}"

    prices = [float(d['Cours']) for d in history[-50:]]
    current_price = prices[-1]

    results = {"symbol": symbol, "current_price": current_price}

    if 'sma20' in indicators:
        results['sma20'] = ctx.tech_analysis.calculate_sma(prices, 20)
    if 'sma50' in indicators:
        results['sma50'] = ctx.tech_analysis.calculate_sma(prices, 50)
    if 'ema12' in indicators:
        results['ema12'] = ctx.tech_analysis.calculate_ema(prices, 12)
    if 'rsi' in indicators:
        results['rsi'] = ctx.tech_analysis.calculate_rsi(prices, 14)
    if 'macd' in indicators:
        results['macd'] = ctx.tech_analysis.calculate_macd(prices)
    if 'bollinger' in indicators:
        results['bollinger_bands'] = ctx.tech_analysis.calculate_bollinger_bands(prices, 20)

    return json.dumps(results, indent=2)
