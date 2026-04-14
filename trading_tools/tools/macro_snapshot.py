import json
from datetime import date

from ._context import ToolContext
from ._registry import tool


@tool(
    name="get_macro_snapshot",
    description=(
        "Get a Morocco macro context snapshot including policy rate, T-bill yields, "
        "CPI YoY, MASI dividend yield, and equity risk premium proxy. "
        "Returns warnings when some fields are unavailable."
    ),
    parameters={"type": "object", "properties": {}, "required": []},
)
def handle(ctx: ToolContext, args: dict) -> str:
    raw = ctx.provider.get_macro_snapshot()
    if not raw:
        return "Error: Could not fetch macro snapshot"

    warnings = list(raw.get("warnings") or [])

    policy_rate = raw.get("policy_rate_pct")
    t13 = raw.get("t_bill_13w_pct")
    t52 = raw.get("t_bill_52w_pct")
    cpi = raw.get("cpi_yoy_pct")
    dy = raw.get("masi_dividend_yield_pct")
    erp = raw.get("equity_risk_premium_pct")

    if erp is None and dy is not None and t52 is not None:
        erp = round(float(dy) - float(t52), 4)

    as_of = raw.get("as_of") or date.today().isoformat()

    missing = [
        key
        for key, value in {
            "policy_rate_pct": policy_rate,
            "t_bill_13w_pct": t13,
            "t_bill_52w_pct": t52,
            "cpi_yoy_pct": cpi,
            "masi_dividend_yield_pct": dy,
            "equity_risk_premium_pct": erp,
        }.items()
        if value is None
    ]
    if missing:
        warnings.append(f"missing_fields: {', '.join(missing)}")

    return json.dumps(
        {
            "as_of": as_of,
            "source": raw.get("source") or getattr(ctx.provider, "name", "unknown"),
            "policy_rate_pct": policy_rate,
            "t_bill_13w_pct": t13,
            "t_bill_52w_pct": t52,
            "cpi_yoy_pct": cpi,
            "masi_dividend_yield_pct": dy,
            "equity_risk_premium_pct": erp,
            "warnings": warnings,
        },
        indent=2,
    )
