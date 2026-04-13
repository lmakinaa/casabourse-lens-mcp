"""
Cross-branch test harness.

Wires a fresh TradingTools against FakeUpstream on every test. Works
against both branches:
  - main: TradingTools(wafa_api=FakeUpstream(), tech_analysis=...)
  - v2:   TradingTools(provider=FakeUpstream(), tech_analysis=...)

Both accept the fake positionally — duck typing does the rest.
"""

from __future__ import annotations

import importlib
import json

import pytest

from tests.fixtures import FakeUpstream


def _branch_marker() -> str:
    """Detect which branch shape is loaded (main vs. v2)."""
    try:
        importlib.import_module("trading_tools.providers")
        return "v2"
    except ModuleNotFoundError:
        return "main"


BRANCH = _branch_marker()


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "v2_only: test only runs on the v2 branch (cache/provider features)"
    )


def pytest_collection_modifyitems(config, items):
    if BRANCH == "main":
        skip_v2 = pytest.mark.skip(reason="feature only exists on v2 branch")
        for item in items:
            if "v2_only" in item.keywords:
                item.add_marker(skip_v2)


@pytest.fixture
def upstream() -> FakeUpstream:
    return FakeUpstream()


@pytest.fixture
def tools(upstream):
    from trading_tools.tools import TradingTools
    from trading_tools.technical_analysis import TechnicalAnalysis

    return TradingTools(upstream, TechnicalAnalysis())


@pytest.fixture
def parse_json():
    """Helper: parse execute_tool() JSON output, or raise with the error body."""

    def _parse(raw: str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AssertionError(f"tool returned non-JSON: {raw!r}") from exc

    return _parse
