"""DigiSearch HTTP client helpers for DigiGraph (direct ``POST /query``).

Orchestrator tool *definitions* and hub dispatch live in DigiSearch
(``/v1/orchestrator_tools``, ``/v1/orchestrator_invoke``). This module keeps
thin ``POST /query`` helpers for code paths that call search without the
orchestrator manifest (e.g. research node utilities).
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from digibase.http import outbound_service_headers

from digigraph.circuit_breaker import CircuitBreaker, CircuitBreakerOpen

# Persistent sync client — reuses TCP connections across repeated search calls.
# Timeout of 15 s matches the previous per-call default.
_sync_client: httpx.Client | None = None
_cb = CircuitBreaker("digisearch", failure_threshold=5, recovery_timeout=30.0)


def _get_sync_client() -> httpx.Client:
    global _sync_client
    if _sync_client is None or _sync_client.is_closed:
        _sync_client = httpx.Client(timeout=15.0)
    return _sync_client


def digisearch(
    text: str,
    index_name: str = "default",
    top_k: int = 10,
    mode: str = "hybrid",
    filter: str | None = None,
    filters: list[dict[str, Any]] | None = None,
    columns: list[str] | None = None,
    response_mode: str = "full",
    summarize_if_over: int | None = None,
    facets: list[str] | None = None,
    highlight_fields: list[str] | None = None,
    order_by: list[str] | None = None,
    skip: int = 0,
    include_total_count: bool = False,
    request_id: str | None = None,
    authorization_bearer: str | None = None,
) -> dict[str, Any] | None:
    """Search DigiSearch. Returns raw response dict (results, query, index_name, total, summary?, facets?) or None."""
    base_url = os.environ.get("DIGISEARCH_URL", "").strip()
    if not base_url:
        return None
    url = f"{base_url.rstrip('/')}/query"
    payload: dict[str, Any] = {"text": text, "index_name": index_name, "top_k": top_k, "mode": mode}
    if filter is not None and filter.strip():
        payload["filter"] = filter.strip()
    if filters:
        payload["filters"] = filters
    if facets:
        payload["facets"] = facets
    if highlight_fields:
        payload["highlight_fields"] = highlight_fields
    if order_by:
        payload["order_by"] = order_by
    if skip:
        payload["skip"] = skip
    if include_total_count:
        payload["include_total_count"] = True
    if columns:
        payload["columns"] = columns
    if response_mode and response_mode.strip().lower() != "full":
        payload["response_mode"] = response_mode.strip().lower()
    if summarize_if_over is not None:
        payload["summarize_if_over"] = summarize_if_over
    bearer = str(authorization_bearer).strip() if authorization_bearer else None
    headers = outbound_service_headers(request_id, bearer)
    try:
        with _cb:
            r = _get_sync_client().post(url, json=payload, headers=headers)
            r.raise_for_status()
            return r.json()
    except CircuitBreakerOpen:
        return None
    except Exception:
        return None


async def async_digisearch(
    text: str,
    index_name: str = "default",
    top_k: int = 10,
    mode: str = "hybrid",
    filter: str | None = None,
    filters: list[dict[str, Any]] | None = None,
    columns: list[str] | None = None,
    response_mode: str = "full",
    summarize_if_over: int | None = None,
    facets: list[str] | None = None,
    highlight_fields: list[str] | None = None,
    order_by: list[str] | None = None,
    skip: int = 0,
    include_total_count: bool = False,
    request_id: str | None = None,
    authorization_bearer: str | None = None,
) -> dict[str, Any] | None:
    """Async variant of :func:`digisearch`. Uses ``httpx.AsyncClient`` to avoid blocking the event loop."""
    base_url = os.environ.get("DIGISEARCH_URL", "").strip()
    if not base_url:
        return None
    url = f"{base_url.rstrip('/')}/query"
    payload: dict[str, Any] = {"text": text, "index_name": index_name, "top_k": top_k, "mode": mode}
    if filter is not None and filter.strip():
        payload["filter"] = filter.strip()
    if filters:
        payload["filters"] = filters
    if facets:
        payload["facets"] = facets
    if highlight_fields:
        payload["highlight_fields"] = highlight_fields
    if order_by:
        payload["order_by"] = order_by
    if skip:
        payload["skip"] = skip
    if include_total_count:
        payload["include_total_count"] = True
    if columns:
        payload["columns"] = columns
    if response_mode and response_mode.strip().lower() != "full":
        payload["response_mode"] = response_mode.strip().lower()
    if summarize_if_over is not None:
        payload["summarize_if_over"] = summarize_if_over
    bearer = str(authorization_bearer).strip() if authorization_bearer else None
    headers = outbound_service_headers(request_id, bearer)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            return r.json()
    except Exception:
        return None


def digisearch_fetch_all(
    text: str,
    index_name: str = "default",
    page_size: int = 500,
    max_results: int | None = None,
    mode: str = "hybrid",
    filter: str | None = None,
    filters: list[dict[str, Any]] | None = None,
    columns: list[str] | None = None,
    order_by: list[str] | None = None,
    request_id: str | None = None,
    authorization_bearer: str | None = None,
) -> dict[str, Any] | None:
    """
    Fetch all matching documents by paginating until exhausted. Returns combined results and total.
    Use for 'retrieve them all' queries (e.g. all emails from user X). Writes to Digistore when run_data_dir set.
    """
    all_results: list[dict] = []
    skip = 0
    total_so_far = 0
    total_estimate: int | None = None
    while True:
        data = digisearch(
            text=text,
            index_name=index_name,
            top_k=page_size,
            mode=mode,
            filter=filter,
            filters=filters,
            columns=columns,
            order_by=order_by,
            skip=skip,
            include_total_count=True,
            request_id=request_id,
            authorization_bearer=authorization_bearer,
        )
        if not data:
            break
        results = data.get("results", [])
        if not results:
            break
        all_results.extend(results)
        total_so_far += len(results)
        total_estimate = data.get("total")
        if total_estimate is not None and total_so_far >= total_estimate:
            break
        if max_results is not None and total_so_far >= max_results:
            all_results = all_results[:max_results]
            break
        if len(results) < page_size:
            break
        skip += page_size
    return {
        "results": all_results,
        "total": len(all_results),
        "query": text,
        "index_name": index_name,
    }
