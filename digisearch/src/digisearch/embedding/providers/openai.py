"""OpenAI embedding provider."""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from digisearch.embedding.base import EmbeddingProvider

logger = logging.getLogger(__name__)

#: Recorded verbatim on every egress record this module emits. ``purpose`` is
#: digillm's ``CallPurpose.EMBEDDING`` value; the test suite pins the literal
#: against that enum so the two vocabularies cannot drift apart unnoticed.
_EGRESS_PROVIDER = "openai"
_EGRESS_PURPOSE = "embedding"

#: This class sits *under* ``EmbeddingCache`` -- the factory wires
#: EmbeddingCache -> BatchEmbedder -> provider -- so a call that reaches here was
#: not served from cache. It is the same ``miss`` digillm records for an uncached
#: chat completion. It can never be ``hit``: a cache hit returns without calling
#: this provider, which is why this module never records a ``cache_hit`` decision.
_EGRESS_CACHE_STATUS = "miss"

#: Compared as plain strings: ``EgressDecision`` is a ``StrEnum``, so this is the
#: same comparison as testing membership, without importing digillm here.
_REFUSED = "refused"
_MASKED = "masked"


def _verdict(client: Any) -> tuple[Any, tuple[str, ...]]:
    """The screening verdict the digillm screen recorded on this client, if any.

    Returns UNSCREENED-equivalent when there is no client, no screen, or no call
    screened yet -- so every caller gets the same three-way answer without this
    module ever importing digillm's types at module scope.
    """
    screened = getattr(client, "last_screen", None)
    # A real verdict carries a str-enum decision. A client double that
    # fabricates attributes on access answers the getattr with a mock, and
    # recording that would put a decision in the ledger that no screen made --
    # and would fail to build the record at all. The check lives here because
    # this module keeps no dependency on digillm at module scope, so the
    # outcome type it would want to test against is not in scope either.
    if screened is None or not isinstance(getattr(screened, "decision", None), str):
        return None, ()
    return screened.decision, tuple(screened.category_ids)


