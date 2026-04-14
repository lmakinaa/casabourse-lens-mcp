"""
Decorator-driven tool registry.

Each handler module declares itself via `@tool(...)`. Importing the
module populates a module-level list in insertion order. The
`TradingTools` shell reads from this list — no walking of `vars(cls)`,
no dispatch dict to keep in sync.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List


@dataclass(frozen=True)
class ToolEntry:
    name: str
    schema: Dict[str, Any]
    handler: Callable[..., str]  # (ctx, args) -> str


_REGISTRY: List[ToolEntry] = []


def tool(*, name: str, description: str, parameters: Dict[str, Any]):
    """Register a handler function as an MCP tool."""

    def decorator(fn: Callable[..., str]) -> Callable[..., str]:
        _REGISTRY.append(
            ToolEntry(
                name=name,
                schema={
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": description,
                        "parameters": parameters,
                    },
                },
                handler=fn,
            )
        )
        return fn

    return decorator


def all_tools() -> List[ToolEntry]:
    return list(_REGISTRY)
