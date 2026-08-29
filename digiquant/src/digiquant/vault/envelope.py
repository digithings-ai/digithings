"""AES-256-GCM credential envelope (K3).

Sealed at-rest storage for secrets that only a runner job may ever open: broker OAuth
tokens and API-key pairs today (`brokers/connections.py`), BYOK LLM keys later (T2/T4
reuse this module unchanged). The envelope layer above the ``--- credential payloads ---``
banner is deliberately credential-agnostic: it seals and opens *bytes*, so a later work
package adds its own payload models beside :class:`OAuthCredential` /
:class:`ApiKeyCredential` without touching the crypto.

Envelope shape
--------------
AES-256-GCM (`cryptography`'s ``AESGCM``, the only AEAD used here), a fresh random 96-bit
nonce per seal, and the associated data bound to the row identity:

    aad = f"{workspace_id}:{broker}:{env}".encode("utf-8")

The AAD is what makes a ciphertext un-replayable onto a different connection row: moving
`workspace A / alpaca / paper`'s bytes onto `workspace B`'s row changes the AAD the opener
computes, GCM's tag check fails, and :class:`EnvelopeAuthenticationError` is raised — the
same failure a wrong master key or a truncated ciphertext produces. :func:`build_aad`
therefore rejects any component containing ``":"``, so the concatenation stays injective
(without that check ``("a:b", "c", "d")`` and ``("a", "b:c", "d")`` would share an AAD).

Master key
----------
``DIGIQUANT_VAULT_MASTER_KEY`` — base64, exactly 32 bytes after decode. There is no
default and no fallback: a missing or malformed value raises
:class:`VaultConfigurationError` at first use, so an unconfigured deployment cannot seal
credentials under a weak key or silently store them in the clear. The key is read from the
environment on every call rather than cached in a module global, so a rotated process
environment takes effect immediately and no long-lived copy of the key sits in module
state. ``DIGIQUANT_VAULT_KEY_ID`` (default ``"v1"``) names the key version and is stored
next to each ciphertext in ``broker_connections.key_id``; opening a row whose ``key_id``
does not match the loaded key fails closed with :class:`VaultKeyMismatchError` rather than
producing a confusing tag failure. Rotation (a second key plus a re-seal job) is out of
scope for K3 — this module only makes the version legible.

What this module never does
---------------------------
No log record, ``repr``, or exception message here carries plaintext. Secret-bearing
fields are declared ``repr=False``, so a payload model's ``repr`` shows only its ``kind``;
:func:`fingerprint` (8 hex characters) is the only display-safe artifact; and every
``ValidationError`` / ``InvalidTag`` raised underneath is re-raised with ``from None``
because a chained exception would put the library's own message — which can echo the
input it rejected — into the traceback. ``tests/dq/vault/test_envelope.py`` captures
logging and asserts the absence of plaintext across all of those surfaces.

Zeroization is deliberately *not* claimed. Python ``bytes`` and ``str`` are immutable and
may be copied by the interpreter, so a decrypted token cannot be reliably scrubbed from
process memory. What :func:`unseal_credential` provides instead is a bounded *lease*: the
plaintext is reachable only inside the ``with`` block, and the lease raises
:class:`CredentialLeaseExpiredError` on any access afterwards, so "callers must not
persist plaintext" is enforced at runtime rather than left as a comment.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Annotated, Final, Literal, TypeAlias

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, model_validator

MASTER_KEY_ENV: Final = "DIGIQUANT_VAULT_MASTER_KEY"
KEY_ID_ENV: Final = "DIGIQUANT_VAULT_KEY_ID"
DEFAULT_KEY_ID: Final = "v1"

MASTER_KEY_BYTES: Final = 32
NONCE_BYTES: Final = 12
GCM_TAG_BYTES: Final = 16
# A credential payload is a few hundred bytes of JSON. The cap is a fail-closed guard
# against a caller stuffing an unrelated blob (a response body, a document) into a column
# whose whole point is that it holds one small secret.
MAX_PLAINTEXT_BYTES: Final = 8192
FINGERPRINT_HEX_CHARS: Final = 8

_KEY_ID_PATTERN: Final = re.compile(r"^[a-z0-9][a-z0-9._-]{0,31}$")


class VaultError(Exception):
    """Base for every credential-vault failure a caller is expected to handle."""


class VaultConfigurationError(VaultError):
    """Master key is absent or malformed — the vault refuses to seal or open."""


class VaultKeyMismatchError(VaultError):
    """Envelope was sealed under a different ``key_id`` than the key now loaded."""


class EnvelopeAuthenticationError(VaultError):
    """GCM tag check failed: wrong key, wrong AAD, truncated or tampered ciphertext.

    Deliberately one exception for all four causes. Distinguishing them would tell an
    attacker which half of the guess was wrong, and no legitimate caller behaves
    differently: every case means "these bytes are not openable here", i.e. fail closed.
    """


class VaultPayloadError(VaultError):
    """Decrypted bytes were authentic but are not a valid credential payload."""


class CredentialLeaseExpiredError(VaultError):
    """A :class:`CredentialLease` was accessed after its ``with`` block closed."""


@dataclass(frozen=True, eq=False)
class MasterKey:
    """A loaded 32-byte AES-256 master key plus the ``key_id`` naming its version.

    ``eq=False`` so two keys are never compared with ``==`` (a non-constant-time
    comparison nothing here needs), and ``material`` is ``repr=False`` so neither a
    debugger dump nor a log line that interpolates this object can print the key.
    """

    key_id: str
    material: bytes = field(repr=False)

    def __repr__(self) -> str:
        return f"MasterKey(key_id={self.key_id!r})"


def _resolve_key_id(source: Mapping[str, str]) -> str:
    raw = (source.get(KEY_ID_ENV) or DEFAULT_KEY_ID).strip()
    if not _KEY_ID_PATTERN.match(raw):
        raise VaultConfigurationError(
            f"{KEY_ID_ENV} must match {_KEY_ID_PATTERN.pattern} "
            "(a short lowercase version label such as 'v1')"
        )
    return raw


def load_master_key(source: Mapping[str, str] | None = None) -> MasterKey:
    """Load the master key from ``source`` (defaults to ``os.environ``), or fail closed.

    ``source`` is injectable so tests never mutate the ambient process environment.
    Error messages name the variable and the expected shape but never echo the value.
    """
    env = os.environ if source is None else source
    raw = (env.get(MASTER_KEY_ENV) or "").strip()
    if not raw:
        raise VaultConfigurationError(
            f"{MASTER_KEY_ENV} is unset; the credential vault has no default key and "
            f"refuses to seal or open anything without {MASTER_KEY_BYTES} bytes of "
            "base64-encoded key material (generate with: openssl rand -base64 32)"
        )
    try:
        material = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        # `from None`: binascii's message can quote the offending input.
        raise VaultConfigurationError(
            f"{MASTER_KEY_ENV} is not valid base64; expected {MASTER_KEY_BYTES} bytes of "
            "base64-encoded key material"
        ) from None
    if len(material) != MASTER_KEY_BYTES:
        raise VaultConfigurationError(
            f"{MASTER_KEY_ENV} decodes to {len(material)} bytes; AES-256-GCM requires "
            f"exactly {MASTER_KEY_BYTES}"
        )
    return MasterKey(key_id=_resolve_key_id(env), material=material)


def build_aad(workspace_id: str, broker: str, env: str) -> bytes:
    """Associated data binding a ciphertext to one ``broker_connections`` row.

    ``f"{workspace_id}:{broker}:{env}"``, UTF-8 encoded. Components must be non-empty and
    colon-free so the join is injective — otherwise two different row identities could
    share an AAD, and the replay protection this AAD exists for would not hold for them.
    """
    for name, value in (("workspace_id", workspace_id), ("broker", broker), ("env", env)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"AAD component {name} must be a non-empty string")
        if ":" in value:
            raise ValueError(
                f"AAD component {name} must not contain ':' — the delimiter would make "
                "the workspace/broker/env binding ambiguous"
            )
    return f"{workspace_id}:{broker}:{env}".encode()


class _VaultModel(BaseModel):
    """Strict, immutable base: unknown fields rejected, instances frozen."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SealedEnvelope(_VaultModel):
    """One sealed payload: ciphertext (GCM tag appended), its nonce, and the ``key_id``.

    ``ciphertext``/``nonce`` are ``repr=False``: they are not plaintext, but there is no
    reason for either to reach a log line, and hiding them keeps every ``repr`` in this
    module fingerprint-only by construction. Both are ``strict=True`` so a ``str`` is
    never silently UTF-8 encoded into a key-shaped field.
    """

    ciphertext: Annotated[bytes, Field(strict=True, repr=False)]
    nonce: Annotated[bytes, Field(strict=True, repr=False)]
    key_id: Annotated[str, Field(min_length=1, max_length=32)]

    @model_validator(mode="after")
    def validate_lifecycle(self) -> SealedEnvelope:
        if len(self.nonce) != NONCE_BYTES:
            raise ValueError(f"nonce must be exactly {NONCE_BYTES} bytes (96-bit GCM nonce)")
        if len(self.ciphertext) <= GCM_TAG_BYTES:
            raise ValueError(
                f"ciphertext must exceed the {GCM_TAG_BYTES}-byte GCM tag; a shorter value "
                "cannot hold any payload and is treated as truncated"
            )
        return self


