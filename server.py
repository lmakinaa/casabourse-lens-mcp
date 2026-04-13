"""
Casabourse Lens MCP Server.

Composes the data stack (WafaBourse provider → DuckDB cache → trading
tools) and exposes it over MCP stdio. The server is the only place
that knows which concrete provider is wired in — everything below
consumes the DataProvider interface.
"""

import asyncio
import logging

from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from trading_tools import (
    CachingDataProvider,
    TechnicalAnalysis,
    TradingTools,
    WafaBourseProvider,
)

logging.basicConfig(
    level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)


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
    provider = CachingDataProvider(WafaBourseProvider())
    trading_tools = TradingTools(provider, TechnicalAnalysis())

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
