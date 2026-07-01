"""Shared HTTP error handling for vertical orchestrator hubs."""

from __future__ import annotations

import json
import logging

import httpx

logger = logging.getLogger(__name__)

HUB_CLIENT_ERRORS = (
    httpx.HTTPStatusError,
    httpx.RequestError,
    json.JSONDecodeError,
    OSError,
    TypeError,
    ValueError,
)


def log_manifest_fetch_failure(service: str, exc: BaseException) -> None:
    logger.warning("%s orchestrator_tools fetch failed: %s", service, exc)