def _cipher(key: MasterKey) -> AESGCM:
    return AESGCM(key.material)


def _seal_bytes_with_nonce(
    plaintext: bytes,
    *,
    nonce: bytes,
    aad: bytes,
    key: MasterKey,
) -> SealedEnvelope:
    """Seal under a caller-supplied nonce — **test-vector generation only**.

    Nonce reuse under a fixed key is catastrophic for GCM (it leaks the XOR of the two
    plaintexts and, with it, the authentication subkey), so no production entry point
    exposes the nonce. :func:`seal_bytes` is the only public seal, and it always generates
    a fresh random one. This private helper exists so ``tests/dq/vault/vectors.json`` can
    pin deterministic ciphertexts for the future TypeScript implementation to reproduce.
    """
    if not isinstance(plaintext, bytes) or not plaintext:
        raise ValueError("plaintext must be non-empty bytes")
    if len(plaintext) > MAX_PLAINTEXT_BYTES:
        raise ValueError(f"plaintext exceeds {MAX_PLAINTEXT_BYTES} bytes")
    if len(nonce) != NONCE_BYTES:
        raise ValueError(f"nonce must be exactly {NONCE_BYTES} bytes")
    ciphertext = _cipher(key).encrypt(nonce, plaintext, aad)
    return SealedEnvelope(ciphertext=ciphertext, nonce=nonce, key_id=key.key_id)


