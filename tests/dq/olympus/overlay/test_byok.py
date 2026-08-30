"""BYOK no-fallback: house provider keys are never used for overlay LLM calls."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from digillm.client import get_byok
from digiquant.olympus.overlay.byok import (
    BYOK_AAD_PURPOSE,
    LLM_PROVIDERS,
    TABLE_NAME,
    CredentialStatus,
    LlmProvider,
    ProviderCredential,
    overlay_llm_session,
    probe_byok,
    provider_base_url,
)
from digiquant.olympus.overlay.dispatch import (
    JobStatus,
    MemoryJobRunStore,
    OverlaySkipReason,
    WorkspaceEntitlement,
    dispatch_overlay_daily,
)
from digiquant.olympus.tenancy import PlanTier, SubscriptionStatus
from digiquant.vault.envelope import (
    ApiKeyCredential,
    MasterKey,
    build_aad,
    seal_credential,
)

pytestmark = pytest.mark.unit

_HOUSE_KEY = "sk-house-must-never-be-used"
_USER_KEY = "sk-user-overlay-only"


def _key() -> MasterKey:
    return MasterKey(key_id="v1", material=os.urandom(32))


def test_aad_is_workspace_provider_llm() -> None:
    workspace = uuid4()
    aad = build_aad(str(workspace), LlmProvider.OPENAI.value, BYOK_AAD_PURPOSE)
    assert aad == f"{workspace}:openai:llm".encode()
    assert "openai" in LLM_PROVIDERS


def test_missing_user_key_skips_and_does_not_bind_house_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", _HOUSE_KEY)
    monkeypatch.setenv("LITELLM_PROXY_API_KEY", _HOUSE_KEY)
    store = MemoryJobRunStore()
    result = dispatch_overlay_daily(
        store=store,
        workspace=WorkspaceEntitlement(
            workspace_id=uuid4(),
            plan_tier=PlanTier.CUSTOM,
            subscription_status=SubscriptionStatus.ACTIVE,
        ),
        run_date=date(2026, 8, 30),
        byok_client=None,
    )
    assert result.job.status is JobStatus.SKIPPED
    assert result.skip_reason is OverlaySkipReason.NO_CREDENTIALS
    assert get_byok() is None
    assert os.environ.get("OPENAI_API_KEY") == _HOUSE_KEY


def test_overlay_llm_session_binds_user_key_not_house(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", _HOUSE_KEY)
    workspace = uuid4()
    master = _key()
    credential = ApiKeyCredential(key_id="user", secret=_USER_KEY)
    aad = build_aad(str(workspace), "openai", BYOK_AAD_PURPOSE)
    envelope = seal_credential(credential, aad=aad, key=master)
    row = ProviderCredential(
        id=uuid4(),
        workspace_id=workspace,
        provider=LlmProvider.OPENAI,
        auth_kind="api_key",
        ciphertext=envelope.ciphertext,
        nonce=envelope.nonce,
        key_id=envelope.key_id,
        fingerprint="abcd1234",
        status=CredentialStatus.ACTIVE,
        created_at=datetime(2026, 8, 30, tzinfo=UTC),
    )
    with overlay_llm_session(credential=row, key=master) as lease:
        bound = get_byok()
        assert bound is not None
        api_key, base_url = bound
        assert api_key == _USER_KEY
        assert api_key != _HOUSE_KEY
        assert base_url == provider_base_url("openai")
        assert lease.fingerprint
    assert get_byok() is None


def test_probe_unsealable_when_aad_mismatched() -> None:
    workspace = uuid4()
    master = _key()
    credential = ApiKeyCredential(key_id="user", secret=_USER_KEY)
    # Seal under a *broker* AAD — overlay opener uses workspace:provider:llm.
    wrong_aad = build_aad(str(workspace), "alpaca", "paper")
    envelope = seal_credential(credential, aad=wrong_aad, key=master)
    row = {
        "id": str(uuid4()),
        "workspace_id": str(workspace),
        "provider": "openai",
        "auth_kind": "api_key",
        "ciphertext": envelope.ciphertext,
        "nonce": envelope.nonce,
        "key_id": envelope.key_id,
        "fingerprint": "abcd1234",
        "scopes": [],
        "status": CredentialStatus.ACTIVE.value,
        "created_at": datetime(2026, 8, 30, tzinfo=UTC),
        "revoked_at": None,
        "last_used_at": None,
    }

    class _Query:
        def select(self, _cols: str) -> _Query:
            return self

        def eq(self, _col: str, _val: object) -> _Query:
            return self

        def limit(self, _n: int) -> _Query:
            return self

        def execute(self) -> object:
            return type("R", (), {"data": [row]})()

    class _Client:
        def table(self, name: str) -> _Query:
            assert name == TABLE_NAME
            return _Query()

    probe = probe_byok(client=_Client(), workspace_id=workspace, key=master)
    assert probe.present_and_unsealable is False
    assert probe.reason == "unsealable"
