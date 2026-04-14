import json

from ._context import ToolContext
from ._registry import tool


@tool(
    name="get_market_overview",
    description="Get overall market status, MASI index, top gainers/losers, and market breadth. Use this first to understand market conditions.",
    parameters={"type": "object", "properties": {}, "required": []},
)
def handle(ctx: ToolContext, args: dict) -> str:
    index = ctx.provider.get_market_index()
    gainers = ctx.provider.get_top_movers('H')
    losers = ctx.provider.get_top_movers('B')
    active = ctx.provider.get_top_movers('V')
    status = ctx.provider.get_market_status()

    return json.dumps({
        "market_status": status.get('Statut') if status else 'Unknown',
        "masi_index": {
            "value": index['Cours'],
            "change_pct": index['VariationP'],
            "volume_mad": index['Volume'] / 1e6,
            "gainers": index['NbrHausse'],
            "losers": index['NbrBaisse']
        } if index else None,
        "top_gainers": [{"symbol": s['Symbol'], "price": s['Cours'], "change": s['Variation']} for s in (gainers or [])[:3]],
        "top_losers": [{"symbol": s['Symbol'], "price": s['Cours'], "change": s['Variation']} for s in (losers or [])[:3]],
        "most_active": [{"symbol": s['Symbol'], "volume": s['Qte']} for s in (active or [])[:3]]
    }, indent=2)
