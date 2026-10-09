"""Egress records: one reconstructable record per outbound call that leaves digillm.

Counsel's question is "what left the process", and for a long time the honest
answer was "we cannot say". This module is that answer: every provider call
that reaches the wire produces exactly one :class:`EgressRecord`, saying where
it went, what was decided, which Art. 9 categories were hit, and a keyed
digest of what was sent.

The record deliberately never carries the payload. A copy of the outbound
messages in a log file is not an audit trail, it is a second copy of the data
with weaker access control than the database it came from. What the record
does carry is ``HMAC-SHA256`` over the canonical outbound messages under a
pepper that never leaves the deployment, so two records can be compared for
"same messages on the wire" while a reader holding a candidate list cannot
rank it. The digest covers the ``messages`` array only, never the whole
request kwargs: two calls with identical messages but different ``tools``,
``temperature`` or ``model`` share a digest. If the pepper is missing the record says ``digest_algorithm: "absent"``
rather than quietly falling back to an unkeyed hash, which would be a lookup
table for every value that has ever been sent.

This leaf does not screen anything. ``decision`` is ``unscreened`` on every
call that reaches the wire and ``cache_hit`` on the path where nothing left.
That is the honest current value, and it is the evidence a later filter will be
judged against: the day ``unscreened`` stops appearing, someone has to justify
it.

Three limits of the record, stated here so no reader over-reads it:

* Granularity is one digillm provider attempt, not one HTTP packet. The OpenAI
  SDK retries a single ``create()`` internally (429 / 5xx / connect errors), so
  one record can stand for more than one request on the wire. Counting packets
  is the SDK's job, and it has no hook to offer.
* ``outcome`` for a streaming attempt is ``started``: the record is written when
  the request is accepted, before the stream is read, because the payload has
  already left at that point and a later edit is impossible on a frozen record.
  The terminal result of the stream is in the telemetry record, joinable on
  ``call_id``. Reporting ``succeeded`` here would be a lie for the streams that
  die mid-flight, which is precisely the case counsel asks about.
* A failed attempt is recorded even when it failed before the wire (DNS, local
  serialization). That over-counts rather than under-counts on purpose: an
  egress ledger that misses the calls it could not prove went is worse than one
  that lists the ones it could not prove did not.

Configuration (environment):

* ``DIGILLM_EGRESS_DIGEST_KEY`` -- the HMAC pepper. Minimum
  :data:`MIN_DIGEST_KEY_LENGTH` characters; unset or too short means
  ``digest_algorithm: "absent"`` and ``payload_digest: null``. There is no
  unkeyed fallback, by design.
* ``DIGILLM_EGRESS_LOG_PATH`` -- JSONL sink path. Defaults to
  ``digiquant/results/egress/records.jsonl`` at the repository root, following
  the ``digiquant/results/`` convention. The literal value ``off`` disables
  the file sink.

Delivery is always fail-soft: neither a registered observer nor a failing disk
may break an LLM call. The file sink is the default because "the audit trail
exists" is the deliverable, and a callback nobody registers is not evidence.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import logging
import os
import threading
from collections.abc import Iterable
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, model_validator

logger = logging.getLogger(__name__)

DIGEST_KEY_ENV = "DIGILLM_EGRESS_DIGEST_KEY"
EGRESS_LOG_PATH_ENV = "DIGILLM_EGRESS_LOG_PATH"

#: Short keys make an HMAC as guessable as its candidate list. 32 characters is
#: the floor, not a recommendation.
MIN_DIGEST_KEY_LENGTH = 32

#: The literal destination for a call that never left the process.
NO_EGRESS_DESTINATION = "none"

#: A client that carried no resolvable base URL. Deliberately *not*
#: :data:`NO_EGRESS_DESTINATION`: conflating the two would turn "we do not know
#: where this went" into "nothing went", which is the one thing the record must
#: never claim.
UNKNOWN_DESTINATION = "unknown"

_SINK_LOCK = threading.Lock()
_HEX_DIGITS = frozenset("0123456789abcdef")


class EgressDecision(StrEnum):
    """What screening decided about one outbound payload.

    ``UNSCREENED`` is the only value a call can get today, and it is the point
    of this leaf: it is the evidence that outbound egress is unscreened rather
    than screened-and-clean. ``PASS``, ``MASKED`` and ``REFUSED`` exist so a
    later filter has somewhere to write its verdict without changing this
    record's shape. ``CACHE_HIT`` is the no-egress path.
    """

    UNSCREENED = "unscreened"
    PASS = "pass"
    MASKED = "masked"
    REFUSED = "refused"
    CACHE_HIT = "cache_hit"


class DigestAlgorithm(StrEnum):
    """How :attr:`EgressRecord.payload_digest` was produced."""

    HMAC_SHA256 = "hmac-sha256"
    ABSENT = "absent"


class EgressCategoryId(StrEnum):
    """The closed set of Art. 9 categories a record may reference.

    Duplicated here on purpose: digillm must not import ``digibase``, and a
    record that could hold free text would be a record that could hold a
    matched value.
    """

    HEALTH = "health"
    GENETIC = "genetic"
    BIOMETRIC = "biometric"
    RACIAL_OR_ETHNIC_ORIGIN = "racial_or_ethnic_origin"
    POLITICAL_OPINIONS = "political_opinions"
    RELIGIOUS_OR_PHILOSOPHICAL_BELIEFS = "religious_or_philosophical_beliefs"
    TRADE_UNION_MEMBERSHIP = "trade_union_membership"
    SEX_LIFE_OR_SEXUAL_ORIENTATION = "sex_life_or_sexual_orientation"


ART9_CATEGORY_IDS: frozenset[EgressCategoryId] = frozenset(EgressCategoryId)


class EgressRecord(BaseModel):
    """One outbound call, recorded without its payload.

    Frozen and ``extra="forbid"``: a record that can grow a new field is a
    record that can grow a ``prompt`` field, and a record that carries the
    prompt is a liability.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    ts: AwareDatetime
    call_id: UUID
    attempt_id: UUID
    #: Resolved provider base URL with any userinfo stripped, ``"none"`` when
    #: nothing was sent, or ``"unknown"`` when the client carried no base URL.
    destination: str
    provider: str
    model: str
    purpose: str
    decision: EgressDecision = EgressDecision.UNSCREENED
    category_ids: tuple[EgressCategoryId, ...] = ()
    payload_digest: str | None = None
    digest_algorithm: DigestAlgorithm = DigestAlgorithm.ABSENT
    cache_status: str
    #: ``succeeded`` / ``failed`` / ``cancelled``, or ``started`` for a streaming
    #: request whose body was accepted but whose stream had not been read yet --
    #: see the module docstring on why that one is not reported as ``succeeded``.
    outcome: str

    @model_validator(mode="after")
    def _validate_shape(self) -> EgressRecord:
        if self.ts.utcoffset() != dt.timedelta(0):
            raise ValueError("egress record timestamps must be UTC")
        if not self.destination:
            raise ValueError("egress record destination must not be empty")

        digest = self.payload_digest
        if self.digest_algorithm is DigestAlgorithm.HMAC_SHA256:
            if digest is None or len(digest) != 64 or not set(digest) <= _HEX_DIGITS:
                raise ValueError("hmac-sha256 records require a full 64-character hex digest")
        elif digest is not None:
            raise ValueError("an absent digest algorithm must not carry a payload_digest")

        if self.decision is EgressDecision.CACHE_HIT:
            if self.destination != NO_EGRESS_DESTINATION:
                raise ValueError(
                    "a cache hit never left the process, so destination must be 'none'"
                )
        elif self.destination == NO_EGRESS_DESTINATION:
            raise ValueError("only a cache hit may use the 'none' destination")

        return self


