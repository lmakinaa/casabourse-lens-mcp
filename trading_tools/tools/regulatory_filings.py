import json

from ._context import ToolContext
from ._registry import tool

# NOTE: AMMC tools temporarily disabled — comment out decorator so discovery
# does not register them. To re-enable, restore the `@tool(...)` decorator.
# @tool(
#     name="get_regulatory_filings",
#     description=(
#         "Get recent AMMC regulatory notices for a ticker (OPA/OPR/OPE, profit warnings, "
#         "and material disclosures). Returns normalized filing type, publication date, source links, "
#         "and coverage warnings."
#     ),
#     parameters={
#         "type": "object",
#         "properties": {
#             "symbol": {"type": "string", "description": "Casablanca ticker symbol"},
#             "lookback_days": {
#                 "type": "integer",
#                 "description": "How far back to scan AMMC pages (default 365, capped at 730)",
#             },
#             "limit": {
#                 "type": "integer",
#                 "description": "Maximum number of filings to return (default 20, capped at 100)",
#             },
#         },
#         "required": ["symbol"],
#     },
# )
def handle(ctx: ToolContext, args: dict) -> str:
    # Tool disabled per user request — return a clear disabled payload.
    return json.dumps(
        {
            "error": "ammc_tool_disabled",
            "message": "AMMC regulatory filings tool has been disabled by user request",
        },
        indent=2,
    )
