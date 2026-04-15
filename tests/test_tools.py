"""
Contract tests for every TradingTools handler.

Strategy: drive each tool through execute_tool(name, args), parse the
JSON, and assert on the *shape* + critical numeric fields. These tests
must pass on both main and v2 branches.
"""

from __future__ import annotations

import json

import pytest


# --------------------------------------------------------------------- #
# Tool registry — 17 core tools must exist on every branch. Branches
# may add more (e.g. corporate-action tools on feat/corporate-actions);
# the core set is the stable contract.
# --------------------------------------------------------------------- #

CORE_TOOLS = {
    "get_market_overview",
    "get_stock_snapshot",
    "get_technical_analysis",
    "get_order_book",
    "get_price_history",
    "analyze_volume_profile",
    "get_all_stocks",
    "get_company_profile",
    "get_shareholders",
    "get_financial_metrics",
    "get_recent_trades",
    "screen_stocks",
    "get_volatility_analysis",
    "get_support_resistance",
    "get_market_breadth",
    "compare_stocks",
    "get_intraday_momentum",
}


def test_tool_definitions_are_openai_shaped(tools):
    defs = tools.get_tool_definitions()
    names = {d["function"]["name"] for d in defs}
    missing = CORE_TOOLS - names
    assert not missing, f"core tools missing: {missing}"
    for d in defs:
        assert d["type"] == "function"
        fn = d["function"]
        assert "description" in fn and fn["description"]
        assert fn["parameters"]["type"] == "object"


def test_unknown_tool_returns_error_string(tools):
    out = tools.execute_tool("nope_does_not_exist", {})
    assert "Unknown tool" in out or "Error" in out


# --------------------------------------------------------------------- #
# Per-tool contract
# --------------------------------------------------------------------- #


def test_market_overview(tools, parse_json):
    out = parse_json(tools.execute_tool("get_market_overview", {}))
    assert out["market_status"] == "OPEN"
    assert out["masi_index"]["value"] == 13_500.0
    assert out["masi_index"]["gainers"] == 40
    assert len(out["top_gainers"]) == 3
    assert len(out["top_losers"]) == 3
    assert out["top_gainers"][0]["symbol"] == "AAA"


def test_stock_snapshot(tools, parse_json):
    out = parse_json(tools.execute_tool("get_stock_snapshot", {"symbol": "TEST"}))
    assert out["symbol"] == "TEST"
    assert out["current_price"] == 110.0
    assert out["change_pct"] == 1.0
    assert out["volume_mad"] == 5.0  # 5_000_000 / 1e6
    assert out["num_trades"] == 250
    assert out["buy_pressure_pct"] == 55.0


def test_technical_analysis_all_indicators(tools, parse_json):
    out = parse_json(
        tools.execute_tool(
            "get_technical_analysis",
            {
                "symbol": "TEST",
                "indicators": ["sma20", "sma50", "ema12", "rsi", "macd", "bollinger"],
            },
        )
    )
    assert out["symbol"] == "TEST"
    assert "current_price" in out
    assert isinstance(out["sma20"], float)
    assert isinstance(out["sma50"], float)
    assert isinstance(out["ema12"], float)
    assert 0 <= out["rsi"] <= 100
    assert {"macd", "signal", "histogram"} <= set(out["macd"].keys())
    bb = out["bollinger_bands"]
    assert bb["upper"] > bb["middle"] > bb["lower"]


def test_order_book(tools, parse_json):
    out = parse_json(tools.execute_tool("get_order_book", {"symbol": "TEST"}))
    assert out["best_bid"] == 109.5
    assert out["best_ask"] == 110.5
    assert abs(out["spread_mad"] - 1.0) < 1e-9
    assert out["total_bid_volume"] == 1000 + 500 + 300 + 200 + 150
    assert out["total_ask_volume"] == 800 + 600 + 400 + 250 + 200
    assert len(out["bid_levels"]) == 5
    assert len(out["ask_levels"]) == 5


def test_price_history_respects_days(tools, parse_json):
    out = parse_json(tools.execute_tool("get_price_history", {"symbol": "TEST", "days": 10}))
    assert out["symbol"] == "TEST"
    assert out["days"] == 10
    assert len(out["data"]) == 10
    for row in out["data"]:
        assert {"date", "close", "volume"} <= set(row.keys())


def test_price_history_default_days(tools, parse_json):
    out = parse_json(tools.execute_tool("get_price_history", {"symbol": "TEST"}))
    assert out["days"] == 30


def test_analyze_volume_profile(tools, parse_json):
    out = parse_json(tools.execute_tool("analyze_volume_profile", {"symbol": "TEST"}))
    assert out["symbol"] == "TEST"
    assert out["current_volume_mad"] == 5.0
    assert out["interpretation"] in {"High", "Normal", "Low"}


def test_get_all_stocks(tools, parse_json):
    out = parse_json(tools.execute_tool("get_all_stocks", {}))
    assert out["total_stocks"] == 3
    assert {s["symbol"] for s in out["stocks"]} == {"AAA", "BBB", "CCC"}


