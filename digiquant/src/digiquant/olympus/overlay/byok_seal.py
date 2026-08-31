"""Seal a gitignored BYOK LLM key into ``workspace_provider_credentials``.

Resume path for the overlay remaining hop when Settings UI is not on
production Pages yet. Default ``--check`` never writes. ``--apply`` seals
with the K3 vault and inserts one active row. Never logs secret values.

AAD is ``workspace_id:provider:llm`` — the same binding as ``byok.py`` / the
settings Edge Function. House and system workspaces are refused. Overlay
billing entitlement (paid Custom/Enterprise or D1 ``plan_floor``) is required.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from digiquant.olympus.kairos.vendor_secret_files import parse_env_file, vendor_secrets_dir
from digiquant.olympus.overlay.cron import (
    load_workspace_plan_floors,
    reserved_overlay_workspace_ids,
)
from digiquant.olympus.overlay.dispatch import WorkspaceEntitlement, overlay_billing_entitled
from digiquant.olympus.tenancy import PlanTier, SubscriptionStatus
from digiquant.vault.envelope import (
    ApiKeyCredential,
    MasterKey,
    SealedEnvelope,
    VaultError,
    build_aad,
    fingerprint,
    load_master_key,
    seal_credential,
    unseal_credential,
)

BYOK_SECRET_FILENAME: str = "digithings-byok.env"
BYOK_AAD_PURPOSE: str = "llm"
TABLE_NAME: str = "workspace_provider_credentials"
LLM_PROVIDERS: frozenset[str] = frozenset(
    {"openai", "anthropic", "groq", "openrouter", "xai", "gemini"}
)
REQUIRED_BYOK_KEYS: tuple[str, ...] = ("BYOK_PROVIDER", "BYOK_API_KEY")
EXIT_BYOK_FILE_OR_KEYS_MISSING: int = 2
EXIT_BYOK_SEAL_FAILED: int = 3
EXIT_BYOK_NOT_ENTITLED: int = 4
_BYTEA_HEX_PREFIX: str = "\\x"


class UniqueActiveByokError(Exception):
    """Partial unique index on ``(workspace_id, provider) WHERE status = active``."""


class ByokSealError(Exception):
    """Structured seal failure (``code`` + ``message``). Never includes secrets."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class PostgrestResponse(Protocol):
    data: object


class PostgrestQuery(Protocol):
    def select(self, columns: str) -> PostgrestQuery: ...
    def insert(self, row: Mapping[str, object]) -> PostgrestQuery: ...
    def update(self, values: Mapping[str, object]) -> PostgrestQuery: ...
    def eq(self, column: str, value: object) -> PostgrestQuery: ...
    def limit(self, count: int) -> PostgrestQuery: ...
    def execute(self) -> PostgrestResponse: ...


class SealStore(Protocol):
    def table(self, name: str) -> PostgrestQuery: ...


class ByokSealFile(BaseModel):
    """Sanitized file report — names only."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    missing_file: bool
    missing_keys: tuple[str, ...] = Field(default_factory=tuple)
    provider: str | None = None
    workspace_id: UUID | None = None


class ByokSealResult(BaseModel):
    """Fingerprint-only persist result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: UUID
    provider: str
    fingerprint: str
    status: str
    replaced: bool = False


def _encode_bytea(raw: bytes) -> str:
    return f"{_BYTEA_HEX_PREFIX}{raw.hex()}"


def _decode_bytea(value: object, *, column: str) -> bytes:
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if not isinstance(value, str) or not value.startswith(_BYTEA_HEX_PREFIX):
        raise ByokSealError("invalid_bytea", f"{TABLE_NAME}.{column} is not a bytea hex literal")
    try:
        return bytes.fromhex(value[len(_BYTEA_HEX_PREFIX) :])
    except ValueError as exc:
        raise ByokSealError("invalid_bytea", f"{TABLE_NAME}.{column} is not valid hex") from exc


def _unique_violation(exc: BaseException) -> bool:
    code = getattr(exc, "code", None)
    if str(code) == "23505":
        return True
    payload = getattr(exc, "args", ())
    if payload and isinstance(payload[0], Mapping) and str(payload[0].get("code")) == "23505":
        return True
    return "23505" in str(exc)


def byok_secret_path(repo_root: Path) -> Path:
    return vendor_secrets_dir(repo_root) / BYOK_SECRET_FILENAME


