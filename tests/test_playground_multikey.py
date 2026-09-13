"""Tests for multi-account support in the playground client.

Covers:
- Default account routing (backward-compatible single-key setup).
- Named account routing (lookup by lowercase name).
- Unknown account raises PlaygroundError(401) cleanly.
- _collect_named_keys env parsing.
- "default" is reserved and always points at the constructor's api_key,
  even if named_keys tries to override it.
"""

from __future__ import annotations

import os
from typing import Dict

import httpx
import pytest

from trading_tools.playground import _collect_named_keys
from trading_tools.playground.client import PlaygroundClient, PlaygroundError


# ── Fakes ────────────────────────────────────────────────────────────────


class FakeTransport(httpx.BaseTransport):
    """Captures the Authorization header sent on each request and returns
    a 200 echo of the requested account name, so tests can assert which
    key the client ended up using on the wire.
    """

    def __init__(self) -> None:
        self.last_authorization: str = ""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.last_authorization = request.headers.get("authorization", "")
        return httpx.Response(
            200,
            json={"echoed_authorization": self.last_authorization},
        )


@pytest.fixture
def transport() -> FakeTransport:
    return FakeTransport()


@pytest.fixture
def client(transport: FakeTransport, monkeypatch: pytest.MonkeyPatch) -> PlaygroundClient:
    # Build a client whose underlying httpx.Client uses our fake transport.
    c = PlaygroundClient(
        base_url="https://fake.example.com",
        api_key="default_key_value",
        named_keys={"momentum": "momentum_key_value", "alpha": "alpha_key_value"},
    )
    # Swap the inner transport so no real HTTP fires.
    c._client = httpx.Client(
        base_url="https://fake.example.com",
        transport=transport,
        headers={"Accept": "application/json"},
    )
    yield c
    c.close()


# ── Resolver-level tests (no HTTP) ───────────────────────────────────────


def test_default_account_resolves_to_constructor_key() -> None:
    c = PlaygroundClient("https://x", "ctor_key", named_keys={"alt": "alt_key"})
    assert c._resolve_key(None) == "ctor_key"
    assert c._resolve_key("default") == "ctor_key"


def test_named_account_resolves_to_its_key() -> None:
    c = PlaygroundClient("https://x", "ctor_key", named_keys={"alt": "alt_key"})
    assert c._resolve_key("alt") == "alt_key"


def test_unknown_account_raises_playground_error() -> None:
    c = PlaygroundClient("https://x", "ctor_key", named_keys={"alt": "alt_key"})
    with pytest.raises(PlaygroundError) as excinfo:
        c._resolve_key("nonexistent")
    assert excinfo.value.status_code == 401
    assert "nonexistent" in excinfo.value.detail
    # The error should list registered accounts to help the caller.
    assert "alt" in excinfo.value.detail
    assert "default" in excinfo.value.detail


def test_default_name_cannot_be_overridden_by_named_keys() -> None:
    """Even if a caller passes named_keys={"default": "X"}, the constructor
    api_key takes precedence — "default" is a reserved name."""
    c = PlaygroundClient(
        "https://x",
        "ctor_key",
        named_keys={"default": "evil_override_attempt"},
    )
    assert c._resolve_key("default") == "ctor_key"
    assert c._resolve_key(None) == "ctor_key"


def test_known_accounts_includes_default_and_named() -> None:
    c = PlaygroundClient(
        "https://x",
        "ctor_key",
        named_keys={"momentum": "k1", "alpha": "k2"},
    )
    accounts = c.known_accounts()
    assert "default" in accounts
    assert "momentum" in accounts
    assert "alpha" in accounts
    # Sorted alphabetically for stable diagnostics.
    assert accounts == sorted(accounts)


def test_empty_named_keys_still_supports_default() -> None:
    c = PlaygroundClient("https://x", "ctor_key")
    assert c._resolve_key(None) == "ctor_key"
    assert c.known_accounts() == ["default"]


# ── Wire-level tests (verify the right header goes out) ──────────────────


def test_call_without_account_sends_default_bearer(
    client: PlaygroundClient, transport: FakeTransport
) -> None:
    client.me()
    assert transport.last_authorization == "Bearer default_key_value"


def test_call_with_default_sends_default_bearer(
    client: PlaygroundClient, transport: FakeTransport
) -> None:
    client.me(account="default")
    assert transport.last_authorization == "Bearer default_key_value"


def test_call_with_named_account_sends_that_bearer(
    client: PlaygroundClient, transport: FakeTransport
) -> None:
    client.me(account="momentum")
    assert transport.last_authorization == "Bearer momentum_key_value"


def test_back_to_back_calls_route_independently(
    client: PlaygroundClient, transport: FakeTransport
) -> None:
    """Two consecutive calls on different accounts should hit the wire
    with different bearers — i.e., auth is per-call, not sticky."""
    client.me(account="momentum")
    assert transport.last_authorization == "Bearer momentum_key_value"
    client.me(account="alpha")
    assert transport.last_authorization == "Bearer alpha_key_value"
    client.me()  # back to default
    assert transport.last_authorization == "Bearer default_key_value"


def test_place_order_routes_to_named_account(
    client: PlaygroundClient, transport: FakeTransport
) -> None:
    client.place_order(
        symbol="ATW",
        side="BUY",
        quantity=10,
        limit_price=692.0,
        account="momentum",
    )
    assert transport.last_authorization == "Bearer momentum_key_value"


def test_unknown_account_on_call_raises_before_http(
    client: PlaygroundClient, transport: FakeTransport
) -> None:
    with pytest.raises(PlaygroundError):
        client.me(account="nonexistent")
    # No HTTP fired, so the transport saw nothing.
    assert transport.last_authorization == ""


# ── Env-parsing tests ────────────────────────────────────────────────────


def _set_env(monkeypatch: pytest.MonkeyPatch, mapping: Dict[str, str]) -> None:
    for k in list(os.environ.keys()):
        if k.startswith("MASI_API_KEY"):
            monkeypatch.delenv(k, raising=False)
    for k, v in mapping.items():
        monkeypatch.setenv(k, v)


def test_collect_named_keys_finds_named_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(
        monkeypatch,
        {
            "MASI_API_KEY": "default_key",  # NOT included in named_keys
            "MASI_API_KEY_MOMENTUM": "momentum_key",
            "MASI_API_KEY_ALPHA": "alpha_key",
        },
    )
    keys = _collect_named_keys()
    assert keys == {"momentum": "momentum_key", "alpha": "alpha_key"}


def test_collect_named_keys_ignores_default_only(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch, {"MASI_API_KEY": "default_key"})
    assert _collect_named_keys() == {}


def test_collect_named_keys_ignores_empty_values(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(
        monkeypatch,
        {
            "MASI_API_KEY": "default_key",
            "MASI_API_KEY_EMPTY": "",
            "MASI_API_KEY_WHITESPACE": "   ",
            "MASI_API_KEY_REAL": "real_key",
        },
    )
    keys = _collect_named_keys()
    assert keys == {"real": "real_key"}


def test_collect_named_keys_lowercases_names(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch, {"MASI_API_KEY_MIXED_CASE_OK": "k"})
    keys = _collect_named_keys()
    assert "mixed_case_ok" in keys