def seal_bytes(
    plaintext: bytes,
    *,
    aad: bytes,
    key: MasterKey | None = None,
) -> SealedEnvelope:
    """Seal arbitrary bytes under a fresh random 96-bit nonce.

    Credential-agnostic on purpose: T2/T4 seal their own payload shapes through here.
    """
    resolved = load_master_key() if key is None else key
    return _seal_bytes_with_nonce(
        plaintext,
        nonce=os.urandom(NONCE_BYTES),
        aad=aad,
        key=resolved,
    )


def open_bytes(
    envelope: SealedEnvelope,
    *,
    aad: bytes,
    key: MasterKey | None = None,
) -> bytes:
    """Authenticate and decrypt an envelope, or fail closed.

    Raises :class:`VaultKeyMismatchError` when the envelope names a different key version
    than the one loaded, and :class:`EnvelopeAuthenticationError` for every
    wrong-key / wrong-AAD / truncated / tampered case.
    """
    resolved = load_master_key() if key is None else key
    if envelope.key_id != resolved.key_id:
        raise VaultKeyMismatchError(
            f"envelope was sealed under key_id={envelope.key_id!r} but the loaded "
            f"{MASTER_KEY_ENV} is key_id={resolved.key_id!r}; re-seal or restore that "
            "key version before opening this row"
        )
    try:
        return _cipher(resolved).decrypt(envelope.nonce, envelope.ciphertext, aad)
    except InvalidTag:
        # `from None`: keep the cause out of the traceback so nothing downstream of
        # cryptography can contribute text to an error a caller might log.
        raise EnvelopeAuthenticationError(
            "sealed credential failed authentication (wrong master key, wrong "
            "workspace/broker/env binding, or altered ciphertext)"
        ) from None


