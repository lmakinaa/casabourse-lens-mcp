"""
TradingTools package.

One file per tool. Each handler module imports ``tool`` from
``_registry`` and declares itself with ``@tool(...)``; importing the
module appends an entry to the registry. ``TradingTools`` is a thin
shell that owns the ``ToolContext`` and dispatches by name.

Handler import order below is deliberate: it fixes the order of
``get_tool_definitions()`` output (declaration order on the old
monolithic class). New tools should be appended to this list.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from ..corporate_actions import CorporateActionService
from ..providers import CachingDataProvider, DataProvider, WafaBourseProvider
from ..technical_analysis import TechnicalAnalysis
from ._context import ToolContext
from ._registry import all_tools

# Explicit imports fix tool order. Do NOT switch to pkgutil auto-discovery
# without updating the schema-diff contract in tests/test_tools.py.
from . import market_overview  # noqa: F401
from . import stock_snapshot  # noqa: F401
from . import technical_indicators  # noqa: F401
from . import order_book  # noqa: F401
from . import price_history  # noqa: F401
from . import volume_profile  # noqa: F401
from . import all_stocks  # noqa: F401
from . import company_profile  # noqa: F401
from . import shareholders  # noqa: F401
from . import financial_metrics  # noqa: F401
from . import recent_trades  # noqa: F401
from . import screen_stocks  # noqa: F401
from . import volatility_analysis  # noqa: F401
from . import support_resistance  # noqa: F401
from . import market_breadth  # noqa: F401
from . import compare_stocks  # noqa: F401
from . import intraday_momentum  # noqa: F401
from . import corporate_events  # noqa: F401
from . import adjusted_price_history  # noqa: F401


class TradingTools:
    """Thin shell: owns the execution context, delegates to the registry."""

    def __init__(
        self,
        provider: DataProvider = None,
        tech_analysis: TechnicalAnalysis = None,
        corporate_actions: Optional[CorporateActionService] = None,
    ):
        self._ctx = ToolContext(
            provider=provider or CachingDataProvider(WafaBourseProvider()),
            tech_analysis=tech_analysis or TechnicalAnalysis(),
            corporate_actions=corporate_actions,
        )

    # Back-compat read/write shims so existing tests (and callers) that
    # reach into `.provider` / `.corporate_actions` keep working. The
    # ToolContext is frozen, so writes rebuild it.
    @property
    def provider(self) -> DataProvider:
        return self._ctx.provider

    @provider.setter
    def provider(self, value: DataProvider) -> None:
        object.__setattr__(self, "_ctx", ToolContext(
            provider=value,
            tech_analysis=self._ctx.tech_analysis,
            corporate_actions=self._ctx.corporate_actions,
        ))

    @property
    def tech_analysis(self) -> TechnicalAnalysis:
        return self._ctx.tech_analysis

    @property
    def corporate_actions(self) -> Optional[CorporateActionService]:
        return self._ctx.corporate_actions

    @corporate_actions.setter
    def corporate_actions(self, value: Optional[CorporateActionService]) -> None:
        object.__setattr__(self, "_ctx", ToolContext(
            provider=self._ctx.provider,
            tech_analysis=self._ctx.tech_analysis,
            corporate_actions=value,
        ))

    def get_tool_definitions(self) -> List[Dict]:
        return [t.schema for t in all_tools()]

    def execute_tool(self, tool_name: str, tool_input: Dict) -> str:
        for t in all_tools():
            if t.name == tool_name:
                try:
                    return t.handler(self._ctx, tool_input or {})
                except Exception as e:
                    return f"Error executing {tool_name}: {str(e)}"
        return f"Error: Unknown tool {tool_name}"
