"""BYOK LLM key unseal for overlay jobs (T4 / D9).

Reuses K3's vault envelope unchanged. AAD is ``workspace_id:provider:llm`` —
the same ``build_aad`` helper, with ``llm`` in the env slot so a broker
ciphertext cannot open here and a BYOK ciphertext cannot open as a broker.

No-fallback (test-pinned): missing or unsealable user key ⇒ skip. House
provider keys in the process environment are never read for overlay LLM
calls; the runner constructs clients only inside :func:`overlay_llm_session`,
which sets ``digillm.client.byok`` (the existing per-request override).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Annotated, Final, Protocol
from uuid import UUID

import digillm.client as digillm_client
from digillm.client import byok as digillm_byok
from digillm.client import get_byok, is_registered_provider
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from digiquant.vault.envelope import (
    ApiKeyCredential,
    CredentialLease,
    MasterKey,
    SealedEnvelope,
    VaultError,
    build_aad,
    unseal_credential,
)

logger = logging.getLogger(__name__)

TABLE_NAME: Final = "workspace_provider_credentials"
BYOK_AAD_PURPOSE: Final = "llm"
LLM_PROVIDERS: frozenset[str] = frozenset(
    {"openai", "anthropic", "groq", "openrouter", "xai", "gemini"}
)

_PROVIDER_BASE_URLS: Final[dict[str, str]] = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1/",
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "xai": "https://api.x.ai/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
}

_BYTEA_HEX_PREFIX: Final = "\\x"
_FULL_COLUMNS: Final = (
    "id, workspace_id, provider, auth_kind, ciphertext, nonce, key_id, "
    "fingerprint, scopes, status, created_at, revoked_at, last_used_at"
)


class LlmProvider(StrEnum):
    """Closed vocabulary matching ``workspace_provider_credentials.provider``."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GROQ = "groq"
    OPENROUTER = "openrouter"
    XAI = "xai"
    GEMINI = "gemini"


class CredentialStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class ByokError(Exception):
    """Structured BYOK failure (``code`` + ``message``)."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class ByokProbe(BaseModel):
    """Entitlement-gate result: present-and-unsealable, or why not."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    present_and_unsealable: bool
    provider: str | None = None
    fingerprint: str | None = None
    reason: str | None = None


class _TableQuery(Protocol):
    def select(self, columns: str) -> _TableQuery: ...
    def eq(self, column: str, value: object) -> _TableQuery: ...
    def limit(self, n: int) -> _TableQuery: ...
    def execute(self) -> object: ...


class _SupabaseClient(Protocol):
    def table(self, name: str) -> _TableQuery: ...


