"""Paper-trading engine read-only tools.

Exposes the JSON state files written by the local paper engine
(/Users/ijaija/Documents/Claude/paper_engine/paper_engine.py) to the
MCP so artifacts and external callers can read account state without
shelling out to the engine itself. Read-only — placement and fill
simulation stays in the engine CLI.

Tools registered:
- paper_portfolio(account_dir)      — full state JSON (cash, positions, orders, meta)
- paper_trade_history(account_dir, limit) — recent trades from the JSONL log
"""

from __future__ import annotations

from .tools import register_paper_tools

__all__ = ["register_paper_tools"]
