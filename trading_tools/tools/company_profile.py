import json

from ._context import ToolContext
from ._registry import tool


@tool(
    name="get_company_profile",
    description="Get detailed company profile including description, sector, IPO date, number of shares, market cap, and website. Useful for fundamental analysis and understanding what a company does.",
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
    profile = ctx.provider.get_company_profile(symbol)

    if not profile:
        return f"Error: Could not fetch company profile for {symbol}"

    presentation = profile.get('Presentation', '')
    presentation = presentation.replace('$$', '\n').replace('||', '\n\nNote: ')

    return json.dumps({
        "symbol": profile.get('Symbol'),
        "name": profile.get('Libelle'),
        "isin": profile.get('Ising'),
        "sector": profile.get('Secteur'),
        "description": presentation,
        "ipo_date": profile.get('DateIntroduction', '').split(' ')[0] if profile.get('DateIntroduction') else None,
        "total_shares": profile.get('NbrTitres'),
        "market_cap_mad": profile.get('Capitalisation'),
        "market_cap_million_mad": profile.get('Capitalisation', 0) / 1e6 if profile.get('Capitalisation') else 0,
        "website": profile.get('SiteInternet', '').strip()
    }, indent=2)
