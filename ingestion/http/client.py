"""
PoliteClient — HTTP client for ingestion agents.

Responsibilities:
  - Proper TLS verification via certifi (avoids the system-bundle gap
    that breaks curl against api.casablanca-bourse.com)
  - Retry on transient failures (network error, 5xx) with exponential
    backoff. 4xx errors raise immediately — a 404 is not a transient.
  - Per-host politeness: min_interval seconds between requests so we
    don't hammer a public API the exchange hosts out of courtesy.
  - Structured logs per request attempt for observability.

Not general-purpose: only exposes get_json() since that's all agents need.
"""

from __future__ import annotations

import logging
import ssl
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
from urllib.parse import urlparse

import certifi
import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

log = logging.getLogger(__name__)

_DEFAULT_USER_AGENT = "casabourse-lens/0.1 (+https://github.com/ijaija/casabourse-lens)"

_CA_EXTRAS_DIR = Path(__file__).parent / "ca_extras"


def _build_ssl_context(extra_ca_files: Iterable[Path]) -> ssl.SSLContext:
    """
    Build an SSL context from certifi + any PEM files in ca_extras/.

    Some TLS endpoints (notably api.casablanca-bourse.com) serve only
    the leaf certificate and expect the client to have the intermediate
    already. certifi only ships roots. We bundle the missing
    intermediates as PEM files in ca_extras/ and load them here.
    Pinning intermediates rather than enabling AIA chasing keeps the
    trust surface explicit and auditable.
    """
    context = ssl.create_default_context(cafile=certifi.where())
    for pem in extra_ca_files:
        context.load_verify_locations(cafile=str(pem))
    return context


def _default_extra_ca_files() -> list[Path]:
    if not _CA_EXTRAS_DIR.is_dir():
        return []
    return sorted(_CA_EXTRAS_DIR.glob("*.pem"))


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return 500 <= exc.response.status_code < 600
    return isinstance(exc, (httpx.TransportError, httpx.TimeoutException))


class PoliteClient:
    """
    httpx client with retry, per-host rate limit, and verified TLS.

    Thread-safe: the per-host throttle uses a lock. Intended to be
    reused across requests — construct once per process, not per call.
    """

    def __init__(
        self,
        *,
        user_agent: str = _DEFAULT_USER_AGENT,
        min_interval: float = 1.0,
        timeout: float = 30.0,
        extra_ca_files: Optional[Iterable[Path]] = None,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        ca_files = list(extra_ca_files) if extra_ca_files is not None else _default_extra_ca_files()
        self._client = httpx.Client(
            verify=_build_ssl_context(ca_files),
            follow_redirects=True,
            timeout=timeout,
            headers={
                "User-Agent": user_agent,
                "Accept": "application/vnd.api+json, application/json;q=0.9",
            },
            transport=transport,
        )
        self._min_interval = min_interval
        self._lock = threading.Lock()
        self._last_request_at: Dict[str, float] = {}

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "PoliteClient":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    def get_json(self, url: str, *, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        GET `url`, return parsed JSON. Retries on 5xx / network errors
        up to 3 times with exponential backoff.
        """
        self._throttle(url)
        return self._get_json_with_retry(url, params)

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception(_is_retryable),
    )
    def _get_json_with_retry(
        self,
        url: str,
        params: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        started = time.monotonic()
        try:
            response = self._client.get(url, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as err:
            log.warning(
                "http.error",
                extra={
                    "url": url,
                    "status": err.response.status_code,
                    "duration_ms": int((time.monotonic() - started) * 1000),
                },
            )
            raise
        except httpx.HTTPError as err:
            log.warning(
                "http.transport_error",
                extra={
                    "url": url,
                    "error": type(err).__name__,
                    "duration_ms": int((time.monotonic() - started) * 1000),
                },
            )
            raise

        log.info(
            "http.ok",
            extra={
                "url": url,
                "status": response.status_code,
                "duration_ms": int((time.monotonic() - started) * 1000),
            },
        )
        return response.json()

    def _throttle(self, url: str) -> None:
        host = urlparse(url).netloc
        with self._lock:
            last = self._last_request_at.get(host, 0.0)
            now = time.monotonic()
            wait_for = self._min_interval - (now - last)
            if wait_for > 0:
                time.sleep(wait_for)
                now = time.monotonic()
            self._last_request_at[host] = now
