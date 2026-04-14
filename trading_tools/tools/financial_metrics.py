import json

from ._context import ToolContext
from ._registry import tool


@tool(
    name="get_financial_metrics",
    description="Get key financial metrics and ratios including P/E ratio, dividend yield, P/B ratio, EPS, DPS, margins, revenue, and net income for the last 2 years. Essential for fundamental valuation.",
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
    metrics = ctx.provider.get_financial_metrics(symbol)

    if not metrics:
        return f"Error: Could not fetch financial metrics for {symbol}"

    valuation = {}
    per_share = {}
    margins = {}
    income_statement = {}

    for metric in metrics:
        label = metric.get('Libelle', '')
        group = metric.get('IdGroupe', 0)

        years = [k for k in metric.keys() if k.isdigit()]
        values = {year: metric.get(year) for year in years}

        if group == 1:
            if 'earning' in label.lower() or 'P/E' in label:
                valuation['pe_ratio'] = values
            elif 'yield' in label.lower():
                valuation['dividend_yield_pct'] = values
            elif 'book' in label.lower():
                valuation['price_to_book'] = values
        elif group == 2:
            if 'bénéfice' in label.lower() or 'eps' in label.lower():
                per_share['earnings_per_share_dh'] = values
            elif 'dividende' in label.lower():
                per_share['dividend_per_share_dh'] = values
            elif 'actif' in label.lower():
                per_share['book_value_per_share_dh'] = values
        elif group == 3:
            if 'opérationnelle' in label.lower():
                margins['operating_margin_pct'] = values
            elif 'nette' in label.lower():
                margins['net_margin_pct'] = values
        elif group == 4:
            if 'chiffre' in label.lower() or 'affaires' in label.lower():
                income_statement['revenue_mdh'] = values
            elif 'exploitation' in label.lower():
                income_statement['operating_income_mdh'] = values
            elif 'net' in label.lower():
                income_statement['net_income_mdh'] = values

    return json.dumps({
        "symbol": symbol,
        "valuation_ratios": valuation,
        "per_share_metrics": per_share,
        "profitability_margins": margins,
        "income_statement": income_statement,
        "raw_data": [{"label": m.get('Libelle'), **{k: m.get(k) for k in m.keys() if k.isdigit()}} for m in metrics]
    }, indent=2)
