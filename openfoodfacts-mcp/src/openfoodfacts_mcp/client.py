"""Async client for the Open Food Facts API.

API reference: https://openfoodfacts.github.io/openfoodfacts-server/api/
"""

from __future__ import annotations

import re
import time
from collections import deque
from typing import Any

import httpx

BASE_URL = "https://world.openfoodfacts.org"
KNOWLEDGE_PANEL_URL = "https://facets-kp.openfoodfacts.org/knowledge_panel"
# Open Food Facts asks every client to identify itself with a custom User-Agent.
USER_AGENT = "public-mcp-demos/openfoodfacts-mcp 2.0 (https://github.com/paul-schauer/public-mcp-demos)"

_BARCODE = re.compile(r"^\d{4,24}$")
# Tag values such as "en:organic", "breakfast-cereals" or "coca-cola". Rejecting "/", "."
# and "?" keeps user input from rewriting the request path.
_TAG = re.compile(r"^[\w:-]{1,100}$")


class OFFError(Exception):
    """Raised for any failed Open Food Facts request, with a message safe to show users."""


def validate_barcode(barcode: str) -> str:
    barcode = barcode.strip()
    if not _BARCODE.match(barcode):
        raise OFFError(f"Invalid barcode {barcode!r}: expected 4-24 digits (EAN-13, UPC-A, ...)")
    return barcode


def validate_tag(value: str, what: str = "tag") -> str:
    value = value.strip()
    if not _TAG.match(value):
        raise OFFError(f"Invalid {what} {value!r}: use letters, digits, '-' and ':' only (e.g. 'en:organic')")
    return value


class RateLimiter:
    """Sliding-window limiter that fails fast instead of queueing, so a tool call never hangs."""

    def __init__(self, max_calls: int, period: float, name: str) -> None:
        self.max_calls = max_calls
        self.period = period
        self.name = name
        self._calls: deque[float] = deque()

    def acquire(self) -> None:
        now = time.monotonic()
        while self._calls and now - self._calls[0] >= self.period:
            self._calls.popleft()
        if len(self._calls) >= self.max_calls:
            wait = self.period - (now - self._calls[0])
            raise OFFError(
                f"Open Food Facts allows {self.max_calls} {self.name} requests per {int(self.period)}s; "
                f"retry in {wait:.0f}s"
            )
        self._calls.append(now)


class OFFClient:
    def __init__(self, *, base_url: str = BASE_URL, timeout: float = 30.0) -> None:
        self._http = httpx.AsyncClient(
            base_url=base_url,
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            follow_redirects=True,
        )
        # Published limits: https://openfoodfacts.github.io/openfoodfacts-server/api/#rate-limits
        self.product_limit = RateLimiter(100, 60, "product")
        self.search_limit = RateLimiter(10, 60, "search")
        self.facet_limit = RateLimiter(2, 60, "facet")

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get(
        self,
        path: str,
        params: dict[str, Any] | None,
        limiter: RateLimiter,
        not_found: str = "Not found on Open Food Facts",
    ) -> Any:
        limiter.acquire()
        try:
            response = await self._http.get(path, params=params)
        except httpx.HTTPError as exc:
            raise OFFError(f"Could not reach Open Food Facts: {type(exc).__name__}") from None
        if response.status_code == 404:
            raise OFFError(not_found)
        if response.status_code == 429:
            raise OFFError("Open Food Facts rate limit reached; try again in a minute")
        if response.is_error:
            raise OFFError(f"Open Food Facts returned HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError:
            raise OFFError("Open Food Facts returned a non-JSON response") from None

    async def get_product(self, barcode: str, fields: str | None = None) -> dict[str, Any]:
        params = {"fields": fields} if fields else None
        barcode = validate_barcode(barcode)
        not_found = f"No product found for barcode {barcode}"
        data = await self.get(f"/api/v2/product/{barcode}.json", params, self.product_limit, not_found)
        if data.get("status") != 1:
            raise OFFError(not_found)
        return data.get("product", {})
