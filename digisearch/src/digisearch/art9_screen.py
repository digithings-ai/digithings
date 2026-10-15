"""Art. 9 screening hop for chat transcripts (DIG-1176 leaf 12b).

digichat posts a transcript here before it reaches Postgres. This endpoint is a
thin adapter over :mod:`digibase.art9`: it bounds the request, calls the
detector exactly once, and maps the verdict onto a small response.

Fail closed. A transcript reaches the caller's storage only on a 200 whose body
carries ``decision == "allow"``. Everything else refuses. ``mask`` is treated as
a refusal: in v1 there is no lawful basis to store a masked transcript, and the
response deliberately carries no redacted value for the caller to store.

The response carries category identifiers and a stable reason code only. It never
carries the matched value, a tenant, an ownerUserSub or a client name, and this
module never logs the screened payload.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from digibase.art9 import ScreenResult, audit_record, screen_request
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Bounds on the already-validated caller payload. Exceeding either refuses the
# request before any screening work happens.
MAX_BODY_BYTES = 1024 * 1024  # 1 MiB
MAX_MESSAGES = 500

router = APIRouter(tags=["art9"])

CODE_REFUSED = "art9_refused"
CODE_UNAVAILABLE = "art9_screen_unavailable"
CODE_TOO_LARGE = "art9_payload_too_large"


class ScreenRequest(BaseModel):
    """The transcript as digichat validated it. Messages stay opaque here."""

    surface: str = Field(min_length=1)
    conversation_id: str = Field(min_length=1)
    messages: list[dict[str, Any]] = Field(min_length=1)
    exception_ref: str | None = None


class ScreenResponse(BaseModel):
    """The verdict. Identifiers and a stable code only, never a matched value."""

    decision: str
    categories: list[str]
    reason: str
    exception_ref: str | None = None


def _audit(result: ScreenResult) -> None:
    """Write one audit line. No outcome is silent, including the happy path.

    The audit view comes from :func:`audit_record`, the only shape allowed to
    leave this module. It carries identifiers and codes, never the payload, so
    the transcript is never written to a log.
    """
    logger.info("art9 screen %s", json.dumps(audit_record(result), sort_keys=True))


def _refusal(status: int, code: str, result: ScreenResult | None) -> JSONResponse:
    """Build a refusal, recording one audit line when a verdict exists.

    A refusal that carries a verdict returns the same identifier fields the
    caller gets on success -- decision, categories, reason, exception_ref -- so a
    refused caller can log why. It never returns ``redacted``: the matched value
    does not leave this process on any path.

    A verdict reached before the refusal is audited. A request refused before
    screening (too large) or lost to a failing hop has no verdict, so there is
    nothing for audit_record to describe; the status code is the record.
    """
    if result is None:
        return JSONResponse(status_code=status, content={"code": code})

    _audit(result)
    return JSONResponse(
        status_code=status,
        content={
            "code": code,
            "decision": result.decision,
            "categories": list(result.categories),
            "reason": result.reason,
            "exception_ref": result.exception_ref,
        },
    )


@router.post("/internal/art9/screen", response_model=ScreenResponse, status_code=200)
def screen(req: ScreenRequest) -> ScreenResponse | JSONResponse:
    """Screen one transcript.

    200 allow, 422 on a policy refusal (including mask), 413 when the request is
    over a declared bound, 502 when the screening hop fails.
    """
    raw = req.model_dump_json().encode("utf-8")
    if len(raw) > MAX_BODY_BYTES or len(req.messages) > MAX_MESSAGES:
        return _refusal(413, CODE_TOO_LARGE, None)

    try:
        # One attempt, no retry: a screening hop that retries is a screening hop
        # that eventually admits. screen_request is a module global so a failing
        # hop can be exercised without a network.
        result = screen_request(
            {"surface": req.surface, "messages": req.messages},
            exception_ref=req.exception_ref,
        )
    except Exception:
        # The traceback is deliberately not logged: an exception raised from
        # inside the detector could quote payload text.
        logger.warning("art9 screen hop unavailable")
        return _refusal(502, CODE_UNAVAILABLE, None)

    if result.decision != "allow":
        # "mask" lands here too: v1 stores nothing for it.
        return _refusal(422, CODE_REFUSED, result)

    _audit(result)
    return ScreenResponse(
        decision=result.decision,
        categories=list(result.categories),
        reason=result.reason,
        exception_ref=result.exception_ref,
    )