class OpenAIEmbedder(EmbeddingProvider):
    """OpenAI text-embedding API.

    This is the second outbound model surface in the stack that does not go
    through ``digillm``: it drives ``openai.OpenAI`` directly, so a record emitted
    only inside ``digillm.client`` never sees it and "every outbound model call"
    would be false. Every call that reaches the wire therefore emits one
    :func:`digillm.egress_record.record_egress`, reusing the stack's single record
    and its single keyed digest. There is no second digest implementation here,
    and ``record_egress`` deliberately offers no way to pass a pre-computed one.

    Four properties this module is responsible for:

    * The record carries destination, provider, model, decision, category ids and
      the keyed digest. It never carries the texts: they are handed to digillm
      only to derive the digest, which is dropped.
    * An empty batch returns ``[]`` and records nothing. ``embed()`` returns before
      a client is built, so nothing leaves the process and there is no attempt to
      describe.
    * A call that fails is recorded with ``outcome="failed"`` and the original
      exception is re-raised. digillm's module documents that an attempt which
      failed before the wire is still recorded, because a ledger missing the calls
      it cannot prove went is worse than one listing calls it cannot prove did
      not.
    * ``decision`` is ``unscreened`` and ``category_ids`` is empty. Nothing screens
      this path, and recording an Art. 9 category that no screener actually matched
      would be a fabricated finding.

    The ``digillm`` import is lazy and sits inside the recording call, not at
    module scope. Module scope would make ``import
    digisearch.embedding.providers.openai`` raise ``ModuleNotFoundError`` in the
    deployed image -- which installs ``[server,ingestion,azure,chroma,web-search]``
    and neither ``digillm`` nor ``openai`` -- introducing a new failure mode into a
    module that imports cleanly today. It also cannot silently degrade into "no
    record in production" on a path that reaches the wire, which is what the lazy
    import bought: ``openai`` and ``digillm`` are declared in the *same*
    ``[embedding]`` extra, so a client that built implies a digillm that imports.
    If the guard below ever fires, the install has neither, and it says so at
    warning level rather than dropping the evidence quietly.
    """

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.model = model
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._base_url = base_url or os.environ.get("OPENAI_API_BASE")
        self._client: object | None = None

    @property
    def dimensions(self) -> int:
        if "text-embedding-3-small" in self.model:
            return 1536
        if "text-embedding-3-large" in self.model:
            return 3072
        if "text-embedding-ada-002" in self.model:
            return 1536
        return 1536  # default

    def _get_client(self) -> object:
        if self._client is None:
            from openai import OpenAI

            kw: dict = {"api_key": self._api_key}
            if self._base_url:
                kw["base_url"] = self._base_url
            self._client = self._screened(OpenAI(**kw))
        return self._client

    @staticmethod
    def _screened(inner: object) -> object:
        """Wrap the constructed client in digillm's Art. 9 egress screen.

        Lazy and non-raising, like every other digillm import in this module: the
        deployed image installs neither digillm nor openai, so this must not turn
        into a new import-time failure in a module that imports cleanly today. A
        digillm that cannot be imported leaves the client exactly as it was --
        unscreened, and recorded as such.
        """
        try:
            from digillm.client import screened_client
        except ImportError as unavailable:
            logger.warning(
                "egress screen not installed: digillm is not importable (%s)",
                type(unavailable).__name__,
            )
            return inner
        return screened_client(inner)

    def _resolved_destination(self) -> str:
        """The base URL this call will dial, with credentials removed.

        The openai client embeds any userinfo and query string in the URL it
        requests, so recording ``self._base_url`` verbatim would write an API key
        into the audit trail -- the one place a secret is guaranteed to be copied
        somewhere new. Falls back to digillm's ``"unknown"`` when no usable base URL
        is configured, never ``"none"``: ``"none"`` is reserved for a call that did
        not leave the process, and "we do not know where it went" must never be
        laundered into "nothing went".
        """
        from digillm.egress_record import UNKNOWN_DESTINATION

        base = self._base_url
        if not base:
            return UNKNOWN_DESTINATION
        try:
            parts = urlsplit(base)
            host = parts.hostname
            port = parts.port
        except ValueError:
            return UNKNOWN_DESTINATION
        if not parts.scheme or not host:
            return UNKNOWN_DESTINATION
        netloc = f"{host}:{port}" if port else host
        return urlunsplit((parts.scheme, netloc, parts.path, "", ""))

    def _record_call(
        self,
        *,
        call_id: uuid.UUID,
        attempt_id: uuid.UUID,
        payload: Any,
        outcome: str,
        decision: Any = None,
        category_ids: tuple[str, ...] = (),
    ) -> None:
        """Emit this provider attempt's egress record. Never raises."""
        try:
            from digillm.egress_record import EgressDecision, record_egress
        except ImportError as unavailable:
            # Unreachable while a client exists -- see the class docstring. Only the
            # exception *type* is logged; a message could carry the module path, and
            # this is a warning that has to stay safe to read in a log aggregator.
            logger.warning(
                "egress record not emitted: digillm is not installed (%s)",
                type(unavailable).__name__,
            )
            return
        if decision is None:
            decision = EgressDecision.UNSCREENED
        record_egress(
            call_id=call_id,
            attempt_id=attempt_id,
            destination=self._resolved_destination(),
            provider=_EGRESS_PROVIDER,
            model=self.model,
            purpose=_EGRESS_PURPOSE,
            cache_status=_EGRESS_CACHE_STATUS,
            outcome=outcome,
            decision=decision,
            category_ids=category_ids,
            payload=payload,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        call_id = uuid.uuid4()
        attempt_id = uuid.uuid4()
        # What goes on the wire: the model plus the batch. digillm canonicalises it,
        # digests it and drops it. Nothing on this side stores or logs it.
        payload: Any = {"model": self.model, "input": list(texts)}
        client: Any = None
        try:
            client = self._get_client()
            r = client.embeddings.create(model=self.model, input=texts)
        except Exception:
            decision, categories = _verdict(client)
            # A refusal never reached the wire, so it is not a failed wire
            # attempt: recording it as one would put a call in the ledger that
            # never reached the provider, the mirror of the error this module
            # exists to avoid. The destination stays the real one -- "none" is
            # reserved for a cache hit, and "where it would have gone" is exactly
            # what a data-subject request needs to know.
            self._record_call(
                call_id=call_id,
                attempt_id=attempt_id,
                payload=payload,
                outcome="refused" if decision == _REFUSED else "failed",
                decision=decision,
                category_ids=categories,
            )
            raise
        vectors = [d.embedding for d in r.data]
        decision, categories = _verdict(client)
        # Digest what went on the wire -- the redaction, when one was substituted.
        sent = payload
        if decision == _MASKED:
            sent = {"model": self.model, "input": client.last_screen.masked_payload}
        self._record_call(
            call_id=call_id,
            attempt_id=attempt_id,
            payload=sent,
            outcome="succeeded",
            decision=decision,
            category_ids=categories,
        )
        return vectors