def test_get_all_stocks_with_limit(tools, parse_json):
    out = parse_json(tools.execute_tool("get_all_stocks", {"limit": 2}))
    assert out["total_stocks"] == 2


def test_company_profile(tools, parse_json):
    out = parse_json(tools.execute_tool("get_company_profile", {"symbol": "TEST"}))
    assert out["symbol"] == "TEST"
    assert out["sector"] == "Banks"
    assert "Line 1" in out["description"] and "Line 2" in out["description"]
    assert out["ipo_date"] == "2010-01-01"
    assert out["website"] == "https://example.ma"


def test_shareholders(tools, parse_json):
    out = parse_json(tools.execute_tool("get_shareholders", {"symbol": "TEST"}))
    assert out["float_percentage"] == 35.0
    assert len(out["major_holders"]) == 2
    assert out["ownership_concentration"] == 65.0


def test_financial_metrics(tools, parse_json):
    out = parse_json(tools.execute_tool("get_financial_metrics", {"symbol": "TEST"}))
    assert out["symbol"] == "TEST"
    assert out["valuation_ratios"]["pe_ratio"]["2023"] == 12.0
    assert out["per_share_metrics"]["earnings_per_share_dh"]["2023"] == 9.0
    assert out["profitability_margins"]["net_margin_pct"]["2023"] == 18.0
    assert out["income_statement"]["revenue_mdh"]["2023"] == 10000


def test_recent_trades(tools, parse_json):
    out = parse_json(tools.execute_tool("get_recent_trades", {"symbol": "TEST"}))
    assert out["num_trades"] == 5
    flow = out["trade_flow_analysis"]
    # Tick rule on oldest→newest prices [110.0, 110.2, 110.1, 110.3, 110.0]:
    # first trade has no predecessor → UNKNOWN, excluded from flow.
    # 110.2 uptick → BUY 150; 110.1 downtick → SELL 80;
    # 110.3 uptick → BUY 120; 110.0 downtick → SELL 90.
    assert flow["total_buy_volume"] == 150 + 120  # 270
    assert flow["total_sell_volume"] == 80 + 90   # 170
    assert flow["net_flow"] == "BUYING_PRESSURE"  # 270/440 ≈ 61.4%
    # Prices flow through (no longer zero) and tick-rule labels the newest.
    first_trade = out["trades"][0]
    assert first_trade["price"] == 110.0
    assert first_trade["direction"] == "SELL"


def test_screen_stocks_direction_up(tools, parse_json):
    out = parse_json(tools.execute_tool("screen_stocks", {"direction": "up"}))
    assert all(s["change_pct"] > 0 for s in out["stocks"])
    assert out["total_matches"] == 1  # only AAA


def test_screen_stocks_min_volume(tools, parse_json):
    out = parse_json(tools.execute_tool("screen_stocks", {"min_volume_mad": 6}))
    assert all(s["volume_mad"] >= 6 for s in out["stocks"])
    assert out["total_matches"] == 1  # only AAA has 10M


def test_volatility_analysis(tools, parse_json):
    out = parse_json(tools.execute_tool("get_volatility_analysis", {"symbol": "TEST"}))
    assert out["symbol"] == "TEST"
    assert out["volatility_classification"] in {"LOW", "MODERATE", "HIGH"}
    assert out["atr"]["period"] == 14


def test_support_resistance(tools, parse_json):
    out = parse_json(
        tools.execute_tool("get_support_resistance", {"symbol": "TEST", "lookback": 30})
    )
    assert out["symbol"] == "TEST"
    assert isinstance(out["resistance_levels"], list)
    assert isinstance(out["support_levels"], list)
    assert out["period_high"] >= out["current_price"] >= out["period_low"]
    assert out["trading_zones"]["current_zone"] in {
        "NEAR_RESISTANCE",
        "NEAR_SUPPORT",
        "MID_RANGE",
    }


def test_market_breadth(tools, parse_json):
    out = parse_json(tools.execute_tool("get_market_breadth", {}))
    b = out["breadth_indicators"]
    assert b["advances"] == 1
    assert b["declines"] == 1
    assert b["unchanged"] == 1
    assert out["market_sentiment"] in {
        "STRONGLY_BULLISH",
        "BULLISH",
        "NEUTRAL",
        "BEARISH",
        "STRONGLY_BEARISH",
    }


def test_compare_stocks(tools, parse_json):
    out = parse_json(
        tools.execute_tool("compare_stocks", {"symbols": ["AAA", "BBB", "CCC"]})
    )
    assert len(out["comparison"]) == 3
    assert out["rankings"]["best_performer_today"] is not None


def test_compare_stocks_requires_two(tools):
    out = tools.execute_tool("compare_stocks", {"symbols": ["AAA"]})
    assert "at least 2" in out


