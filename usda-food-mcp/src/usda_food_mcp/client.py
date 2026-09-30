"""Async client for the USDA FoodData Central (FDC) REST API.

API reference: https://fdc.nal.usda.gov/api-guide
"""

from __future__ import annotations

from typing import Any, Literal

import httpx

BASE_URL = "https://api.nal.usda.gov/fdc/v1"
MAX_PAGE_SIZE = 200
MAX_IDS_PER_REQUEST = 20

DataType = Literal["Branded", "Foundation", "Survey (FNDDS)", "SR Legacy"]
Format = Literal["abridged", "full"]
SortOrder = Literal["asc", "desc"]


class FDCError(Exception):
    """Raised when the FDC API returns an error. Messages never include the API key."""


class FDCClient:
    """Thin wrapper over the four FDC endpoints.

    The API key is sent in the ``X-Api-Key`` header rather than the query string so it
    can't leak into error messages, logs or tracebacks that include the request URL.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = BASE_URL,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("An FDC API key is required")
        self._http = httpx.AsyncClient(
            base_url=base_url,
            headers={"X-Api-Key": api_key},
            timeout=timeout,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get_food(
        self, fdc_id: int, format: Format = "full", nutrients: list[int] | None = None
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"format": format}
        if nutrients:
            params["nutrients"] = ",".join(map(str, nutrients))
        return await self._request("GET", f"/food/{fdc_id}", params=params)

    async def get_foods(
        self, fdc_ids: list[int], format: Format = "full", nutrients: list[int] | None = None
    ) -> list[dict[str, Any]]:
        if not fdc_ids:
            raise ValueError("Provide at least one FDC ID")
        if len(fdc_ids) > MAX_IDS_PER_REQUEST:
            raise ValueError(f"At most {MAX_IDS_PER_REQUEST} FDC IDs per request")
        body: dict[str, Any] = {"fdcIds": fdc_ids, "format": format}
        if nutrients:
            body["nutrients"] = nutrients
        return await self._request("POST", "/foods", json=body)

    async def search_foods(
        self,
        query: str,
        data_type: list[DataType] | None = None,
        page_size: int = 50,
        page_number: int = 1,
        sort_by: str | None = None,
        sort_order: SortOrder | None = None,
        brand_owner: str | None = None,
    ) -> dict[str, Any]:
        body = _paging(page_size, page_number, data_type, sort_by, sort_order)
        body["query"] = query
        if brand_owner:
            body["brandOwner"] = brand_owner
        return await self._request("POST", "/foods/search", json=body)

    async def list_foods(
        self,
        data_type: list[DataType] | None = None,
        page_size: int = 50,
        page_number: int = 1,
        sort_by: str | None = None,
        sort_order: SortOrder | None = None,
    ) -> list[dict[str, Any]]:
        body = _paging(page_size, page_number, data_type, sort_by, sort_order)
        return await self._request("POST", "/foods/list", json=body)

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await self._http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise FDCError(f"Could not reach the FDC API: {type(exc).__name__}") from None

        if response.status_code == 404:
            raise FDCError("No food found for that FDC ID")
        if response.status_code in (401, 403):
            raise FDCError("The FDC API rejected the API key")
        if response.status_code == 429:
            raise FDCError("FDC API rate limit reached; try again later")
        if response.is_error:
            raise FDCError(f"FDC API returned HTTP {response.status_code}")
        return response.json()


def _paging(
    page_size: int,
    page_number: int,
    data_type: list[DataType] | None,
    sort_by: str | None,
    sort_order: SortOrder | None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "pageSize": max(1, min(page_size, MAX_PAGE_SIZE)),
        "pageNumber": max(1, page_number),
    }
    if data_type:
        body["dataType"] = data_type
    if sort_by:
        body["sortBy"] = sort_by
    if sort_order:
        body["sortOrder"] = sort_order
    return body
