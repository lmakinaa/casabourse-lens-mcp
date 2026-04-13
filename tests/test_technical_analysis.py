"""
Pure-math tests for TechnicalAnalysis. Identical on both branches.
"""

from __future__ import annotations

import math

import pytest

from trading_tools.technical_analysis import TechnicalAnalysis


@pytest.fixture
def ta():
    return TechnicalAnalysis()


def test_sma_basic(ta):
    assert ta.calculate_sma([10, 20, 30, 40, 50], 5) == 30.0
    assert ta.calculate_sma([1, 2, 3, 4, 5, 6], 3) == 5.0  # mean of last 3


def test_sma_insufficient_data(ta):
    assert ta.calculate_sma([1, 2], 5) is None


def test_ema_converges_toward_mean(ta):
    prices = [100.0] * 50
    assert abs(ta.calculate_ema(prices, 12) - 100.0) < 1e-6


def test_rsi_all_up_is_100(ta):
    # Strictly rising series → RSI ≈ 100
    prices = [float(i) for i in range(1, 30)]
    rsi = ta.calculate_rsi(prices, 14)
    assert rsi is not None and rsi > 99


def test_rsi_all_down_is_0(ta):
    prices = [float(i) for i in range(30, 1, -1)]
    rsi = ta.calculate_rsi(prices, 14)
    assert rsi is not None and rsi < 1


def test_rsi_insufficient(ta):
    assert ta.calculate_rsi([1, 2, 3], 14) is None


def test_macd_shape(ta):
    prices = [100 + math.sin(i / 3) for i in range(50)]
    out = ta.calculate_macd(prices)
    assert out is not None
    assert {"macd", "signal", "histogram"} <= set(out.keys())


def test_bollinger_upper_gt_lower(ta):
    prices = [100 + (i % 5) for i in range(40)]
    bb = ta.calculate_bollinger_bands(prices, 20)
    assert bb is not None
    assert bb["upper"] > bb["middle"] > bb["lower"]


def test_atr_positive(ta):
    highs = [float(i + 2) for i in range(30)]
    lows = [float(i) for i in range(30)]
    closes = [float(i + 1) for i in range(30)]
    atr = ta.calculate_atr(highs, lows, closes, 14)
    assert atr is not None and atr > 0


def test_support_resistance_contains_price(ta):
    highs = [100 + i * 0.1 for i in range(40)]
    lows = [95 + i * 0.1 for i in range(40)]
    closes = [97 + i * 0.1 for i in range(40)]
    out = ta.calculate_support_resistance(highs, lows, closes, 30)
    assert out is not None
    assert out["period_high"] >= out["current_price"] >= out["period_low"]
