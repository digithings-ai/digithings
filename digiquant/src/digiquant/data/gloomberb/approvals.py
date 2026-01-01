"""Public wire model for a two-phase order ticket.

The private backend mints and redeems the HMAC token; the public repo carries
only the ticket model the MCP contract exchanges.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["ApprovalError", "OrderTicket"]


class ApprovalError(ValueError):
    """A ticket/token failure: malformed, expired, replayed, or unsigned."""


class OrderTicket(BaseModel):
    """The order a preview minted and the token is bound to."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str = Field(min_length=1, max_length=32)
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0)
    order_type: Literal["market", "limit"] = "market"
    limit_price: float | None = Field(default=None, gt=0)
    exchange: str | None = None
    jti: str = Field(default_factory=lambda: uuid.uuid4().hex)