class EgressObserver(Protocol):
    """A sink for egress records. Implementations may raise; digillm swallows it."""

    def __call__(self, record: EgressRecord) -> None:
        raise NotImplementedError


_egress_observer: EgressObserver | None = None


def set_egress_observer(observer: EgressObserver | None) -> None:
    """Register a process-wide egress sink, or ``None`` to unregister.

    Registration is a convenience for callers that want records in-process; it
    is not what makes the audit trail exist. The JSONL sink writes whether or
    not anyone registers.
    """
    global _egress_observer
    _egress_observer = observer


def canonical_payload_bytes(payload: Any) -> bytes:
    """Serialize a payload deterministically, so digests compare across runs.

    Deterministic for JSON-native payloads (outbound messages are dicts of
    strings). ``default=str`` keeps an exotic value from losing the whole
    record -- ``record_egress`` drops the record when serialization raises,
    which is worse than a weak digest -- but its ``str()`` coercion can embed
    a memory address, so digests over non-JSON-native values may not reproduce
    across processes. Do not remove it without replacing that guarantee.
    """
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    ).encode("utf-8")


def compute_payload_digest(
    payload: Any, *, key: str | None = None
) -> tuple[str | None, DigestAlgorithm]:
    """Return ``(digest, algorithm)`` for ``payload`` under ``key``.

    ``key`` defaults to :data:`DIGEST_KEY_ENV`. When it is unset or shorter
    than :data:`MIN_DIGEST_KEY_LENGTH` the result is ``(None, "absent")``. There
    is no unkeyed fallback: an unkeyed hash of a low-entropy value is the value
    looked up in a table, and a silent fallback would hide that.
    """
    pepper = os.environ.get(DIGEST_KEY_ENV, "") if key is None else key
    pepper = pepper.strip()
    if len(pepper) < MIN_DIGEST_KEY_LENGTH:
        return None, DigestAlgorithm.ABSENT
    digest = hmac.new(
        pepper.encode("utf-8"), canonical_payload_bytes(payload), hashlib.sha256
    ).hexdigest()
    return digest, DigestAlgorithm.HMAC_SHA256


