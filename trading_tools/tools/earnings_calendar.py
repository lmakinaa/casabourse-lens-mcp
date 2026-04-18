import json

from ._context import ToolContext
from ._registry import tool

# NOTE: AMMC tools temporarily disabled — comment out decorator so discovery
# does not register them. To re-enable, restore the `@tool(...)` decorator.
# @tool(
#     name="get_earnings_calendar",
#     description=(
#         "Get the next known AMMC earnings/publication calendar entry for a ticker. "
#         "Returns the next event date, the publication title, and warnings when the issuer mapping is incomplete."
#     ),
#     parameters={
#         "type": "object",
#         "properties": {
#             "symbol": {"type": "string", "description": "Casablanca ticker symbol"},
#             "lookahead_days": {
#                 "type": "integer",
#                 "description": "How far ahead to search AMMC listings (default 365, capped at 730)",
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
            "message": "AMMC earnings calendar tool has been disabled by user request",
        },
        indent=2,
    )
