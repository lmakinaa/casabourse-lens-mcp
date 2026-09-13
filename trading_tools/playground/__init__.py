"""Optional integration with the MASI Trading Simulator (playground).

This package registers MCP tools that let an LLM trade in the simulator:
place/cancel orders, read portfolio + trade history, check leaderboard.
Registration is gated on environment configuration — if
`MASI_PLAYGROUND_URL` and `MASI_API_KEY` aren't both set, no tools are
registered and the core read-only Casabourse Lens stays unchanged.

Multi-account support:
- `MASI_API_KEY` is the default account's bearer token (required).
- `MASI_API_KEY_<NAME>` registers an additional named account. The name
  becomes lowercase for tool calls — e.g., `MASI_API_KEY_MOMENTUM` is
  reached by passing `account="momentum"` to any playground tool.
- Omitting `account` (or passing `account="default"`) routes to the
  default key — fully backward-compatible with single-account setups.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Dict, Optional

from .client import PlaygroundClient, PlaygroundError

log = logging.getLogger(__name__)

# `MASI_API_KEY_<NAME>` env var → named account. NAME must be
# uppercase alphanumeric+underscore; surfaced lowercase to tools.
_NAMED_KEY_PATTERN = re.compile(r"^MASI_API_KEY_([A-Z][A-Z0-9_]*)$")


def _env(name: str) -> Optional[str]:
    val = os.environ.get(name, "").strip()
    return val or None


def _collect_named_keys() -> Dict[str, str]:
    """Return {lowercase_account_name: api_key} for every MASI_API_KEY_<NAME>
    env var present and non-empty. The default MASI_API_KEY is NOT included
    here — it's handled separately by the client's resolver.
    """
    out: Dict[str, str] = {}
    for key, val in os.environ.items():
        m = _NAMED_KEY_PATTERN.match(key)
        if m and val.strip():
            out[m.group(1).lower()] = val.strip()
    return out


def build_client_from_env() -> Optional[PlaygroundClient]:
    """Instantiate a PlaygroundClient iff MASI_PLAYGROUND_URL + MASI_API_KEY are set.

    Returns None (and logs a warning) on partial configuration so the
    rest of the MCP can boot read-only.
    """
    url = _env("MASI_PLAYGROUND_URL")
    default_key = _env("MASI_API_KEY")
    if not url or not default_key:
        if url or default_key:
            log.warning(
                "Playground partially configured — need BOTH MASI_PLAYGROUND_URL "
                "and MASI_API_KEY. Trading tools disabled."
            )
        return None

    named_keys = _collect_named_keys()
    if named_keys:
        log.info(
            "Playground: registered %d additional account(s): %s",
            len(named_keys),
            ", ".join(sorted(named_keys.keys())),
        )

    return PlaygroundClient(url, default_key, named_keys=named_keys)


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
