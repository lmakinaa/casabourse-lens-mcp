"""
Data provider layer.

Exposes the abstract DataProvider contract, the WafaBourse concrete
implementation, and the DuckDB caching decorator. Tools depend only on
the DataProvider interface — never on a concrete client.
"""

from .base import DataProvider, DataClass, ProviderError
from .wafabourse import WafaBourseProvider
from .cache import CachingDataProvider, TTLPolicy

__all__ = [
    "DataProvider",
    "DataClass",
    "ProviderError",
    "WafaBourseProvider",
    "CachingDataProvider",
    "TTLPolicy",
]
