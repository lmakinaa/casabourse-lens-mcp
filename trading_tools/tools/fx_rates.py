import json
from datetime import date

from ._context import ToolContext
from ._registry import tool


@tool(
    name="get_fx_rates",
    description="Get EUR/MAD and USD/MAD spot rates with 20-day percentage change.",
    parameters={"type": "object", "properties": {}, "required": []},
)
def handle(ctx: ToolContext, args: dict) -> str:
    raw = ctx.provider.get_fx_rates()
    if not raw:
        return "Error: Could not fetch FX rates"

    warnings = list(raw.get("warnings") or [])

    usd_spot = raw.get("usd_mad_spot")
    eur_spot = raw.get("eur_mad_spot")
    usd_chg = raw.get("usd_mad_20d_change_pct")
    eur_chg = raw.get("eur_mad_20d_change_pct")

    missing = [
        key
        for key, value in {
            "usd_mad_spot": usd_spot,
            "eur_mad_spot": eur_spot,
            "usd_mad_20d_change_pct": usd_chg,
            "eur_mad_20d_change_pct": eur_chg,
        }.items()
        if value is None
    ]
    if missing:
        warnings.append(f"missing_fields: {', '.join(missing)}")

    return json.dumps(
        {
            "as_of": raw.get("as_of") or date.today().isoformat(),
            "source": raw.get("source") or getattr(ctx.provider, "name", "unknown"),
            "usd_mad_spot": usd_spot,
            "eur_mad_spot": eur_spot,
            "usd_mad_20d_change_pct": usd_chg,
            "eur_mad_20d_change_pct": eur_chg,
            "warnings": warnings,
        },
        indent=2,
    )
