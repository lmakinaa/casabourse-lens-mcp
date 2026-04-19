"""
Casabourse Lens MCP Server.

Composes the data stack (WafaBourse provider → DuckDB cache → trading
tools) and exposes it over MCP stdio. The server is the only place
that knows which concrete provider is wired in — everything below
consumes the DataProvider interface.
"""

import asyncio
import logging
import os
from pathlib import Path

from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from trading_tools import (
    CachingDataProvider,
    TechnicalAnalysis,
    TradingTools,
    WafaBourseProvider,
)
from trading_tools.corporate_actions import (
    CorporateActionService,
    CorporateActionStore,
)
from trading_tools.playground import (
    build_client_from_env as build_playground_client,
    register_trading_tools as register_playground_tools,
)

logging.basicConfig(
    level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)

REPO_ROOT = Path(__file__).resolve().parent
CA_DB_PATH = Path(os.environ.get("CASABOURSE_CA_DB", REPO_ROOT / "data" / "corporate_actions.sqlite"))


def build_mcp_tools(tool_defs: list) -> list[types.Tool]:
    """Convert OpenAI-format tool definitions to MCP Tool objects."""
    return [
        types.Tool(
            name=t["function"]["name"],
            description=t["function"]["description"],
            inputSchema=t["function"]["parameters"],
        )
        for t in tool_defs
    ]


def main():
    print("Starting Casabourse Lens MCP Server V2...")
    provider = CachingDataProvider(WafaBourseProvider())
    ca_store = CorporateActionStore(CA_DB_PATH)
    ca_service = CorporateActionService(ca_store)
    trading_tools = TradingTools(provider, TechnicalAnalysis(), ca_service)

    # Optional: MASI Trading Simulator (playground) write tools. Registered
    # only when both MASI_PLAYGROUND_URL and MASI_API_KEY are set. Must run
    # BEFORE get_tool_definitions() so the new handlers appear in the MCP
    # list_tools() response.
    playground_client = build_playground_client()
    if playground_client is not None:
        count = register_playground_tools(playground_client)
        logging.getLogger(__name__).info(
            "Playground trading tools registered: %d", count
        )

    mcp_tool_list = build_mcp_tools(trading_tools.get_tool_definitions())
    server = Server("casabourse-lens")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return mcp_tool_list

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        result = trading_tools.execute_tool(name, arguments)
        return [types.TextContent(type="text", text=result)]

    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    asyncio.run(run())


if __name__ == "__main__":
    main()