def inspect_byok_secret_file(repo_root: Path) -> ByokSealFile:
    """Report missing file/key *names*. Never returns secret values."""
    path = byok_secret_path(repo_root)
    if not path.is_file():
        return ByokSealFile(missing_file=True, missing_keys=REQUIRED_BYOK_KEYS)
    parsed = parse_env_file(path)
    missing = tuple(name for name in REQUIRED_BYOK_KEYS if not (parsed.get(name) or "").strip())
    provider = (parsed.get("BYOK_PROVIDER") or "").strip().lower() or None
    raw_ws = (parsed.get("BYOK_WORKSPACE_ID") or "").strip()
    workspace_id: UUID | None = None
    if raw_ws:
        try:
            workspace_id = UUID(raw_ws)
        except ValueError:
            workspace_id = None
    return ByokSealFile(
        missing_file=False,
        missing_keys=missing,
        provider=provider,
        workspace_id=workspace_id,
    )


def format_byok_seal_blocked(report: ByokSealFile) -> str:
    if report.missing_file:
        return (
            "Kairos BYOK seal blocked — missing file: "
            f"{BYOK_SECRET_FILENAME}. Write gitignored .local/secrets/{BYOK_SECRET_FILENAME}; "
            "do not seal a placeholder or house LLM key."
        )
    return "Kairos BYOK seal blocked — missing keys: " + ", ".join(report.missing_keys)


def assert_workspace_may_receive_byok(workspace: WorkspaceEntitlement) -> None:
    """Refuse house/system and workspaces overlay dispatch would skip as not_entitled."""
    if workspace.workspace_id in reserved_overlay_workspace_ids():
        raise ByokSealError(
            "reserved_workspace", "house/system workspaces cannot receive overlay BYOK"
        )
    if not overlay_billing_entitled(workspace):
        raise ByokSealError(
            "not_entitled",
            "workspace is not overlay-billing entitled (paid custom/enterprise or plan_floor)",
        )


def load_secret_payload(repo_root: Path) -> tuple[str, str]:
    """Return ``(provider, secret)``. Caller must not log the secret."""
    parsed = parse_env_file(byok_secret_path(repo_root))
    provider = (parsed.get("BYOK_PROVIDER") or "").strip().lower()
    secret = (parsed.get("BYOK_API_KEY") or "").strip()
    if provider not in LLM_PROVIDERS:
        raise ByokSealError(
            "invalid_provider",
            "BYOK_PROVIDER must be one of openai, anthropic, groq, openrouter, xai, gemini",
        )
    if not secret:
        raise ByokSealError("missing_keys", "BYOK_API_KEY is empty")
    return provider, secret


def build_sealed_row(
    *,
    workspace_id: UUID,
    provider: str,
    secret: str,
    key: MasterKey,
    row_id: UUID | None = None,
) -> dict[str, object]:
    """Seal an api_key payload. Returned mapping has no plaintext secret."""
    credential = ApiKeyCredential(key_id="api_key", secret=secret)
    aad = build_aad(str(workspace_id), provider, BYOK_AAD_PURPOSE)
    envelope = seal_credential(credential, aad=aad, key=key)
    return {
        "id": str(row_id or uuid4()),
        "workspace_id": str(workspace_id),
        "provider": provider,
        "auth_kind": "api_key",
        "ciphertext": _encode_bytea(envelope.ciphertext),
        "nonce": _encode_bytea(envelope.nonce),
        "key_id": envelope.key_id,
        "fingerprint": fingerprint(credential),
        "scopes": [],
        "status": "active",
    }


def verify_sealed_row(row: Mapping[str, object], *, key: MasterKey) -> None:
    """Fail closed if the just-built envelope cannot unseal under the same AAD."""
    ciphertext = _decode_bytea(row["ciphertext"], column="ciphertext")
    nonce = _decode_bytea(row["nonce"], column="nonce")
    aad = build_aad(str(row["workspace_id"]), str(row["provider"]), BYOK_AAD_PURPOSE)
    sealed = SealedEnvelope(ciphertext=ciphertext, nonce=nonce, key_id=str(row["key_id"]))
    with unseal_credential(sealed, aad=aad, key=key) as lease:
        _ = lease.fingerprint


def _insert_row(client: SealStore, row: Mapping[str, object]) -> list[Mapping[str, object]]:
    try:
        result = client.table(TABLE_NAME).insert(row).execute()
    except UniqueActiveByokError:
        raise
    except Exception as exc:
        if _unique_violation(exc):
            raise UniqueActiveByokError from None
        raise ByokSealError("connect_failed", "Unable to store provider credential") from None
    error = getattr(result, "error", None)
    if error is not None and _unique_violation(Exception(str(error))):
        raise UniqueActiveByokError
    data = getattr(result, "data", result)
    if not isinstance(data, list) or not data or not isinstance(data[0], Mapping):
        raise ByokSealError("connect_failed", "insert returned no row")
    return [data[0]]


def _revoke_active(client: SealStore, workspace_id: UUID, provider: str, stamp: str) -> None:
    client.table(TABLE_NAME).update({"status": "revoked", "revoked_at": stamp}).eq(
        "workspace_id", str(workspace_id)
    ).eq("provider", provider).eq("status", "active").execute()


