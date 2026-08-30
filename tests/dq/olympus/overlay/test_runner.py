"""Overlay runner: corpus assertion, publish-if-missing, workspace scoping, isolation."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest

pytest.importorskip("digillm.client", reason="digiquant-only CI lane omits full-workspace deps")
from digiquant.olympus.atlas.state import AtlasConfigBundle, AtlasResearchState, PhaseHermesState
from digiquant.olympus.hermes.writers.commit_io import (
    OVERLAY_MANIFEST_PREFIX,
    book_portfolio,
    load_commit_manifests,
    manifest_document_key,
)
from digiquant.olympus.overlay.byok import ByokProbe
from digiquant.olympus.overlay.dispatch import (
    JobStatus,
    MemoryJobRunStore,
    WorkspaceEntitlement,
    dispatch_overlay_daily,
)
from digiquant.olympus.overlay.persist import LEGACY_BOOK_UNIQUE_CODE, OverlayLegacyBookBlocked
from digiquant.olympus.overlay.runner import (
    OverlayError,
    OverlayRunRequest,
    assert_tenant_agnostic_corpus_key,
    pin_seam_config,
    publish_overlay_corpus_pin,
    run_overlay,
)
from digiquant.olympus.research_corpus import (
    ResearchCorpusKeyError,
    ResearchCorpusPin,
    ResearchCorpusStore,
    corpus_pin_version_id,
    house_corpus_pin,
)
from digiquant.olympus.tenancy import (
    PlanTier,
    SubscriptionStatus,
    house_workspace_id,
)

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient
from tests.dq.olympus.overlay._sealed import sealed_openai

pytestmark = pytest.mark.unit

_OK = ByokProbe(present_and_unsealable=True, provider="openai", fingerprint="deadbeef")


def _request(**kwargs: object) -> OverlayRunRequest:
    payload = {
        "workspace_id": uuid4(),
        "run_date": date(2026, 8, 30),
        "profile_version_id": uuid4(),
        "themes": ("ai",),
        "watchlist": ("SPY",),
    }
    payload.update(kwargs)
    return OverlayRunRequest.model_validate(payload)


def _claimed(workspace_id=None):
    store = MemoryJobRunStore()
    ws = WorkspaceEntitlement(
        workspace_id=workspace_id or uuid4(),
        plan_tier=PlanTier.CUSTOM,
        subscription_status=SubscriptionStatus.ACTIVE,
    )
    result = dispatch_overlay_daily(store=store, workspace=ws, run_date=date(2026, 8, 30), byok=_OK)
    return store, ws, result.job


def test_corpus_key_rejects_workspace_id() -> None:
    workspace_id = uuid4()
    with pytest.raises(ResearchCorpusKeyError, match="workspace/user id"):
        assert_tenant_agnostic_corpus_key(f"theme:{workspace_id}", workspace_id=workspace_id)


def test_corpus_key_rejects_user_id() -> None:
    user_id = uuid4()
    with pytest.raises(ResearchCorpusKeyError, match="workspace/user id"):
        assert_tenant_agnostic_corpus_key(f"asset:{user_id}", workspace_id=uuid4(), user_id=user_id)


def test_publish_if_missing_existing_pin_does_not_write() -> None:
    store = ResearchCorpusStore()
    house = house_corpus_pin("theme:ai", label="house AI")
    store.publish_if_missing(house)
    overlay = ResearchCorpusPin(
        version_id=corpus_pin_version_id("theme:ai"),
        corpus_key="theme:ai",
        writer_role="overlay_request",
        label="overlay AI overwrite",
    )
    published, wrote = publish_overlay_corpus_pin(store, overlay, workspace_id=uuid4())
    assert wrote is False
    assert published.label == "house AI"
    assert store.get_by_key("theme:ai") is not None
    assert store.get_by_key("theme:ai").label == "house AI"


def test_publish_if_missing_writes_when_absent() -> None:
    store = ResearchCorpusStore()
    pin = ResearchCorpusPin(
        version_id=corpus_pin_version_id("theme:energy"),
        corpus_key="theme:energy",
        writer_role="overlay_request",
        label="Energy",
    )
    published, wrote = publish_overlay_corpus_pin(store, pin, workspace_id=uuid4())
    assert wrote is True
    assert published.corpus_key == "theme:energy"


def test_pin_seam_threads_version_and_workspace() -> None:
    version = uuid4()
    workspace = uuid4()
    seam = pin_seam_config(requested_version_id=version, workspace_id=workspace)
    assert seam.profile_config_version_id == str(version)
    assert seam.workspace_id == str(workspace)
    house = pin_seam_config(requested_version_id=None, workspace_id=None)
    assert house.profile_config_version_id is None
    assert house.workspace_id is None


def test_house_config_workspace_id_absent_is_none() -> None:
    """House default (workspace param absent) stays byte-identical at the pin seam."""
    bundle = AtlasConfigBundle(watchlist=["SPY"])
    assert bundle.workspace_id is None
    assert bundle.profile_config_version_id is None


def test_overlay_run_writes_carry_overlay_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLYMPUS_OVERLAY_PERSIST", "1")
    seen: dict[str, object] = {}

    def chain(*, workspace_id, run_date, requested_version_id):
        seen["workspace_id"] = workspace_id
        seen["run_date"] = run_date
        seen["requested_version_id"] = requested_version_id

    store, ws, job = _claimed()
    request = _request(workspace_id=ws.workspace_id, profile_version_id=uuid4())
    credential, master = sealed_openai(ws.workspace_id)
    result = run_overlay(
        request=request,
        job=job,
        store=store,
        corpus=ResearchCorpusStore(),
        byok=_OK,
        chain=chain,
        credential=credential,
        vault_key=master,
    )
    assert result.status is JobStatus.SUCCEEDED
    assert seen["workspace_id"] == ws.workspace_id
    assert seen["workspace_id"] != house_workspace_id()
    assert seen["requested_version_id"] == request.profile_version_id
    assert "theme:ai" in result.published_keys
    assert "asset:spy" in result.published_keys


def test_overlay_failure_does_not_touch_house_job_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OLYMPUS_OVERLAY_PERSIST", "1")
    house_store = MemoryJobRunStore()
    overlay_store, ws, job = _claimed()
    credential, master = sealed_openai(ws.workspace_id)

    def boom(**_kwargs: object) -> None:
        raise RuntimeError("overlay exploded")

    result = run_overlay(
        request=_request(workspace_id=ws.workspace_id),
        job=job,
        store=overlay_store,
        corpus=ResearchCorpusStore(),
        byok=_OK,
        chain=boom,
        credential=credential,
        vault_key=master,
        house_job_store=house_store,
    )
    assert result.status is JobStatus.FAILED
    assert result.house_workspace_untouched is True
    assert house_store.get_by_idempotency_key(job.idempotency_key) is None
    overlay_row = overlay_store.get_by_idempotency_key(job.idempotency_key)
    assert overlay_row is not None
    assert overlay_row.status is JobStatus.FAILED


def test_overlay_refuses_house_workspace_id() -> None:
    store, _ws, job = _claimed(workspace_id=house_workspace_id())
    # Bypass dispatch identity: stamp the house id onto a job the runner must refuse.
    house_job = job.model_copy(update={"workspace_id": house_workspace_id()})
    store.update(house_job)
    with pytest.raises(OverlayError, match="house workspace"):
        run_overlay(
            request=_request(workspace_id=house_workspace_id()),
            job=house_job,
            store=store,
            corpus=ResearchCorpusStore(),
            byok=_OK,
        )


def test_overlay_manifest_key_is_namespaced() -> None:
    workspace = uuid4()
    key = manifest_document_key("run-1", str(workspace))
    assert key.startswith(OVERLAY_MANIFEST_PREFIX)
    assert str(workspace) in key
    assert manifest_document_key("run-1") == "commit-run/run-1"
    # House UUID is truthy — must still use the house prefix, not overlay-commit/.
    assert manifest_document_key("run-1", str(house_workspace_id())) == "commit-run/run-1"


def test_load_commit_manifests_house_uuid_ignores_overlay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """House lookup (omitted or house UUID) must not see overlay-commit rows.

    Persist-on does not lift this. A truthy house UUID used to search
    overlay-commit/{house}/ and miss existing commit-run/ manifests.
    Overlay listed first so dropping the is_private_workspace prefix fails.
    """
    monkeypatch.setenv("OLYMPUS_OVERLAY_PERSIST", "1")
    overlay = uuid4()
    run_date = date(2026, 8, 30)
    iso = run_date.isoformat()
    house = str(house_workspace_id())
    client = FakeSupabaseClient(
        canned_reads={
            "documents": [
                {
                    "date": iso,
                    "document_key": f"overlay-commit/{overlay}/ov-run",
                    "workspace_id": str(overlay),
                    "payload": {"weights_fingerprint": "overlay"},
                },
                {
                    "date": iso,
                    "document_key": "commit-run/house-run",
                    "workspace_id": house,
                    "payload": {"weights_fingerprint": "house"},
                },
            ]
        }
    )
    overlay_found = load_commit_manifests(
        client=client, run_date=run_date, workspace_id=str(overlay)
    )
    house_omitted = load_commit_manifests(client=client, run_date=run_date)
    house_pinned = load_commit_manifests(client=client, run_date=run_date, workspace_id=house)
    assert [m["weights_fingerprint"] for m in overlay_found] == ["overlay"]
    assert [m["weights_fingerprint"] for m in house_omitted] == ["house"]
    assert [m["weights_fingerprint"] for m in house_pinned] == ["house"]


def _book_state(*, workspace_id: str | None = None) -> AtlasResearchState:
    state = AtlasResearchState(
        run_type="delta",
        run_date=date(2026, 8, 30),
        config=AtlasConfigBundle(workspace_id=workspace_id),
    )
    state.phase_hermes = PhaseHermesState(
        sized_book={
            "recommended_portfolio": [{"ticker": "SPY", "target_pct": 100.0}],
            "actions": [],
            "notes": "overlay book",
        }
    )
    return state


def test_overlay_book_refuses_while_legacy_unique_remains(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persist=1 must not stamp overlay positions/NAV onto UNIQUE(date) tables."""
    monkeypatch.setenv("OLYMPUS_OVERLAY_PERSIST", "1")
    overlay_id = uuid4()
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
            state=_book_state(workspace_id=str(overlay_id)),
            book={
                "recommended_portfolio": [{"ticker": "SPY", "target_pct": 100.0}],
                "actions": [],
                "notes": "overlay",
            },
        )
    assert exc.value.code == LEGACY_BOOK_UNIQUE_CODE
    assert client.store.get("positions", []) == []
    assert client.store.get("nav_history", []) == []


def test_house_book_stamp_remains_house_workspace() -> None:
    client = FakeSupabaseClient(
        canned_reads={
            "thesis_vehicles": [],
            "nav_history": [],
            "price_history": [],
            "positions": [],
        }
    )
    book_portfolio(
        client=client,
        state=_book_state(workspace_id=None),
        book={
            "recommended_portfolio": [{"ticker": "SPY", "target_pct": 100.0}],
            "actions": [],
            "notes": "house",
        },
    )
    positions = client.store.get("positions", [])
    assert positions
    assert all(row["workspace_id"] == str(house_workspace_id()) for row in positions)


def test_runner_missing_byok_skips_even_if_house_key_in_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-house-must-not-be-used")
    store, ws, job = _claimed()
    result = run_overlay(
        request=_request(workspace_id=ws.workspace_id),
        job=job,
        store=store,
        corpus=ResearchCorpusStore(),
        byok=ByokProbe(present_and_unsealable=False, reason="missing"),
    )
    assert result.status is JobStatus.SKIPPED
    assert result.skip_reason is not None
    assert result.skip_reason.value == "no_credentials"