class ProviderCredential(BaseModel):
    """One ``workspace_provider_credentials`` row (fingerprint-only ``repr``)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    workspace_id: UUID
    provider: LlmProvider
    auth_kind: str
    ciphertext: Annotated[bytes, Field(strict=True, repr=False)]
    nonce: Annotated[bytes, Field(strict=True, repr=False)]
    key_id: Annotated[str, Field(min_length=1, max_length=32)]
    fingerprint: Annotated[str, Field(pattern=r"^[0-9a-f]{8}$")]
    status: CredentialStatus
    created_at: AwareDatetime
    revoked_at: AwareDatetime | None = None
    last_used_at: AwareDatetime | None = None

    @property
    def sealed_envelope(self) -> SealedEnvelope:
        return SealedEnvelope(ciphertext=self.ciphertext, nonce=self.nonce, key_id=self.key_id)

    @property
    def aad(self) -> bytes:
        return build_aad(str(self.workspace_id), self.provider.value, BYOK_AAD_PURPOSE)


def model_route_prefix(model: str) -> str | None:
    """Registered ``provider/`` prefix, or ``None`` when the default client handles it."""
    if "/" not in model:
        return None
    prefix, _, _ = model.partition("/")
    return prefix if is_registered_provider(prefix) else None


def assert_byok_covers_model(model: str, bound_provider: str) -> None:
    """Refuse a prefixed model the unsealed provider does not cover.

    ``digillm.get_client_for_model`` would otherwise fall through to house
    env keys (``ANTHROPIC_API_KEY``, …) when the BYOK base URL does not
    match the prefix.
    """
    prefix = model_route_prefix(model)
    if prefix is not None and prefix != bound_provider:
        raise ByokError(
            "byok_provider_mismatch",
            f"model {model!r} routes to {prefix!r}; bound BYOK is {bound_provider!r}",
        )


@contextmanager
def _gate_byok_models(bound_provider: str) -> Iterator[None]:
    original = digillm_client.get_client_for_model

    def gated(model: str) -> object:
        assert_byok_covers_model(model, bound_provider)
        return original(model)

    digillm_client.get_client_for_model = gated  # type: ignore[method-assign]
    try:
        yield
    finally:
        digillm_client.get_client_for_model = original


def provider_base_url(provider: str) -> str:
    """OpenAI-compatible base URL for a sealed provider name."""
    url = _PROVIDER_BASE_URLS.get(provider)
    if url is None:
        raise ByokError("unknown_provider", f"unsupported LLM provider {provider!r}")
    return url


def _decode_bytea(value: object, *, column: str) -> bytes:
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if not isinstance(value, str) or not value.startswith(_BYTEA_HEX_PREFIX):
        raise ByokError(
            "invalid_bytea",
            f"{TABLE_NAME}.{column} must be a bytea hex literal or bytes",
        )
    try:
        return bytes.fromhex(value[len(_BYTEA_HEX_PREFIX) :])
    except ValueError as exc:
        raise ByokError("invalid_bytea", f"{TABLE_NAME}.{column} is not valid hex") from exc


def _rows(result: object) -> list[Mapping[str, object]]:
    data = getattr(result, "data", result)
    if data is None:
        return []
    if isinstance(data, list):
        return [row for row in data if isinstance(row, Mapping)]
    return []


def _row_to_credential(row: Mapping[str, object]) -> ProviderCredential:
    created = row.get("created_at")
    if not isinstance(created, datetime):
        created = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
    revoked = row.get("revoked_at")
    last_used = row.get("last_used_at")
    return ProviderCredential(
        id=UUID(str(row["id"])),
        workspace_id=UUID(str(row["workspace_id"])),
        provider=LlmProvider(str(row["provider"])),
        auth_kind=str(row["auth_kind"]),
        ciphertext=_decode_bytea(row["ciphertext"], column="ciphertext"),
        nonce=_decode_bytea(row["nonce"], column="nonce"),
        key_id=str(row["key_id"]),
        fingerprint=str(row["fingerprint"]),
        status=CredentialStatus(str(row["status"])),
        created_at=created if created.tzinfo else created.replace(tzinfo=UTC),
        revoked_at=revoked if isinstance(revoked, datetime) else None,
        last_used_at=last_used if isinstance(last_used, datetime) else None,
    )


def load_active_credential(
    *,
    client: object | None,
    workspace_id: UUID,
    provider: str | None = None,
) -> ProviderCredential | None:
    """Return the active BYOK row, or ``None`` when absent / client missing."""
    if client is None:
        return None
    query = (
        client.table(TABLE_NAME)
        .select(_FULL_COLUMNS)
        .eq("workspace_id", str(workspace_id))
        .eq("status", CredentialStatus.ACTIVE.value)
    )
    if provider is not None:
        query = query.eq("provider", provider)
    rows = _rows(query.limit(1).execute())
    if not rows:
        return None
    return _row_to_credential(rows[0])


def probe_byok(
    *,
    client: object | None,
    workspace_id: UUID,
    key: MasterKey | None = None,
) -> ByokProbe:
    """Present-and-unsealable check. Never constructs a house-key LLM client."""
    row = load_active_credential(client=client, workspace_id=workspace_id)
    if row is None:
        return ByokProbe(present_and_unsealable=False, reason="missing")
    try:
        with unseal_credential(row.sealed_envelope, aad=row.aad, key=key) as lease:
            _ = lease.fingerprint
    except VaultError:
        logger.info(
            "overlay BYOK unseal failed workspace_id=%s fingerprint=%s",
            workspace_id,
            row.fingerprint,
        )
        return ByokProbe(
            present_and_unsealable=False,
            provider=row.provider.value,
            fingerprint=row.fingerprint,
            reason="unsealable",
        )
    return ByokProbe(
        present_and_unsealable=True,
        provider=row.provider.value,
        fingerprint=row.fingerprint,
    )


@contextmanager
def overlay_llm_session(
    *,
    credential: ProviderCredential,
    key: MasterKey | None = None,
) -> Iterator[CredentialLease]:
    """Unseal the user key and bind ``digillm.byok`` for the ``with`` block.

    House ``OPENAI_API_KEY`` / LiteLLM proxy env is not read while this
    session is open: ``get_client`` honors the BYOK override first.
    """
    if credential.status is not CredentialStatus.ACTIVE:
        raise ByokError(
            "not_active",
            f"{TABLE_NAME} row id={credential.id} is {credential.status.value}",
        )
    with unseal_credential(credential.sealed_envelope, aad=credential.aad, key=key) as lease:
        payload = lease.credential
        if not isinstance(payload, ApiKeyCredential):
            raise ByokError("unsupported_kind", "overlay BYOK requires kind=api_key")
        with digillm_byok(payload.secret, provider_base_url(credential.provider.value)):
            if get_byok() is None:
                raise ByokError("byok_not_bound", "digillm BYOK override failed to bind")
            with _gate_byok_models(credential.provider.value):
                yield lease


def invoke_overlay_chain(
    *,
    chain: Callable[..., object],
    credential: ProviderCredential | None,
    vault_key: MasterKey | None,
    workspace_id: UUID,
    run_date: date,
    requested_version_id: UUID,
) -> None:
    """One-graph invoke. ``credential is None`` refuses — never call ``chain()``."""
    if credential is None:
        raise ByokError(
            "no_credentials",
            "overlay chain requires a bound BYOK credential; house env keys are not a fallback",
        )
    with overlay_llm_session(credential=credential, key=vault_key):
        chain(
            workspace_id=workspace_id,
            run_date=run_date,
            requested_version_id=requested_version_id,
        )


__all__ = [
    "BYOK_AAD_PURPOSE",
    "ByokError",
    "ByokProbe",
    "CredentialStatus",
    "LLM_PROVIDERS",
    "LlmProvider",
    "ProviderCredential",
    "TABLE_NAME",
    "assert_byok_covers_model",
    "invoke_overlay_chain",
    "load_active_credential",
    "model_route_prefix",
    "overlay_llm_session",
    "probe_byok",
    "provider_base_url",
]