def test_intraday_momentum(tools, parse_json):
    out = parse_json(tools.execute_tool("get_intraday_momentum", {"symbol": "TEST"}))
    assert out["symbol"] == "TEST"
    assert out["overall_momentum"] in {"BULLISH", "BEARISH", "NEUTRAL"}
    assert "book_imbalance" not in out  # key is namespaced under pressure_analysis
    assert "order_book_imbalance_pct" in out["pressure_analysis"]


def test_orderflow_imbalance(tools, parse_json):
    out = parse_json(tools.execute_tool("analyze_orderflow_imbalance", {"symbol": "TEST"}))
    assert out["symbol"] == "TEST"
    assert out["classification"]["method"] == "lee_ready_quote_then_tick"
    assert out["classification"]["reference_mid"] == 110.0
    flow = out["flow"]
    quality = out["quality"]
    assert flow["buy_volume"] == 350
    assert flow["sell_volume"] == 90
    assert flow["net_flow"] == "BUYING_PRESSURE"
    assert flow["volume_imbalance_pct"] == 59.09
    assert quality["classification_coverage_pct"] == 81.48
    assert quality["trades_total"] == 5


def test_correlation_matrix_requires_ca_service(tools):
    out = tools.execute_tool("get_correlation_matrix", {"symbols": ["AAA", "BBB"]})
    assert "corporate-action service not configured" in out


def test_beta_requires_ca_service(tools):
    out = tools.execute_tool("get_beta", {"symbol": "AAA"})
    assert "corporate-action service not configured" in out


def test_macro_snapshot(tools, parse_json):
    out = parse_json(tools.execute_tool("get_macro_snapshot", {}))
    assert out["source"] == "fake_macro"
    assert out["as_of"] == "2026-04-14"
    assert out["policy_rate_pct"] == 3.0
    assert out["t_bill_13w_pct"] == 2.85
    assert out["t_bill_52w_pct"] == 3.1
    assert out["cpi_yoy_pct"] == 1.7
    assert out["masi_dividend_yield_pct"] == 3.9
    assert out["equity_risk_premium_pct"] == 0.8


def test_fx_rates(tools, parse_json):
    out = parse_json(tools.execute_tool("get_fx_rates", {}))
    assert out["source"] == "fake_fx"
    assert out["as_of"] == "2026-04-15"
    assert out["usd_mad_spot"] == 9.98
    assert out["eur_mad_spot"] == 10.82
    assert out["usd_mad_20d_change_pct"] == 0.45
    assert out["eur_mad_20d_change_pct"] == -0.22
    assert out["warnings"] == []


def test_commodity_prices(tools, parse_json):
    out = parse_json(tools.execute_tool("get_commodity_prices", {}))
    assert out["source"] == "fake_commodities"
    assert out["as_of"] == "2026-04-15"
    assert out["brent_usd_per_bbl"] == 84.2
    assert out["gold_usd_per_oz"] == 2310.0
    assert out["phosphate_usd_per_mt"] == 152.0
    assert out["brent_30d_change_pct"] == 3.2
    assert out["gold_30d_change_pct"] == 1.1
    assert out["phosphate_30d_change_pct"] == 0.0
    assert out["warnings"] == []


def test_news(tools, parse_json):
    out = parse_json(tools.execute_tool("get_news", {"symbol": "CSR", "limit": 5, "days": 7}))
    assert out["symbol"] == "CSR"
    assert out["window_days"] == 7
    assert out["source"] == "fake_news"
    assert out["article_count"] == 2
    assert len(out["articles"]) == 2
    assert out["articles"][0]["source"] in {"medias24", "lavieeco"}


def test_news_sentiment(tools, parse_json):
    out = parse_json(tools.execute_tool("get_news_sentiment", {"symbol": "CSR", "window_days": 7}))
    assert out["symbol"] == "CSR"
    assert out["window_days"] == 7
    assert out["source"] == "fake_news"
    assert out["mentions_current"] == 4
    assert out["mentions_baseline_avg"] == 1.5
    assert out["sentiment_label"] == "positive"
    assert out["warnings"] == []


# --------------------------------------------------------------------- #
# Error paths — upstream returning None must surface as a clean error
# string, never an uncaught exception.
# --------------------------------------------------------------------- #


def test_stock_snapshot_handles_missing_upstream(tools):
    tools.provider_attr = None  # placeholder; real patch below

    # Patch the getter that backs this tool to return None
    upstream = _get_upstream(tools)
    upstream.get_stock_details = lambda symbol: None  # type: ignore[assignment]

    out = tools.execute_tool("get_stock_snapshot", {"symbol": "TEST"})
    assert "Error" in out and "TEST" in out


def test_order_book_handles_empty(tools):
    upstream = _get_upstream(tools)
    upstream.get_order_book = lambda symbol, depth=5: None  # type: ignore[assignment]

    out = tools.execute_tool("get_order_book", {"symbol": "TEST"})
    assert "Error" in out


# --------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------- #


def _get_upstream(tools):
    """
    Return the upstream client regardless of branch.
    - main: TradingTools.wafa_api
    - v2:   TradingTools.provider
    """
    return getattr(tools, "provider", None) or getattr(tools, "wafa_api")
