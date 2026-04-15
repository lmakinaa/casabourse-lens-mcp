import json

from ._context import ToolContext
from ._registry import tool


@tool(
    name="get_regulatory_filings",
    description=(
        "Get recent AMMC regulatory notices for a ticker (OPA/OPR/OPE, profit warnings, "
        "and material disclosures). Returns normalized filing type, publication date, source links, "
        "and coverage warnings."
    ),
    parameters={
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Casablanca ticker symbol"},
            "lookback_days": {
                "type": "integer",
                "description": "How far back to scan AMMC pages (default 365, capped at 730)",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of filings to return (default 20, capped at 100)",
            },
        },
        "required": ["symbol"],
    },
)
def handle(ctx: ToolContext, args: dict) -> str:
    symbol = str(args.get("symbol", "")).strip().upper()
    if not symbol:
        return "Error: symbol is required"

    lookback_days = int(args.get("lookback_days", 365))
    limit = int(args.get("limit", 20))
    raw = ctx.provider.get_regulatory_filings(
        symbol,
        lookback_days=lookback_days,
        limit=limit,
    )
    if not raw:
        return f"Error: Could not fetch regulatory filings for {symbol}"

    return json.dumps(
        {
            "symbol": raw.get("symbol", symbol),
            "as_of": raw.get("as_of"),
            "source": raw.get("source") or getattr(ctx.provider, "name", "unknown"),
            "lookback_days": raw.get("lookback_days", lookback_days),
            "filing_count": raw.get("filing_count", 0),
            "latest_filing_date": raw.get("latest_filing_date"),
            "coverage": raw.get("coverage") or {},
            "warnings": raw.get("warnings") or [],
            "filings": raw.get("filings") or [],
        },
        indent=2,
    )
