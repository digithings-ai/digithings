"""Shared sealed BYOK row for overlay runner tests that invoke a chain."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

from digiquant.olympus.overlay.byok import (
    BYOK_AAD_PURPOSE,
    CredentialStatus,
    LlmProvider,
    ProviderCredential,
)
from digiquant.vault.envelope import ApiKeyCredential, MasterKey, build_aad, seal_credential


def sealed_openai(
    workspace_id: UUID,
    *,
    secret: str = "sk-user-overlay-only",
) -> tuple[ProviderCredential, MasterKey]:
    master = MasterKey(key_id="v1", material=os.urandom(32))
    envelope = seal_credential(
        ApiKeyCredential(key_id="user", secret=secret),
        aad=build_aad(str(workspace_id), "openai", BYOK_AAD_PURPOSE),
        key=master,
    )
    row = ProviderCredential(
        id=uuid4(),
        workspace_id=workspace_id,
        provider=LlmProvider.OPENAI,
        auth_kind="api_key",
        ciphertext=envelope.ciphertext,
        nonce=envelope.nonce,
        key_id=envelope.key_id,
        fingerprint="abcd1234",
        status=CredentialStatus.ACTIVE,
        created_at=datetime(2026, 8, 30, tzinfo=UTC),
    )
    return row, master
