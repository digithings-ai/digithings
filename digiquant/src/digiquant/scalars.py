"""Scalar coercions shared across digiquant (pure, no I/O).

These lived as private copies in eight modules, and the copies had started to
disagree on what a bad value means — ``_opt_float`` returned ``None`` in the
portfolio writers and raised in ``tearsheet_data``, so the same corrupt row
could be silently dropped from a book and crash a tearsheet. One helper per
*policy*, named for the policy, so a caller picks the failure mode on purpose:

- :func:`opt_float` / :func:`opt_decimal` — lenient: garbage becomes ``None``.
- :func:`opt_float_strict` / :func:`decimal_or_raise` — strict: garbage raises.

Never guess which one a call site wants; read the name.
"""

from __future__ import annotations

from decimal import Decimal

_CASH = "CASH"


def is_cash(ticker: object) -> bool:
    """Whether ``ticker`` names the cash sleeve.

    Takes ``object`` on purpose: the unguarded copies did ``ticker.strip()`` and
    raised ``AttributeError`` when a broker or LLM payload carried a non-string
    ticker. A non-string is never cash.
    """
    return isinstance(ticker, str) and ticker.strip().upper() == _CASH


def opt_float(value: object) -> float | None:
    """Coerce to ``float``, or ``None`` for ``None`` / non-numeric values."""
    try:
        return float(value) if value is not None else None  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def opt_float_strict(value: object) -> float | None:
    """Coerce to ``float``; ``None`` passes through, anything else must be numeric.

    The strict sibling of :func:`opt_float`. Callers that would rather crash than
    publish a tearsheet with a silently missing statistic use this one.
    """
    return None if value is None else float(value)  # type: ignore[arg-type]


def opt_decimal(raw: object) -> Decimal | None:
    """Coerce to ``Decimal`` via its string form, or ``None``.

    ``Decimal(str(raw))`` rather than ``Decimal(raw)``: Supabase returns
    numerics as ``str``/``int``/``float``, and ``Decimal(float)`` drags in the
    binary float's error.
    """
    if raw is None:
        return None
    try:
        return Decimal(str(raw))
    except (ArithmeticError, ValueError):
        return None


def decimal_or_raise(value: object) -> Decimal:
    """Exact ``Decimal`` from ``value``; raises on anything not representable."""
    return Decimal(str(value))


__all__ = [
    "decimal_or_raise",
    "is_cash",
    "opt_decimal",
    "opt_float",
    "opt_float_strict",
]
