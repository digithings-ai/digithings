"""Call DigiSearch ``POST /v1/research_turn`` from the hub."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
from digibase.http import outbound_service_headers
from digibase.http_client import sync_client

logger = logging.getLogger(__name__)


def call_research_turn(
    *,
    base_url: str,
    payload: dict[str, Any],
    request_id: str | None,
    bearer_token: str | None,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """POST research turn; returns JSON body or ``{ok: False, error, status_code}``."""
    url = f"{base_url.rstrip('/')}/v1/research_turn"
    headers = outbound_service_headers(request_id, bearer_token)
    headers["Content-Type"] = "application/json"
    try:
        with sync_client(timeout=timeout) as client:
            r = client.post(url, json=payload, headers=headers)
            r.raise_for_status()
            body = r.json()
    except httpx.HTTPStatusError as e:
        try:
            detail: Any = e.response.json()
        except (json.JSONDecodeError, ValueError, TypeError):
            detail = e.response.text
        logger.warning("DigiSearch research_turn HTTP %s: %s", e.response.status_code, detail)
        return {"ok": False, "status_code": e.response.status_code, "error": detail}
    except httpx.RequestError as e:
        logger.warning("DigiSearch research_turn request error: %s", e)
        return {"ok": False, "status_code": None, "error": str(e)}
    if isinstance(body, dict):
        body.setdefault("ok", True)
        return body
    return {"ok": True, "data": body}