def persist_active_byok(
    *,
    client: SealStore,
    row: Mapping[str, object],
    now: datetime | None = None,
) -> ByokSealResult:
    """Insert an active row; on unique conflict revoke then insert (Settings EF reconnect)."""
    workspace_id = UUID(str(row["workspace_id"]))
    provider = str(row["provider"])
    replaced = False
    try:
        stored = _insert_row(client, row)[0]
    except UniqueActiveByokError:
        stamp = (now or datetime.now(tz=UTC)).astimezone(UTC).isoformat()
        _revoke_active(client, workspace_id, provider, stamp)
        retry = dict(row)
        retry["id"] = str(uuid4())
        stored = _insert_row(client, retry)[0]
        replaced = True
    return ByokSealResult(
        workspace_id=workspace_id,
        provider=provider,
        fingerprint=str(stored.get("fingerprint") or row["fingerprint"]),
        status=str(stored.get("status") or "active"),
        replaced=replaced,
    )


def load_workspace_entitlement(client: SealStore, workspace_id: UUID) -> WorkspaceEntitlement:
    result = (
        client.table("workspaces")
        .select("id,plan_tier,subscription_status")
        .eq("id", str(workspace_id))
        .limit(1)
        .execute()
    )
    data = getattr(result, "data", result)
    if isinstance(data, list):
        data = data[0] if data else None
    if not isinstance(data, Mapping):
        raise ByokSealError("workspace_not_found", "unknown workspace_id")
    floors = load_workspace_plan_floors(client)
    return WorkspaceEntitlement(
        workspace_id=workspace_id,
        plan_tier=PlanTier(str(data["plan_tier"])),
        subscription_status=SubscriptionStatus(str(data["subscription_status"])),
        plan_floor=floors.get(workspace_id),
    )


def run_byok_seal(
    *,
    repo_root: Path,
    apply: bool,
    log: Callable[[str], None],
    workspace_id: UUID | None = None,
    client: SealStore | None = None,
    key: MasterKey | None = None,
    entitlement: WorkspaceEntitlement | None = None,
    now: datetime | None = None,
) -> int:
    report = inspect_byok_secret_file(repo_root)
    if report.missing_file or report.missing_keys:
        log(format_byok_seal_blocked(report))
        return EXIT_BYOK_FILE_OR_KEYS_MISSING
    if report.provider is not None:
        log(f"BYOK provider name present: {report.provider}")
    if not apply:
        log("BYOK seal: check ok (file and required key names present; not written)")
        return 0
    target = workspace_id or report.workspace_id
    if target is None:
        log("BYOK seal blocked — pass --workspace-id or BYOK_WORKSPACE_ID")
        return EXIT_BYOK_SEAL_FAILED
    try:
        master = key if key is not None else load_master_key()
        provider, secret = load_secret_payload(repo_root)
        workspace = entitlement
        if workspace is None:
            if client is None:
                raise ByokSealError("store_not_configured", "seal apply requires a store client")
            workspace = load_workspace_entitlement(client, target)
        assert_workspace_may_receive_byok(workspace)
        row = build_sealed_row(
            workspace_id=workspace.workspace_id, provider=provider, secret=secret, key=master
        )
        verify_sealed_row(row, key=master)
        if client is None:
            raise ByokSealError("store_not_configured", "seal apply requires a store client")
        result = persist_active_byok(client=client, row=row, now=now)
    except ByokSealError as exc:
        log(f"BYOK seal blocked — {exc.code}")
        if exc.code == "not_entitled" or exc.code == "reserved_workspace":
            return EXIT_BYOK_NOT_ENTITLED
        return EXIT_BYOK_SEAL_FAILED
    except VaultError:
        log("BYOK seal blocked — vault_unusable")
        return EXIT_BYOK_SEAL_FAILED
    log(
        f"BYOK seal: stored provider={result.provider} fingerprint={result.fingerprint} "
        f"replaced={str(result.replaced).lower()}"
    )
    return 0


__all__ = [
    "BYOK_AAD_PURPOSE",
    "BYOK_SECRET_FILENAME",
    "ByokSealError",
    "ByokSealFile",
    "ByokSealResult",
    "EXIT_BYOK_FILE_OR_KEYS_MISSING",
    "EXIT_BYOK_NOT_ENTITLED",
    "EXIT_BYOK_SEAL_FAILED",
    "LLM_PROVIDERS",
    "REQUIRED_BYOK_KEYS",
    "TABLE_NAME",
    "assert_workspace_may_receive_byok",
    "build_sealed_row",
    "format_byok_seal_blocked",
    "inspect_byok_secret_file",
    "persist_active_byok",
    "run_byok_seal",
]
