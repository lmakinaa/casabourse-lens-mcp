import json

from ._context import ToolContext
from ._registry import tool


@tool(
    name="compare_stocks",
    description="Compare multiple stocks side by side on key metrics including price performance, volume, volatility, and technicals. Useful for relative value analysis and pair trading.",
    parameters={
        "type": "object",
        "properties": {
            "symbols": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of stock symbols to compare (2-5 stocks)",
            }
        },
        "required": ["symbols"],
    },
)
def handle(ctx: ToolContext, args: dict) -> str:
    symbols = args.get('symbols', [])

    if len(symbols) < 2:
        return "Error: Need at least 2 symbols to compare"
    if len(symbols) > 5:
        symbols = symbols[:5]

    comparisons = []

    for symbol in symbols:
        details = ctx.provider.get_stock_details(symbol)
        history = ctx.provider.get_price_history(symbol)

        if not details:
            comparisons.append({"symbol": symbol, "error": "Could not fetch data"})
            continue

        prices = [float(d['Cours']) for d in history[-30:]] if history else []
        rsi = ctx.tech_analysis.calculate_rsi(prices, 14) if len(prices) >= 15 else None
        sma20 = ctx.tech_analysis.calculate_sma(prices, 20) if len(prices) >= 20 else None

        current_price = details.get('Cours', 0)

        comparisons.append({
            "symbol": symbol,
            "name": details.get('Libelle', ''),
            "price": current_price,
            "change_today_pct": details.get('VariationP', 0),
            "ytd_change_pct": details.get('VariationPDAnnee', 0),
            "volume_mad": details.get('Volume', 0) / 1e6,
            "rsi_14": round(rsi, 2) if rsi else None,
            "vs_sma20_pct": round((current_price - sma20) / sma20 * 100, 2) if sma20 and current_price else None,
            "52w_high": details.get('PlusHautDAnnee', 0),
            "52w_low": details.get('PlusBasDAnnee', 0),
            "from_52w_high_pct": round((current_price - details.get('PlusHautDAnnee', current_price)) / details.get('PlusHautDAnnee', current_price) * 100, 2) if details.get('PlusHautDAnnee') else None
        })

    valid_comparisons = [c for c in comparisons if 'error' not in c]

    if valid_comparisons:
        best_today = max(valid_comparisons, key=lambda x: x.get('change_today_pct', -999))
        worst_today = min(valid_comparisons, key=lambda x: x.get('change_today_pct', 999))

        with_rsi = [c for c in valid_comparisons if c.get('rsi_14')]
        most_oversold = min(with_rsi, key=lambda x: x['rsi_14']) if with_rsi else None
        most_overbought = max(with_rsi, key=lambda x: x['rsi_14']) if with_rsi else None
    else:
        best_today = worst_today = most_oversold = most_overbought = None

    return json.dumps({
        "comparison": comparisons,
        "rankings": {
            "best_performer_today": best_today['symbol'] if best_today else None,
            "worst_performer_today": worst_today['symbol'] if worst_today else None,
            "most_oversold": most_oversold['symbol'] if most_oversold else None,
            "most_overbought": most_overbought['symbol'] if most_overbought else None
        }
    }, indent=2)