# --- credential payloads -----------------------------------------------------------
# Everything above is credential-agnostic. The models below are K3's broker payloads;
# a later work package (BYOK LLM keys) adds its own beside them and reuses the envelope
# unchanged. Note the name collision the spec's §3 sketch also carries:
# `ApiKeyCredential.key_id` is the *broker's* API key identifier (sealed inside the
# ciphertext), while `SealedEnvelope.key_id` / `MasterKey.key_id` name the *master key*
# version (stored in the clear beside the ciphertext). They are unrelated.


class _CredentialPayload(_VaultModel):
    """Base for sealed credential payloads.

    Subclasses declare every secret-bearing field ``repr=False`` and implement
    :meth:`secret_material`, which is both what :func:`fingerprint` digests and what the
    plaintext-absence test asserts never escapes.
    """

    def secret_material(self) -> str:
        raise NotImplementedError


class OAuthCredential(_CredentialPayload):
    """OAuth bearer credential — the product "connect with broker" flow.

    ``refresh_token`` is optional and matches the spec §3 note that an OAuth envelope
    holds ``{access_token, refresh_token}``; token *exchange* is out of K3's scope, so
    nothing here refreshes anything. Expiry is a property of the row
    (``broker_connections.status``), not of this payload.
    """

    kind: Literal["oauth"] = "oauth"
    access_token: Annotated[str, Field(min_length=1, max_length=4096, repr=False)]
    refresh_token: Annotated[str | None, Field(min_length=1, max_length=4096, repr=False)] = None

    def secret_material(self) -> str:
        return self.access_token


class ApiKeyCredential(_CredentialPayload):
    """API key-pair credential (Alpaca ``key_id``/``secret``, IBKR equivalents).

    ``key_id`` is the broker's key identifier, not the master-key version — see the
    banner above. It is ``repr=False`` alongside ``secret`` because the fingerprint is
    the only artifact this program ever displays for a connection.
    """

    kind: Literal["api_key"] = "api_key"
    key_id: Annotated[str, Field(min_length=1, max_length=256, repr=False)]
    secret: Annotated[str, Field(min_length=1, max_length=4096, repr=False)]

    def secret_material(self) -> str:
        return self.secret


BrokerCredential: TypeAlias = Annotated[
    OAuthCredential | ApiKeyCredential, Field(discriminator="kind")
]

_CREDENTIAL_ADAPTER: Final = TypeAdapter(BrokerCredential)


def canonical_json(credential: OAuthCredential | ApiKeyCredential) -> bytes:
    """Serialize a payload to the canonical plaintext form that gets sealed.

    Canonical means: keys sorted, no whitespace, ``null``-valued optional fields omitted,
    non-ASCII left unescaped, UTF-8 encoded. That is exactly reproducible in TypeScript
    (``JSON.stringify`` over an object whose keys were inserted in sorted order, with
    absent optionals left out), which is what lets the Edge Function implementation pass
    the committed ``vectors.json`` byte-for-byte.
    """
    payload = credential.model_dump(mode="json", exclude_none=True)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def fingerprint(credential: OAuthCredential | ApiKeyCredential) -> str:
    """First 8 hex characters of ``sha256(secret material)`` — the only display artifact.

    Read it as a *label*, never as an identity: 8 hex characters is 32 bits, so
    collisions are expected well before a large table, and nothing may compare
    fingerprints to decide that two connections carry the same credential. It is also
    not a password hash — an unsalted digest of a high-entropy broker token is fine to
    show a user, but it would confirm a guessed low-entropy secret, so this is only ever
    computed over broker-issued material.
    """
    digest = hashlib.sha256(credential.secret_material().encode()).hexdigest()
    return digest[:FINGERPRINT_HEX_CHARS]


