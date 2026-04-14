"""
v2-only: DuckDB CachingDataProvider behaviour.

Skipped automatically on main (no providers package).
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("trading_tools.providers")

from trading_tools.providers import (  # noqa: E402
    CachingDataProvider,
    DataClass,
    TTLPolicy,
)

from tests.fixtures import FakeUpstream  # noqa: E402

pytestmark = pytest.mark.v2_only


@pytest.fixture
def cache_path(tmp_path: Path) -> Path:
    return tmp_path / "cache.duckdb"


def test_hit_suppresses_upstream_call(cache_path):
    up = FakeUpstream()
    c = CachingDataProvider(up, cache_path=cache_path)
    c.get_stock_details("TEST")
    c.get_stock_details("TEST")
    assert up.calls["stock_details:TEST"] == 1


def test_different_key_is_a_miss(cache_path):
    up = FakeUpstream()
    c = CachingDataProvider(up, cache_path=cache_path)
    c.get_stock_details("A")
    c.get_stock_details("B")
    assert up.calls["stock_details:A"] == 1
    assert up.calls["stock_details:B"] == 1


def test_expired_ttl_refetches(cache_path):
    up = FakeUpstream()
    ttl0 = TTLPolicy(overrides={DataClass.STOCK_QUOTE: 0})
    c = CachingDataProvider(up, cache_path=cache_path, ttl_policy=ttl0)
    c.get_stock_details("TEST")
    c.get_stock_details("TEST")
    assert up.calls["stock_details:TEST"] == 2


def test_stale_while_revalidate(cache_path):
    """Cache must serve stale data when upstream returns None."""
    up = FakeUpstream()
    ttl0 = TTLPolicy(overrides={DataClass.STOCK_QUOTE: 0})

    # Prime the cache.
    primer = CachingDataProvider(up, cache_path=cache_path, ttl_policy=ttl0)
    primed = primer.get_stock_details("TEST")
    assert primed is not None
    primer.close()

    # New upstream of the same source name, but broken.
    class Broken(FakeUpstream):
        def get_stock_details(self, symbol):
            self._tick(f"stock_details:{symbol}")
            return None

    broken = Broken()
    broken.name = "fake"  # must match to read the same cache row
    c = CachingDataProvider(broken, cache_path=cache_path, ttl_policy=ttl0)
    served = c.get_stock_details("TEST")
    assert served is not None
    assert served == primed


def test_cache_persists_across_reopen(cache_path):
    up = FakeUpstream()
    c1 = CachingDataProvider(up, cache_path=cache_path)
    c1.get_stock_details("TEST")
    c1.close()

    c2 = CachingDataProvider(up, cache_path=cache_path)
    c2.get_stock_details("TEST")
    assert up.calls["stock_details:TEST"] == 1


def test_provider_name_decoration(cache_path):
    up = FakeUpstream()
    c = CachingDataProvider(up, cache_path=cache_path)
    assert c.name == "cached(fake)"


def test_macro_snapshot_is_cached(cache_path):
    up = FakeUpstream()
    c = CachingDataProvider(up, cache_path=cache_path)
    c.get_macro_snapshot()
    c.get_macro_snapshot()
    assert up.calls["macro_snapshot"] == 1
