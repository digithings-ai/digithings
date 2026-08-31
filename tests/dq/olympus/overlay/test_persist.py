"""Overlay persist guard + namespaced H7/H8 document keys."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest

pytest.importorskip("digillm.client", reason="digiquant-only CI lane omits full-workspace deps")
from digiquant.olympus.atlas.state import AtlasConfigBundle, AtlasResearchState, PhaseHermesState
from digiquant.olympus.hermes.writers.commit_io import publish_hermes_documents
from digiquant.olympus.overlay.byok import ByokProbe
from digiquant.olympus.overlay.dispatch import (
    JobStatus,
    MemoryJobRunStore,
    WorkspaceEntitlement,
    dispatch_overlay_daily,
)
from digiquant.olympus.overlay.persist import (
    OverlayPersistDisabled,
    hermes_document_key,
    require_overlay_persist,
)
from digiquant.olympus.overlay.runner import OverlayRunRequest, run_overlay
from digiquant.olympus.research_corpus import ResearchCorpusStore
from digiquant.olympus.tenancy import PlanTier, SubscriptionStatus, house_workspace_id

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient

pytestmark = pytest.mark.unit

_OK = ByokProbe(present_and_unsealable=True, provider="openai", fingerprint="deadbeef")


def test_hermes_keys_house_unprefixed_overlay_namespaced() -> None:
    overlay = uuid4()
    assert hermes_document_key("pm-direction-memo", None) == "pm-direction-memo"
    assert hermes_document_key("pm-direction-memo", house_workspace_id()) == "pm-direction-memo"
    namespaced = hermes_document_key("pm-direction-memo", overlay)
    assert namespaced == f"overlay/{overlay}/pm-direction-memo"


def test_require_overlay_persist_refuses_private_when_flag_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OLYMPUS_OVERLAY_PERSIST", raising=False)
    with pytest.raises(OverlayPersistDisabled) as exc:
        require_overlay_persist(uuid4())
    assert exc.value.code == JobStatus.PERSIST_DISABLED.value
    assert "migration 110" in exc.value.message
    require_overlay_persist(None)
    require_overlay_persist(house_workspace_id())


def test_publish_hermes_documents_namespaces_overlay_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLYMPUS_OVERLAY_PERSIST", "1")
    overlay = uuid4()
    state = AtlasResearchState(
        run_type="delta",
        run_date=date(2026, 8, 30),
        config=AtlasConfigBundle(workspace_id=str(overlay)),
    )
    state.phase_hermes = PhaseHermesState(
        pm_direction_memo={"stance": "risk-on", "notes": "overlay"},
    )
    client = FakeSupabaseClient()
    artifacts = publish_hermes_documents(client=client, state=state)
    keys = {a.document_key for a in artifacts}
    assert f"overlay/{overlay}/pm-direction-memo" in keys
    assert "pm-direction-memo" not in keys
    rows = client.store["documents"]
    assert all(r["workspace_id"] == str(overlay) for r in rows)
    assert all(r["_on_conflict"] == "workspace_id,date,document_key" for r in rows)


def test_overlay_persist_disabled_after_corpus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OLYMPUS_OVERLAY_PERSIST", raising=False)
    called = {"chain": False}

    def chain(**_kwargs: object) -> None:
        called["chain"] = True

    store = MemoryJobRunStore()
    ws = WorkspaceEntitlement(
        workspace_id=uuid4(),
        plan_tier=PlanTier.CUSTOM,
        subscription_status=SubscriptionStatus.ACTIVE,
    )
    job = dispatch_overlay_daily(
        store=store, workspace=ws, run_date=date(2026, 8, 30), byok=_OK
    ).job
    result = run_overlay(
        request=OverlayRunRequest(
            workspace_id=ws.workspace_id,
            run_date=date(2026, 8, 30),
            profile_version_id=uuid4(),
            themes=("ai",),
        ),
        job=job,
        store=store,
        corpus=ResearchCorpusStore(),
        byok=_OK,
        chain=chain,
    )
    assert called["chain"] is False
    assert result.status is JobStatus.PERSIST_DISABLED
    assert "theme:ai" in result.published_keys
    finished = store.get_by_idempotency_key(job.idempotency_key)
    assert finished is not None
    assert finished.status is JobStatus.PERSIST_DISABLED
    assert finished.error == JobStatus.PERSIST_DISABLED.value
