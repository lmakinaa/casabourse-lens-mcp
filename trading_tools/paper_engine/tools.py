"""MCP tools that expose the local paper-engine state.

Read-only: these tools never mutate the engine state. Trade placement,
fill simulation, and order management stay in the engine CLI
(/Users/ijaija/Documents/Claude/paper_engine/paper_engine.py).

Account directories are passed as absolute paths. Each directory
contains:
  paper_state.json   — cash, positions, orders, meta
  paper_trades.jsonl — append-only trade log
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from ..tools._context import ToolContext
from ..tools._registry import tool

STATE_FILE = "paper_state.json"
TRADES_FILE = "paper_trades.jsonl"


def _err(msg: str, status_code: int = 400) -> str:
    return json.dumps({"error": msg, "status_code": status_code})


def _read_state(account_dir: str) -> Dict[str, Any]:
    path = os.path.join(account_dir, STATE_FILE)
    if not os.path.exists(path):
        raise FileNotFoundError(f"state not found at {path}")
    with open(path, "r") as f:
        return json.load(f)


def _read_trades(account_dir: str, limit: int = 50) -> List[Dict[str, Any]]:
    path = os.path.join(account_dir, TRADES_FILE)
    if not os.path.exists(path):
        return []
    trades: List[Dict[str, Any]] = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                trades.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    trades.reverse()  # newest first
    return trades[:limit]


def register_paper_tools() -> int:
    """Declare paper-engine read tools against the shared registry; return count."""

    @tool(
        name="paper_portfolio",
        description=(
            "Return the local paper-engine account state for the given absolute "
            "directory. Mirrors the playground_get_portfolio shape: cash, "
            "holdings_value (computed from current price = avg_cost as fallback "
            "unless quotes are provided), total_value, pnl_mad, pnl_pct, "
            "positions[]. Also returns the orders dict for free. Read-only."
        ),
        parameters={
            "type": "object",
            "properties": {
                "account_dir": {
                    "type": "string",
                    "description": "Absolute path to the paper account directory (containing paper_state.json).",
                },
                "quotes_json": {
                    "type": "string",
                    "description": (
                        'Optional JSON map {"SYMBOL":{"bid":X,"ask":Y,"last":Z}} '
                        "for accurate mark-to-market. Omit to use avg_cost as proxy."
                    ),
                },
            },
            "required": ["account_dir"],
        },
    )
    def _portfolio(_ctx: ToolContext, args: Dict[str, Any]) -> str:
        account_dir = args.get("account_dir")
        if not account_dir:
            return _err("account_dir is required")
        try:
            state = _read_state(account_dir)
        except FileNotFoundError as e:
            return _err(str(e), 404)
        except Exception as e:
            return _err(f"read error: {e}", 500)

        quotes: Optional[Dict[str, Dict[str, float]]] = None
        if args.get("quotes_json"):
            try:
                quotes = json.loads(args["quotes_json"])
            except json.JSONDecodeError as e:
                return _err(f"invalid quotes_json: {e}")

        positions_out: List[Dict[str, Any]] = []
        holdings_value = 0.0
        for symbol, pos in (state.get("positions") or {}).items():
            qty = pos["qty"]
            avg_cost = pos["avg_cost"]
            if quotes and symbol in quotes:
                q = quotes[symbol]
                if q.get("last") is not None:
                    current_price = q["last"]
                elif q.get("bid") is not None and q.get("ask") is not None:
                    current_price = (q["bid"] + q["ask"]) / 2
                else:
                    current_price = avg_cost
            else:
                current_price = avg_cost
            market_value = qty * current_price
            unrealized_pnl = (current_price - avg_cost) * qty
            holdings_value += market_value
            positions_out.append({
                "symbol": symbol,
                "quantity": qty,
                "avg_cost": avg_cost,
                "current_price": current_price,
                "market_value": market_value,
                "unrealized_pnl": unrealized_pnl,
                "entered_at": pos["entered_at"],
            })

        cash = state.get("cash", 0.0)
        starting = state.get("starting_cash", 0.0)
        total_value = cash + holdings_value
        pnl_mad = total_value - starting if starting else 0.0
        pnl_pct = (pnl_mad / starting * 100) if starting else 0.0

        return json.dumps({
            "agent_id": state.get("account_id"),
            "username": state.get("username"),
            "cash": cash,
            "holdings_value": holdings_value,
            "total_value": total_value,
            "pnl_mad": pnl_mad,
            "pnl_pct": pnl_pct,
            "starting_cash": starting,
            "high_water_mark": state.get("high_water_mark"),
            "positions": positions_out,
            "orders": list((state.get("orders") or {}).values()),
        }, indent=2, default=str)

    @tool(
        name="paper_trade_history",
        description=(
            "Return executed paper-engine trades for the account at the given "
            "absolute directory, most recent first. Each trade has: id, "
            "order_id, symbol, side, quantity, price, total_value, commission, "
            "traded_at. Read-only."
        ),
        parameters={
            "type": "object",
            "properties": {
                "account_dir": {
                    "type": "string",
                    "description": "Absolute path to the paper account directory.",
                },
                "limit": {
                    "type": "integer",
                    "default": 50,
                    "minimum": 1,
                    "maximum": 500,
                },
            },
            "required": ["account_dir"],
        },
    )
    def _trades(_ctx: ToolContext, args: Dict[str, Any]) -> str:
        account_dir = args.get("account_dir")
        if not account_dir:
            return _err("account_dir is required")
        try:
            trades = _read_trades(account_dir, int(args.get("limit", 50)))
        except Exception as e:
            return _err(f"read error: {e}", 500)
        return json.dumps(trades, indent=2, default=str)

    return 2
