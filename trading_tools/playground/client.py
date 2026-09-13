"""HTTP client for the MASI Trading Simulator (playground).

Kept deliberately separate from the DataProvider hierarchy: the playground
is a *write* system (orders, portfolio, leaderboard) not a data source.
Authentication is always a long-lived API key (`masi_...`) — we don't
expose username/password flows to the MCP layer.

Multi-account support: a single client instance can route calls to any
of N configured accounts. The default account uses the constructor's
`api_key`; additional accounts are registered via `named_keys` and
addressed by name on each method call. Auth headers are injected
per-request rather than baked into the shared httpx.Client, so all
accounts share the connection pool.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx


class PlaygroundError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(f"[{status_code}] {detail}")
        self.status_code = status_code
        self.detail = detail


class PlaygroundClient:
    """Thin synchronous client over the MASI simulator REST API.

    Args:
        base_url: REST endpoint root.
        api_key: API key for the *default* account.
        named_keys: Optional {name: api_key} for additional accounts.
            Names should be lowercase; addressed via `account="<name>"`
            on any method call.
        timeout: HTTP timeout in seconds.

    The reserved name "default" always resolves to `api_key` regardless
    of what's in `named_keys`, so calls can be explicit without conflict.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        named_keys: Optional[Dict[str, str]] = None,
        timeout: float = 15.0,
    ):
        if not base_url:
            raise ValueError("base_url is required")
        if not api_key:
            raise ValueError("api_key is required")
        self._base = base_url.rstrip("/")
        self._default_key = api_key
        self._named_keys: Dict[str, str] = dict(named_keys or {})
        # "default" is reserved — points at the constructor key.
        # Explicit override via named_keys["default"] is intentionally not allowed.
        self._named_keys["default"] = api_key
        self._client = httpx.Client(
            base_url=self._base,
            timeout=timeout,
            headers={"Accept": "application/json"},
        )

    def close(self) -> None:
        self._client.close()

    # ── Auth resolution ──────────────────────────────────────────────────

    def _resolve_key(self, account: Optional[str]) -> str:
        """Return the bearer token for the requested account.

        None or "default" → the default key. Any other name must be in
        `named_keys`; unknown names raise PlaygroundError(401, ...) so
        the failure is surfaced to the LLM as a clean tool error rather
        than a Python exception.
        """
        if account is None or account == "default":
            return self._default_key
        key = self._named_keys.get(account)
        if not key:
            registered = ", ".join(sorted(self._named_keys.keys()))
            raise PlaygroundError(
                401,
                f"Unknown account '{account}'. Registered accounts: {registered}",
            )
        return key

    def known_accounts(self) -> List[str]:
        """Return the names of all configured accounts.

        Useful for tool schema documentation and runtime diagnostics.
        Always includes "default" plus any named accounts.
        """
        return sorted(self._named_keys.keys())

    # ── HTTP ─────────────────────────────────────────────────────────────

    def _request(
        self,
        method: str,
        path: str,
        account: Optional[str] = None,
        **kw,
    ) -> Any:
        # Per-call Authorization header — overrides the shared client's
        # default (which has no auth, only Accept). This lets a single
        # httpx.Client serve every account on the same connection pool.
        api_key = self._resolve_key(account)
        headers = kw.pop("headers", None) or {}
        headers = {**headers, "Authorization": f"Bearer {api_key}"}

        try:
            resp = self._client.request(method, path, headers=headers, **kw)
        except httpx.HTTPError as e:
            raise PlaygroundError(0, f"Connection error: {e}") from None

        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text or f"HTTP {resp.status_code}"
            raise PlaygroundError(resp.status_code, detail)

        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    # ── Identity ─────────────────────────────────────────────────────────

    def me(self, account: Optional[str] = None) -> Dict:
        return self._request("GET", "/auth/me", account=account)

    # ── Market ───────────────────────────────────────────────────────────

    def market_status(self, account: Optional[str] = None) -> Dict:
        return self._request("GET", "/market/status", account=account)

    # ── Orders ───────────────────────────────────────────────────────────

    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        limit_price: Optional[float] = None,
        account: Optional[str] = None,
    ) -> Dict:
        order_type = "LIMIT" if limit_price is not None else "MARKET"
        payload: Dict[str, Any] = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "order_type": order_type,
            "quantity": quantity,
        }
        if limit_price is not None:
            payload["limit_price"] = limit_price
        return self._request("POST", "/orders/", account=account, json=payload)

    def list_orders(
        self,
        status: Optional[str] = None,
        symbol: Optional[str] = None,
        limit: int = 50,
        account: Optional[str] = None,
    ) -> List[Dict]:
        params: Dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        if symbol:
            params["symbol"] = symbol.upper()
        return self._request("GET", "/orders/", account=account, params=params)

    def get_order(self, order_id: str, account: Optional[str] = None) -> Dict:
        return self._request("GET", f"/orders/{order_id}", account=account)

    def cancel_order(self, order_id: str, account: Optional[str] = None) -> Dict:
        return self._request("DELETE", f"/orders/{order_id}", account=account)

    # ── Portfolio ────────────────────────────────────────────────────────

    def portfolio(self, account: Optional[str] = None) -> Dict:
        return self._request("GET", "/portfolio/", account=account)

    def trade_history(
        self,
        limit: int = 50,
        account: Optional[str] = None,
    ) -> List[Dict]:
        return self._request(
            "GET",
            "/portfolio/trades",
            account=account,
            params={"limit": limit},
        )

    # ── Leaderboard ──────────────────────────────────────────────────────

    def leaderboard(
        self,
        limit: int = 20,
        account: Optional[str] = None,
    ) -> Dict:
        return self._request(
            "GET",
            "/leaderboard/",
            account=account,
            params={"limit": limit},
        )
