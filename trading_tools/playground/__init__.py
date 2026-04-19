"""Optional integration with the MASI Trading Simulator (playground).

This package registers MCP tools that let an LLM trade in the simulator:
place/cancel orders, read portfolio + trade history, check leaderboard.
Registration is gated on environment configuration — if
`MASI_PLAYGROUND_URL` and `MASI_API_KEY` aren't both set, no tools are
registered and the core read-only Casabourse Lens stays unchanged.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from .client import PlaygroundClient, PlaygroundError

log = logging.getLogger(__name__)


def _env(name: str) -> Optional[str]:
    val = os.environ.get(name, "").strip()
    return val or None


def build_client_from_env() -> Optional[PlaygroundClient]:
    """Instantiate a PlaygroundClient iff both env vars are present."""
    url = _env("MASI_PLAYGROUND_URL")
    key = _env("MASI_API_KEY")
    if not url or not key:
        if url or key:
            log.warning(
                "Playground partially configured — need BOTH MASI_PLAYGROUND_URL and MASI_API_KEY. Trading tools disabled."
            )
        return None
    return PlaygroundClient(url, key)


def register_trading_tools(client: PlaygroundClient) -> int:
    """Register trading tools against the shared MCP registry.

    Returns the number of tools registered. Importing the tools module has
    the side-effect of declaring each tool via `@tool(...)` against the
    closure-captured client.
    """
    # Deferred import — avoids mandatory dependency when trading is disabled.
    from . import tools as _tools  # noqa: F401

    return _tools.register(client)


__all__ = [
    "PlaygroundClient",
    "PlaygroundError",
    "build_client_from_env",
    "register_trading_tools",
]
