"""HTTP client for the MASI Trading Simulator (playground).

Kept deliberately separate from the DataProvider hierarchy: the playground
is a *write* system (orders, portfolio, leaderboard) not a data source.
Authentication is always a long-lived API key (`masi_...`) — we don't
expose username/password flows to the MCP layer.
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
    """Thin synchronous client over the MASI simulator REST API."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 15.0,
    ):
        if not base_url:
            raise ValueError("base_url is required")
        if not api_key:
            raise ValueError("api_key is required")
        self._base = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self._base,
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
        )

    def close(self) -> None:
        self._client.close()

    # ── HTTP ─────────────────────────────────────────────────────────────

    def _request(self, method: str, path: str, **kw) -> Any:
        try:
            resp = self._client.request(method, path, **kw)
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

    def me(self) -> Dict:
        return self._request("GET", "/auth/me")

    # ── Market ───────────────────────────────────────────────────────────

    def market_status(self) -> Dict:
        return self._request("GET", "/market/status")

    # ── Orders ───────────────────────────────────────────────────────────

    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        limit_price: Optional[float] = None,
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
        return self._request("POST", "/orders/", json=payload)

    def list_orders(
        self,
        status: Optional[str] = None,
        symbol: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        params: Dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        if symbol:
            params["symbol"] = symbol.upper()
        return self._request("GET", "/orders/", params=params)

    def get_order(self, order_id: str) -> Dict:
        return self._request("GET", f"/orders/{order_id}")

    def cancel_order(self, order_id: str) -> Dict:
        return self._request("DELETE", f"/orders/{order_id}")

    # ── Portfolio ────────────────────────────────────────────────────────

    def portfolio(self) -> Dict:
        return self._request("GET", "/portfolio/")

    def trade_history(self, limit: int = 50) -> List[Dict]:
        return self._request("GET", "/portfolio/trades", params={"limit": limit})

    # ── Leaderboard ──────────────────────────────────────────────────────

    def leaderboard(self, limit: int = 20) -> Dict:
        return self._request("GET", "/leaderboard/", params={"limit": limit})
