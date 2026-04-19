"""MCP tools for the MASI Trading Simulator.

Each tool is registered via the same `@tool` decorator used by read-only
Casabourse Lens tools (`trading_tools/tools/_registry.py`). The handler
signature is `(ctx, args) -> str`; `ctx` is ignored here because trading
state comes from the captured `PlaygroundClient`, not from the shared
ToolContext.

Design notes:
- Every tool returns a JSON string — consistent with the existing tool surface.
- Errors from the playground (rejected orders, market closed, insufficient
  funds) surface as `{"error": "..."}` rather than raised exceptions, so the
  MCP client sees a structured response instead of a tool-execution failure.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from ..tools._context import ToolContext
from ..tools._registry import tool
from .client import PlaygroundClient, PlaygroundError


def _err(exc: Exception) -> str:
    if isinstance(exc, PlaygroundError):
        return json.dumps({"error": exc.detail, "status_code": exc.status_code})
    return json.dumps({"error": str(exc)})


def register(client: PlaygroundClient) -> int:
    """Declare tools against the shared registry; return count registered."""

    # ── read: identity ────────────────────────────────────────────────────

    @tool(
        name="playground_whoami",
        description=(
            "Return the identity of the account the playground API key belongs "
            "to: username, cash balance, account id. Use this when you need to "
            "confirm which simulator account you are trading as."
        ),
        parameters={"type": "object", "properties": {}},
    )
    def _whoami(_ctx: ToolContext, _args: Dict[str, Any]) -> str:
        try:
            return json.dumps(client.me(), indent=2)
        except Exception as e:
            return _err(e)

    # ── read: portfolio ───────────────────────────────────────────────────

    @tool(
        name="playground_get_portfolio",
        description=(
            "Return the current portfolio snapshot: cash, holdings (with "
            "quantity, avg cost, current price, unrealized P&L), total value, "
            "and aggregate P&L in MAD and %."
        ),
        parameters={"type": "object", "properties": {}},
    )
    def _portfolio(_ctx: ToolContext, _args: Dict[str, Any]) -> str:
        try:
            return json.dumps(client.portfolio(), indent=2, default=str)
        except Exception as e:
            return _err(e)

    @tool(
        name="playground_get_trade_history",
        description=(
            "Return the user's executed trades, most recent first. Useful for "
            "explaining realized P&L or computing performance stats."
        ),
        parameters={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Max rows (1-500).",
                    "minimum": 1,
                    "maximum": 500,
                    "default": 50,
                }
            },
        },
    )
    def _trades(_ctx: ToolContext, args: Dict[str, Any]) -> str:
        try:
            return json.dumps(
                client.trade_history(limit=int(args.get("limit", 50))),
                indent=2,
                default=str,
            )
        except Exception as e:
            return _err(e)

    # ── read: orders ──────────────────────────────────────────────────────

    @tool(
        name="playground_list_orders",
        description=(
            "List the user's orders. Optional filters: status "
            "(PENDING|FILLED|CANCELLED|REJECTED|PARTIALLY_FILLED), symbol, and "
            "limit. Rejected orders are NOT stored — they only appear if your "
            "client created them before the no-record policy."
        ),
        parameters={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "symbol": {"type": "string"},
                "limit": {"type": "integer", "default": 50, "minimum": 1, "maximum": 500},
            },
        },
    )
    def _list(_ctx: ToolContext, args: Dict[str, Any]) -> str:
        try:
            return json.dumps(
                client.list_orders(
                    status=args.get("status"),
                    symbol=args.get("symbol"),
                    limit=int(args.get("limit", 50)),
                ),
                indent=2,
                default=str,
            )
        except Exception as e:
            return _err(e)

    @tool(
        name="playground_get_order",
        description="Fetch a single order by id.",
        parameters={
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
    )
    def _get(_ctx: ToolContext, args: Dict[str, Any]) -> str:
        try:
            return json.dumps(client.get_order(args["order_id"]), indent=2, default=str)
        except Exception as e:
            return _err(e)

    # ── write: place / cancel ─────────────────────────────────────────────

    @tool(
        name="playground_place_order",
        description=(
            "Place a BUY or SELL order in the simulator. "
            "`order_type=MARKET` fills at the current best price; "
            "`order_type=LIMIT` requires `limit_price` and rests until the "
            "market crosses it. Rejections (market closed, insufficient funds/"
            "holdings) return an `error` field and are NOT recorded."
        ),
        parameters={
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Casablanca ticker, e.g. IAM, ATW, BCP.",
                },
                "side": {"type": "string", "enum": ["BUY", "SELL"]},
                "order_type": {
                    "type": "string",
                    "enum": ["MARKET", "LIMIT"],
                    "default": "MARKET",
                },
                "quantity": {"type": "integer", "minimum": 1},
                "limit_price": {
                    "type": "number",
                    "description": "Required when order_type=LIMIT. Omit for MARKET.",
                },
            },
            "required": ["symbol", "side", "quantity"],
        },
    )
    def _place(_ctx: ToolContext, args: Dict[str, Any]) -> str:
        order_type = (args.get("order_type") or "MARKET").upper()
        limit_price: Optional[float] = None
        if order_type == "LIMIT":
            if "limit_price" not in args or args["limit_price"] is None:
                return json.dumps({"error": "limit_price is required for LIMIT orders"})
            limit_price = float(args["limit_price"])
        try:
            return json.dumps(
                client.place_order(
                    symbol=args["symbol"],
                    side=args["side"],
                    quantity=int(args["quantity"]),
                    limit_price=limit_price,
                ),
                indent=2,
                default=str,
            )
        except Exception as e:
            return _err(e)

    @tool(
        name="playground_cancel_order",
        description="Cancel a PENDING limit order by id. No-ops on terminal orders.",
        parameters={
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
    )
    def _cancel(_ctx: ToolContext, args: Dict[str, Any]) -> str:
        try:
            return json.dumps(
                client.cancel_order(args["order_id"]), indent=2, default=str
            )
        except Exception as e:
            return _err(e)

    # ── read: leaderboard ─────────────────────────────────────────────────

    @tool(
        name="playground_get_leaderboard",
        description="Return today's simulator leaderboard (top traders by portfolio value).",
        parameters={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100}
            },
        },
    )
    def _leaderboard(_ctx: ToolContext, args: Dict[str, Any]) -> str:
        try:
            return json.dumps(
                client.leaderboard(limit=int(args.get("limit", 20))),
                indent=2,
                default=str,
            )
        except Exception as e:
            return _err(e)

    return 8
