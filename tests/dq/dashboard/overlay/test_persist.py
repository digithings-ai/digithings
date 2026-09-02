"""Overlay persist guard + namespaced H7/H8 document keys."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest

pytest.importorskip("digillm.client", reason="digiquant-only CI lane omits full-workspace deps")
from digiquant.research.state import ResearchConfigBundle, ResearchState, PhasePortfolioState
from digiquant.portfolio.writers.commit_io import book_portfolio, publish_portfolio_documents
from digiquant.dashboard.overlay.byok import ByokProbe
from digiquant.dashboard.overlay.dispatch import (
    JobStatus,
    MemoryJobRunStore,
    WorkspaceEntitlement,
    dispatch_overlay_daily,
)
from digiquant.dashboard.overlay.persist import (
    LEGACY_BOOK_UNIQUE_CODE,
    OverlayLegacyBookBlocked,
    OverlayPersistDisabled,
    portfolio_document_key,
    require_overlay_legacy_book_safe,
    require_overlay_persist,
    skip_overlay_shared_register,
)
from digiquant.dashboard.overlay.runner import OverlayRunRequest, run_overlay
from digiquant.dashboard.research_corpus import ResearchCorpusStore
from digiquant.dashboard.tenancy import PlanTier, SubscriptionStatus, house_workspace_id

from tests.dq.research.test_supabase_io import FakeSupabaseClient

pytestmark = pytest.mark.unit

_OK = ByokProbe(present_and_unsealable=True, provider="openai", fingerprint="deadbeef")


def test_portfolio_keys_house_unprefixed_overlay_namespaced() -> None:
    overlay = uuid4()
    assert portfolio_document_key("pm-direction-memo", None) == "pm-direction-memo"
    assert portfolio_document_key("pm-direction-memo", house_workspace_id()) == "pm-direction-memo"
    namespaced = portfolio_document_key("pm-direction-memo", overlay)
    assert namespaced == f"overlay/{overlay}/pm-direction-memo"


def test_require_overlay_persist_refuses_private_when_flag_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OLYMPUS_OVERLAY_PERSIST", raising=False)
    monkeypatch.delenv("DIGIQUANT_OVERLAY_PERSIST", raising=False)
    with pytest.raises(OverlayPersistDisabled) as exc:
        require_overlay_persist(uuid4())
    assert exc.value.code == JobStatus.PERSIST_DISABLED.value
    assert "migration 110" in exc.value.message
    require_overlay_persist(None)
    require_overlay_persist(house_workspace_id())


def test_require_overlay_legacy_book_safe_blocks_private_allows_house() -> None:
    """positions/NAV/ledger stay single-tenant until staged 113 is applied."""
    with pytest.raises(OverlayLegacyBookBlocked) as exc:
        require_overlay_legacy_book_safe(uuid4())
    assert exc.value.code == LEGACY_BOOK_UNIQUE_CODE
    require_overlay_legacy_book_safe(None)
    require_overlay_legacy_book_safe(house_workspace_id())


def test_skip_overlay_shared_register_independent_of_persist_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persist=1 still must not upsert house-owned shared registers."""
    overlay = uuid4()
    monkeypatch.setenv("OLYMPUS_OVERLAY_PERSIST", "1")
    assert skip_overlay_shared_register(overlay) is True
    monkeypatch.delenv("OLYMPUS_OVERLAY_PERSIST", raising=False)
    assert skip_overlay_shared_register(overlay) is True
    assert skip_overlay_shared_register(None) is False
    assert skip_overlay_shared_register(house_workspace_id()) is False


def test_overlay_book_portfolio_refuses_private_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persist=1 must not write overlay positions/NAV while UNIQUE(date) remains."""
    monkeypatch.setenv("OLYMPUS_OVERLAY_PERSIST", "1")
    overlay = uuid4()
    state = ResearchState(
        run_type="delta",
        run_date=date(2026, 8, 30),
        config=ResearchConfigBundle(workspace_id=str(overlay)),
    )
    client = FakeSupabaseClient(
        canned_reads={
            "thesis_vehicles": [],
            "nav_history": [],
            "price_history": [],
            "positions": [],
        }
    )
    with pytest.raises(OverlayLegacyBookBlocked) as exc:
        book_portfolio(
            client=client,
            state=state,
            book={
                "recommended_portfolio": [{"ticker": "SPY", "target_pct": 100.0}],
                "actions": [],
                "notes": "overlay",
            },
        )
    assert exc.value.code == LEGACY_BOOK_UNIQUE_CODE
    assert client.store.get("positions", []) == []
    assert client.store.get("nav_history", []) == []


def test_publish_portfolio_documents_namespaces_overlay_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLYMPUS_OVERLAY_PERSIST", "1")
    overlay = uuid4()
    state = ResearchState(
        run_type="delta",
        run_date=date(2026, 8, 30),
        config=ResearchConfigBundle(workspace_id=str(overlay)),
    )
    state.phase_portfolio = PhasePortfolioState(
        pm_direction_memo={"stance": "risk-on", "notes": "overlay"},
    )
    client = FakeSupabaseClient()
    artifacts = publish_portfolio_documents(client=client, state=state)
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
    monkeypatch.delenv("DIGIQUANT_OVERLAY_PERSIST", raising=False)
    called = {"chain": False}

    def chain(**_kwargs: object) -> None:
        called["chain"] = True

    store = MemoryJobRunStore()
    ws = WorkspaceEntitlement(
        workspace_id=uuid4(),
        plan_tier=PlanTier.STUDIO,
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
