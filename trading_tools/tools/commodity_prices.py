import json
from datetime import date

from ._context import ToolContext
from ._registry import tool


@tool(
    name="get_commodity_prices",
    description=(
        "Get phosphate rock, Brent crude, and gold prices in USD with 30-day percentage changes."
    ),
    parameters={"type": "object", "properties": {}, "required": []},
)
def handle(ctx: ToolContext, args: dict) -> str:
    raw = ctx.provider.get_commodity_prices()
    if not raw:
        return "Error: Could not fetch commodity prices"

    warnings = list(raw.get("warnings") or [])

    brent = raw.get("brent_usd_per_bbl")
    gold = raw.get("gold_usd_per_oz")
    phosphate = raw.get("phosphate_usd_per_mt")

    missing = [
        key
        for key, value in {
            "brent_usd_per_bbl": brent,
            "gold_usd_per_oz": gold,
            "phosphate_usd_per_mt": phosphate,
            "brent_30d_change_pct": raw.get("brent_30d_change_pct"),
            "gold_30d_change_pct": raw.get("gold_30d_change_pct"),
            "phosphate_30d_change_pct": raw.get("phosphate_30d_change_pct"),
        }.items()
        if value is None
    ]
    if missing:
        warnings.append(f"missing_fields: {', '.join(missing)}")

    return json.dumps(
        {
            "as_of": raw.get("as_of") or date.today().isoformat(),
            "source": raw.get("source") or getattr(ctx.provider, "name", "unknown"),
            "brent_usd_per_bbl": brent,
            "brent_30d_change_pct": raw.get("brent_30d_change_pct"),
            "gold_usd_per_oz": gold,
            "gold_30d_change_pct": raw.get("gold_30d_change_pct"),
            "phosphate_usd_per_mt": phosphate,
            "phosphate_30d_change_pct": raw.get("phosphate_30d_change_pct"),
            "warnings": warnings,
        },
        indent=2,
    )