def default_sink_path() -> Path | None:
    """Resolve the JSONL sink path, or ``None`` when the sink is turned off."""
    configured = os.environ.get(EGRESS_LOG_PATH_ENV)
    if configured is not None:
        cleaned = configured.strip()
        if cleaned.lower() in {"off", "none"}:
            return None
        if cleaned:
            return Path(cleaned)
    return _checkout_default_sink_path()


@lru_cache(maxsize=1)
def _checkout_default_sink_path() -> Path:
    """The checkout-relative default, resolved once per process.

    Cached because the fallback walks the filesystem on every record and the
    answer cannot change while the process lives. The configured-env branch above
    is deliberately *not* cached, so an operator setting the variable still wins
    immediately.
    """
    # Walk up from the package to the checkout root (the one holding digiquant or
    # .git). Installed into site-packages there is no such root, so fall back to the
    # working directory rather than writing records into the virtualenv.
    for parent in Path(__file__).resolve().parents:
        if (parent / "digiquant").is_dir() or (parent / ".git").exists():
            return parent / "digiquant" / "results" / "egress" / "records.jsonl"
    return Path.cwd() / "digiquant" / "results" / "egress" / "records.jsonl"


def _write_sink_line(path: Path, record: EgressRecord) -> None:
    line = record.model_dump_json()
    with _SINK_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{line}\n")


def emit_egress_record(record: EgressRecord) -> bool:
    """Deliver ``record`` to the registered observer and the JSONL sink.

    Returns whether it was delivered somewhere. Never raises: a broken
    observer or a read-only disk must not take down an LLM call.
    """
    delivered = False
    observer = _egress_observer
    if observer is not None:
        try:
            observer(record)
            delivered = True
        except Exception as observer_error:
            logger.debug("egress observer raised: %s", type(observer_error).__name__)

    try:
        path = default_sink_path()
    except Exception as path_error:
        # Warning, not debug: losing the sink is losing the evidence, and an audit
        # trail that quietly stopped persisting is the one failure this leaf exists
        # to prevent. Only the exception type is logged -- never a message.
        logger.warning("egress sink path unavailable: %s", type(path_error).__name__)
        return delivered

    if path is not None:
        try:
            _write_sink_line(path, record)
            delivered = True
        except Exception as sink_error:
            logger.warning("egress sink write failed: %s", type(sink_error).__name__)
    return delivered


def record_egress(
    *,
    call_id: UUID,
    attempt_id: UUID,
    destination: str,
    provider: str,
    model: str,
    purpose: str,
    cache_status: str,
    outcome: str,
    decision: EgressDecision = EgressDecision.UNSCREENED,
    category_ids: Iterable[EgressCategoryId] = (),
    payload: Any = None,
) -> EgressRecord | None:
    """Build and emit one egress record.

    ``payload`` is the outbound messages as they went on the wire -- already
    truncated where digillm truncates -- and is used only to derive the digest.
    It is never stored, logged, or attached to an exception. Pass
    ``payload=None`` for the no-egress path.

    There is deliberately no way to pass a pre-computed digest. Any caller-supplied
    string would be indistinguishable from a keyed one, which is precisely the
    unkeyed-fallback hole this module refuses to offer.

    Returns the record, or ``None`` if it could not even be built; delivery
    failures are swallowed so the call proceeds either way.
    """
    try:
        if payload is None:
            digest, algorithm = None, DigestAlgorithm.ABSENT
        else:
            digest, algorithm = compute_payload_digest(payload)
        record = EgressRecord(
            ts=dt.datetime.now(dt.UTC),
            call_id=call_id,
            attempt_id=attempt_id,
            destination=destination,
            provider=provider,
            model=model,
            purpose=purpose,
            decision=decision,
            category_ids=tuple(dict.fromkeys(category_ids)),
            payload_digest=digest,
            digest_algorithm=algorithm,
            cache_status=cache_status,
            outcome=outcome,
        )
    except Exception as build_error:
        # Warning, not debug: a systematic build failure (an unserialisable payload,
        # a bad destination) empties the ledger silently at debug level, and an
        # audit trail that looks complete while recording nothing is worse than none.
        logger.warning("egress record not built: %s", type(build_error).__name__)
        return None

    emit_egress_record(record)
    return record


__all__ = [
    "ART9_CATEGORY_IDS",
    "DIGEST_KEY_ENV",
    "EGRESS_LOG_PATH_ENV",
    "MIN_DIGEST_KEY_LENGTH",
    "NO_EGRESS_DESTINATION",
    "UNKNOWN_DESTINATION",
    "DigestAlgorithm",
    "EgressCategoryId",
    "EgressDecision",
    "EgressObserver",
    "EgressRecord",
    "canonical_payload_bytes",
    "compute_payload_digest",
    "default_sink_path",
    "emit_egress_record",
    "record_egress",
    "set_egress_observer",
]
