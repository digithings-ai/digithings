"""BYOK no-fallback: house provider keys are never used for overlay LLM calls."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest

pytest.importorskip("digillm.client", reason="digiquant-only CI lane omits full-workspace deps")

import digillm.client as digillm_client
from digillm.client import get_byok
from digiquant.dashboard.overlay.byok import (
    BYOK_AAD_PURPOSE,
    LLM_PROVIDERS,
    TABLE_NAME,
    ByokError,
    ByokProbe,
    CredentialStatus,
    LlmProvider,
    ProviderCredential,
    invoke_overlay_chain,
    overlay_llm_session,
    probe_byok,
    provider_base_url,
)
from digiquant.dashboard.overlay.dispatch import (
    JobStatus,
    MemoryJobRunStore,
    OverlaySkipReason,
    WorkspaceEntitlement,
    dispatch_overlay_daily,
)
from digiquant.dashboard.overlay.runner import OverlayRunRequest, run_overlay
from digiquant.dashboard.research_corpus import ResearchCorpusStore
from digiquant.dashboard.tenancy import PlanTier, SubscriptionStatus
from digiquant.vault.envelope import (
    ApiKeyCredential,
    MasterKey,
    build_aad,
    seal_credential,
)

from tests.dq.dashboard.overlay._sealed import sealed_openai

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
            plan_tier=PlanTier.STUDIO,
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


def test_invoke_chain_credential_none_refuses_never_calls_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLYMPUS_OVERLAY_PERSIST", "1")
    called = {"n": 0}

    def chain(**_kwargs: object) -> None:
        called["n"] += 1

    store = MemoryJobRunStore()
    workspace = WorkspaceEntitlement(
        workspace_id=uuid4(),
        plan_tier=PlanTier.STUDIO,
        subscription_status=SubscriptionStatus.ACTIVE,
    )
    job = dispatch_overlay_daily(
        store=store,
        workspace=workspace,
        run_date=date(2026, 8, 30),
        byok=ByokProbe(present_and_unsealable=True, provider="openai"),
    ).job
    result = run_overlay(
        request=OverlayRunRequest(
            workspace_id=workspace.workspace_id,
            run_date=date(2026, 8, 30),
            profile_version_id=uuid4(),
        ),
        job=job,
        store=store,
        corpus=ResearchCorpusStore(),
        byok=ByokProbe(present_and_unsealable=True, provider="openai"),
        chain=chain,
        credential=None,
    )
    assert called["n"] == 0
    assert result.status is JobStatus.SKIPPED
    assert result.skip_reason is OverlaySkipReason.NO_CREDENTIALS


def test_invoke_overlay_chain_none_raises_without_calling() -> None:
    called = {"n": 0}

    def chain(**_kwargs: object) -> None:
        called["n"] += 1

    with pytest.raises(ByokError) as exc:
        invoke_overlay_chain(
            chain=chain,
            credential=None,
            vault_key=None,
            workspace_id=uuid4(),
            run_date=date(2026, 8, 30),
            requested_version_id=uuid4(),
        )
    assert exc.value.code == "no_credentials"
    assert called["n"] == 0


def test_prefixed_model_not_covered_by_bound_provider_refuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-house-anthropic-must-not-be-used")
    monkeypatch.setenv("OPENAI_API_KEY", _HOUSE_KEY)
    workspace = uuid4()
    credential, master = sealed_openai(workspace)
    with overlay_llm_session(credential=credential, key=master):
        with pytest.raises(ByokError) as exc:
            digillm_client.get_client_for_model("anthropic/claude-sonnet-4-6")
    assert exc.value.code == "byok_provider_mismatch"