def seal_credential(
    credential: OAuthCredential | ApiKeyCredential,
    *,
    aad: bytes,
    key: MasterKey | None = None,
) -> SealedEnvelope:
    """Validate, canonicalize, and seal a credential payload.

    The argument is already a validated Pydantic instance — the seal path never accepts a
    loose mapping, so no ``ValidationError`` (whose message can echo its input) is ever
    raised with plaintext in it here.
    """
    if not isinstance(credential, (OAuthCredential, ApiKeyCredential)):
        raise TypeError(
            "seal_credential requires a validated OAuthCredential/ApiKeyCredential "
            f"instance, got {type(credential).__name__}"
        )
    return seal_bytes(canonical_json(credential), aad=aad, key=key)


class CredentialLease:
    """A time-bounded handle to one opened credential.

    Yielded by :func:`unseal_credential` and invalidated when that ``with`` block exits:
    any later access raises :class:`CredentialLeaseExpiredError`. This is what turns
    "decrypt only for the duration of the broker call" into an enforced rule — a caller
    that stashes the lease on ``self`` to reuse later gets an exception, not a silently
    long-lived token. ``repr`` is fingerprint-only.
    """

    __slots__ = ("_credential", "_fingerprint")

    def __init__(self, credential: OAuthCredential | ApiKeyCredential) -> None:
        self._credential: OAuthCredential | ApiKeyCredential | None = credential
        self._fingerprint = fingerprint(credential)

    @property
    def fingerprint(self) -> str:
        """Display-safe 8-hex label; readable even after the lease closes."""
        return self._fingerprint

    @property
    def credential(self) -> OAuthCredential | ApiKeyCredential:
        if self._credential is None:
            raise CredentialLeaseExpiredError(
                f"credential lease fingerprint={self._fingerprint} is closed; open a new "
                "lease instead of holding plaintext past the call that needed it"
            )
        return self._credential

    def close(self) -> None:
        self._credential = None

    def __repr__(self) -> str:
        state = "closed" if self._credential is None else "open"
        return f"CredentialLease(fingerprint={self._fingerprint!r}, state={state!r})"


@contextmanager
def unseal_credential(
    envelope: SealedEnvelope,
    *,
    aad: bytes,
    key: MasterKey | None = None,
) -> Iterator[CredentialLease]:
    """Open an envelope for the duration of the ``with`` block.

    Fails closed on a wrong key version, a failed tag check, or authentic bytes that are
    not a valid payload. The lease is closed on the way out — including on an exception —
    so no path leaves a usable handle behind.
    """
    plaintext = open_bytes(envelope, aad=aad, key=key)
    try:
        credential = _CREDENTIAL_ADAPTER.validate_json(plaintext)
    except ValidationError:
        # `from None`: a pydantic ValidationError echoes the input it rejected, which on
        # this path is decrypted credential material.
        raise VaultPayloadError(
            "sealed payload authenticated but is not a valid credential "
            "(expected kind='oauth' or kind='api_key')"
        ) from None
    lease = CredentialLease(credential)
    try:
        yield lease
    finally:
        lease.close()


__all__ = [
    "DEFAULT_KEY_ID",
    "FINGERPRINT_HEX_CHARS",
    "GCM_TAG_BYTES",
    "KEY_ID_ENV",
    "MASTER_KEY_BYTES",
    "MASTER_KEY_ENV",
    "MAX_PLAINTEXT_BYTES",
    "NONCE_BYTES",
    "ApiKeyCredential",
    "BrokerCredential",
    "CredentialLease",
    "CredentialLeaseExpiredError",
    "EnvelopeAuthenticationError",
    "MasterKey",
    "OAuthCredential",
    "SealedEnvelope",
    "VaultConfigurationError",
    "VaultError",
    "VaultKeyMismatchError",
    "VaultPayloadError",
    "build_aad",
    "canonical_json",
    "fingerprint",
    "load_master_key",
    "open_bytes",
    "seal_bytes",
    "seal_credential",
    "unseal_credential",
]
