"""Retrieval tool contract tests (dashboard #930 — tools/research-retrieval)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from digiquant.dashboard.research_retrieval import (
    ResearchCache,
    ResearchRetriever,
    assert_blinded_h5_prompt,
    assert_blinded_h6_prompt,
    build_research_tool_dispatcher,
    build_retrieval_query_pin,
    link_manifest_provider_tokens,
    persist_pre_call_role_manifest,
    portfolio_tool_allowed,
    query_portfolio,
    query_research,
    research_document_allowed,
    search_research,
    strip_blinded_forbidden_keys,
)
from digiquant.dashboard.research_retrieval.context import (
    ContextCompileInput,
    ContextRole,
    compile_context_capsule,
)
from digiquant.dashboard.research_retrieval.models import (
    LegacyDocumentRef,
    content_digest,
    legacy_document_ref_id,
)
from digiquant.dashboard.research_retrieval.queries import RetrievalManifestMode
from digiquant.dashboard.research_retrieval.store import (
    ActualProviderAttemptUsage,
    LoadedResearchState,
    RoleRetrievalManifestStore,
)
from digiquant.dashboard.research_retrieval.tools import resolve_retrieval_manifest_mode
from digiquant.dashboard.tenancy import house_workspace_id

from tests.dq.dashboard.test_context_compiler import _evidence, _loaded_state
from tests.dq.research.test_supabase_io import FakeSupabaseClient

_TS = datetime(2026, 8, 26, 18, 0, tzinfo=UTC)


@pytest.mark.unit
class TestQueryResearch:
    def test_document_exact_date(self) -> None:
        client = FakeSupabaseClient(
            canned_reads={
                "documents": [
                    {
                        "date": "2026-06-18",
                        "document_key": "macro",
                        "payload": {"headline": "Thu macro"},
                    },
                    {
                        "date": "2026-06-19",
                        "document_key": "macro",
                        "payload": {"headline": "Fri macro"},
                    },
                ]
            }
        )
        out = query_research(
            client,
            run_date=date(2026, 6, 20),
            document_key="macro",
            as_of_date=date(2026, 6, 19),
        )
        assert out["source"] == "documents"
        assert out["as_of_date"] == "2026-06-19"
        assert out["payload"] == {"headline": "Fri macro"}

    def test_document_ignores_overlay_same_key_listed_first(self) -> None:
        house = str(house_workspace_id())
        overlay = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        client = FakeSupabaseClient(
            canned_reads={
                "documents": [
                    {
                        "date": "2026-06-19",
                        "document_key": "macro",
                        "payload": {"headline": "overlay"},
                        "workspace_id": overlay,
                    },
                    {
                        "date": "2026-06-19",
                        "document_key": "macro",
                        "payload": {"headline": "house"},
                        "workspace_id": house,
                    },
                ]
            }
        )
        out = query_research(
            client,
            run_date=date(2026, 6, 20),
            document_key="macro",
            as_of_date=date(2026, 6, 19),
        )
        assert out["payload"] == {"headline": "house"}

    def test_document_prior_published_fallback(self) -> None:
        client = FakeSupabaseClient(
            canned_reads={
                "documents": [
                    {
                        "date": "2026-06-18",
                        "document_key": "macro",
                        "payload": {"headline": "Thu macro"},
                    }
                ]
            }
        )
        out = query_research(
            client,
            run_date=date(2026, 6, 20),
            document_key="macro",
            as_of_date=date(2026, 6, 19),
        )
        assert out["as_of_date"] == "2026-06-18"
        assert out["payload"]["headline"] == "Thu macro"

    def test_digest_from_daily_snapshots(self) -> None:
        client = FakeSupabaseClient(
            canned_reads={
                "daily_snapshots": [
                    {
                        "date": "2026-06-19",
                        "snapshot": {"one_line_summary": "Risk-on"},
                    }
                ]
            }
        )
        out = query_research(
            client,
            run_date=date(2026, 6, 20),
            document_key="digest",
            as_of_date=date(2026, 6, 19),
        )
        assert out["source"] == "daily_snapshots"
        assert out["payload"] == {"one_line_summary": "Risk-on"}

    def test_segment_alias_maps_to_document_key(self) -> None:
        client = FakeSupabaseClient(
            canned_reads={
                "documents": [
                    {
                        "date": "2026-06-19",
                        "document_key": "equity",
                        "payload": {"bias": "bullish"},
                    }
                ]
            }
        )
        out = query_research(
            client,
            run_date=date(2026, 6, 20),
            segment="equity",
        )
        assert out["document_key"] == "equity"
        assert out["payload"]["bias"] == "bullish"

    def test_default_as_of_is_latest_before_run_date(self) -> None:
        client = FakeSupabaseClient(
            canned_reads={
                "documents": [
                    {
                        "date": "2026-06-19",
                        "document_key": "macro",
                        "payload": {"headline": "latest"},
                    }
                ]
            }
        )
        out = query_research(client, run_date=date(2026, 6, 20), document_key="macro")
        assert out["as_of_date"] == "2026-06-19"

    def test_cache_hit_for_latest_segment(self) -> None:
        client = FakeSupabaseClient(canned_reads={"documents": []})
        cache = ResearchCache(
            latest_segments={
                "macro": {
                    "date": "2026-06-19",
                    "document_key": "macro",
                    "payload": {"headline": "cached"},
                }
            },
            last_snapshots=[],
        )
        out = query_research(
            client,
            run_date=date(2026, 6, 20),
            document_key="macro",
            cache=cache,
        )
        assert out["payload"]["headline"] == "cached"
        assert out["cache_hit"] is True


@pytest.mark.unit
class TestFetchPriorDocument:
    def test_wraps_query_research_full_body(self) -> None:
        retriever = ResearchRetriever(
            client=FakeSupabaseClient(
                canned_reads={
                    "documents": [
                        {
                            "date": "2026-06-19",
                            "document_key": "macro",
                            "payload": {"headline": "full body"},
                        }
                    ]
                }
            ),
            run_date=date(2026, 6, 20),
            phase="research_edit",
        )
        assert retriever.fetch_prior_document("macro") == {"headline": "full body"}

    def test_section_path_navigation(self) -> None:
        retriever = ResearchRetriever(
            client=FakeSupabaseClient(
                canned_reads={
                    "documents": [
                        {
                            "date": "2026-06-19",
                            "document_key": "macro",
                            "payload": {"sections": {"rates": {"view": "higher"}}},
                        }
                    ]
                }
            ),
            run_date=date(2026, 6, 20),
            phase="research_edit",
        )
        assert retriever.fetch_prior_document("macro", section_path="/sections/rates") == {
            "view": "higher"
        }


@pytest.mark.unit
class TestQueryPortfolio:
    def test_returns_positions_nav_theses_lessons(self) -> None:
        client = FakeSupabaseClient(
            canned_reads={
                "positions": [
                    {"date": "2026-06-19", "ticker": "SPY", "weight_pct": 12.0},
                ],
                "nav_history": [
                    {"date": "2026-06-19", "nav": 1.02, "cash_pct": 5.0, "invested_pct": 95.0},
                ],
                "theses": [
                    {
                        "date": "2026-06-19",
                        "thesis_id": "t1",
                        "name": "AI capex",
                        "vehicle": "SMH",
                        "status": "ACTIVE",
                    }
                ],
                "decision_log": [
                    {
                        "id": "1",
                        "run_date": "2026-06-18",
                        "ticker": "SPY",
                        "status": "resolved",
                        "reflection": "waited for confirmation",
                    }
                ],
                "portfolio_metrics": [
                    {
                        "date": "2026-06-19",
                        "pnl_pct": 0.01,
                        "sharpe": 1.2,
                        "volatility": 0.1,
                        "max_drawdown": -0.05,
                        "alpha": 0.002,
                    }
                ],
            }
        )
        out = query_portfolio(
            client,
            run_date=date(2026, 6, 20),
            phase="h7_pm",
            as_of_date=date(2026, 6, 19),
            watchlist=("SPY",),
        )
        assert out["as_of_date"] == "2026-06-19"
        assert out["positions"] == [{"date": "2026-06-19", "ticker": "SPY", "weight_pct": 12.0}]
        assert out["nav"]["nav"] == 1.02
        assert out["theses"][0]["thesis_id"] == "t1"
        assert out["decision_lessons"][0]["reflection"] == "waited for confirmation"

    def test_ticker_filter(self) -> None:
        client = FakeSupabaseClient(
            canned_reads={
                "positions": [
                    {"date": "2026-06-19", "ticker": "SPY", "weight_pct": 12.0},
                    {"date": "2026-06-19", "ticker": "QQQ", "weight_pct": 8.0},
                ],
                "nav_history": [],
                "theses": [],
                "decision_log": [],
            }
        )
        out = query_portfolio(
            client,
            run_date=date(2026, 6, 20),
            phase="h7_pm",
            as_of_date=date(2026, 6, 19),
            ticker="SPY",
        )
        assert len(out["positions"]) == 1
        assert out["positions"][0]["ticker"] == "SPY"

    def test_prior_published_fallback(self) -> None:
        client = FakeSupabaseClient(
            canned_reads={
                "positions": [
                    {"date": "2026-06-17", "ticker": "SPY", "weight_pct": 10.0},
                ],
                "nav_history": [],
                "theses": [],
                "decision_log": [],
            }
        )
        out = query_portfolio(
            client,
            run_date=date(2026, 6, 20),
            phase="h7_pm",
            as_of_date=date(2026, 6, 19),
        )
        assert out["as_of_date"] == "2026-06-17"

    def test_house_book_ignores_same_date_overlay_rows(self) -> None:
        overlay = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        house = str(house_workspace_id())
        client = FakeSupabaseClient(
            canned_reads={
                "positions": [
                    {
                        "date": "2026-06-19",
                        "ticker": "SPY",
                        "weight_pct": 12.0,
                        "workspace_id": house,
                    },
                    {
                        "date": "2026-06-19",
                        "ticker": "OVERLAY",
                        "weight_pct": 99.0,
                        "workspace_id": overlay,
                    },
                ],
                "nav_history": [
                    {
                        "date": "2026-06-19",
                        "nav": 1.02,
                        "cash_pct": 5.0,
                        "invested_pct": 95.0,
                        "workspace_id": house,
                    },
                    {
                        "date": "2026-06-19",
                        "nav": 999.0,
                        "cash_pct": 0.0,
                        "invested_pct": 100.0,
                        "workspace_id": overlay,
                    },
                ],
                "theses": [],
                "decision_log": [],
            }
        )
        out = query_portfolio(
            client,
            run_date=date(2026, 6, 20),
            phase="h7_pm",
            as_of_date=date(2026, 6, 19),
        )
        assert [row["ticker"] for row in out["positions"]] == ["SPY"]
        assert out["nav"]["nav"] == 1.02

    def test_overlay_only_as_of_does_not_seed_house_fallback(self) -> None:
        overlay = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        house = str(house_workspace_id())
        client = FakeSupabaseClient(
            canned_reads={
                "positions": [
                    {
                        "date": "2026-06-17",
                        "ticker": "SPY",
                        "weight_pct": 10.0,
                        "workspace_id": house,
                    },
                    {
                        "date": "2026-06-19",
                        "ticker": "OVERLAY",
                        "weight_pct": 99.0,
                        "workspace_id": overlay,
                    },
                ],
                "nav_history": [
                    {"date": "2026-06-17", "nav": 1.01, "workspace_id": house},
                    {"date": "2026-06-19", "nav": 999.0, "workspace_id": overlay},
                ],
                "theses": [],
                "decision_log": [],
            }
        )
        out = query_portfolio(
            client,
            run_date=date(2026, 6, 20),
            phase="h7_pm",
            as_of_date=date(2026, 6, 19),
        )
        assert out["as_of_date"] == "2026-06-17"
        assert out["positions"][0]["ticker"] == "SPY"
        assert out["nav"]["nav"] == 1.01


@pytest.mark.unit
class TestBlinding:
    def test_h5_analyst_blocks_portfolio(self) -> None:
        assert portfolio_tool_allowed("h5_analyst") is False
        out = query_portfolio(
            FakeSupabaseClient(),
            run_date=date(2026, 6, 20),
            phase="h5_analyst",
        )
        assert "error" in out

    def test_h5_analyst_blocks_analyst_documents(self) -> None:
        assert research_document_allowed("h5_analyst", "analyst/SPY") is False
        out = query_research(
            FakeSupabaseClient(),
            run_date=date(2026, 6, 20),
            document_key="analyst/SPY",
            phase="h5_analyst",
        )
        assert "error" in out

    def test_h5_analyst_allows_macro_segment(self) -> None:
        assert research_document_allowed("h5_analyst", "macro") is True
        client = FakeSupabaseClient(
            canned_reads={
                "documents": [
                    {
                        "date": "2026-06-19",
                        "document_key": "macro",
                        "payload": {"headline": "ok"},
                    }
                ]
            }
        )
        out = query_research(
            client,
            run_date=date(2026, 6, 20),
            document_key="macro",
            phase="h5_analyst",
        )
        assert "error" not in out

    def test_h6_blocks_portfolio(self) -> None:
        assert portfolio_tool_allowed("h6_deliberation") is False

    def test_h7_allows_portfolio(self) -> None:
        assert portfolio_tool_allowed("h7_pm") is True

    def test_h1_allows_digest_and_portfolio(self) -> None:
        assert research_document_allowed("h1_thesis", "digest") is True
        assert portfolio_tool_allowed("h1_thesis") is True

    def test_h6_blocks_portfolio_query(self) -> None:
        out = query_portfolio(
            FakeSupabaseClient(),
            run_date=date(2026, 6, 20),
            phase="h6_deliberation",
        )
        assert "error" in out


@pytest.mark.unit
class TestBlindedPromptGuards:
    def test_h5_rejects_prior_book_in_prompt(self) -> None:
        with pytest.raises(ValueError, match="blinded keys"):
            assert_blinded_h5_prompt({"ticker": "AAPL", "prior_book": []})

    def test_h6_rejects_materiality_features(self) -> None:
        with pytest.raises(ValueError, match="blinded keys"):
            assert_blinded_h6_prompt({"ticker": "AAPL", "weight_pct": 12.0})

    def test_strip_removes_portfolio_keys_for_h6(self) -> None:
        stripped = strip_blinded_forbidden_keys(
            {
                "ticker": "AAPL",
                "analyst_payload": {"stance": "hold"},
                "prior_book": [{"ticker": "MSFT"}],
                "transcript": [],
            },
            role="h6_deliberation",
        )
        assert "prior_book" not in stripped
        assert stripped["analyst_payload"]["stance"] == "hold"
        assert stripped["transcript"] == []


def _macro_legacy_ref() -> LegacyDocumentRef:
    digest = content_digest({"document_key": "macro", "payload_hash": "abc"})
    return LegacyDocumentRef(
        legacy_ref_id=legacy_document_ref_id(
            document_key="macro",
            as_of_date="2026-08-20",
            source_hash=digest,
        ),
        document_key="macro",
        as_of_date="2026-08-20",
        source_table="documents",
        source_hash=digest,
    )


def _manifest_with_legacy(*, legacy: LegacyDocumentRef) -> tuple[LoadedResearchState, object]:
    evidence = _evidence(summary="revenue beat")
    loaded = _loaded_state(evidence=(evidence,), legacy_refs=(legacy,))
    capsule, manifest = compile_context_capsule(
        ContextCompileInput(
            role=ContextRole.H5_ANALYST,
            state=loaded,
            ticker="AAPL",
        )
    )
    return loaded, manifest


@pytest.mark.unit
class TestRetrievalManifestPinning:
    def test_enforce_rejects_unpinned_dispatcher(self) -> None:
        execute = build_research_tool_dispatcher(
            FakeSupabaseClient(),
            run_date=date(2026, 6, 20),
            phase="h5_analyst",
            pin_mode=RetrievalManifestMode.ENFORCE,
        )
        out = execute("query_research", {"document_key": "macro", "as_of_date": "2026-06-19"})
        assert out.startswith("Error:")
        assert "manifest pin" in out

    def test_enforce_rejects_latest_date_fallback(self) -> None:
        legacy = _macro_legacy_ref()
        loaded, manifest = _manifest_with_legacy(legacy=legacy)
        pin = build_retrieval_query_pin(
            manifest=manifest,
            state=loaded,
            mode=RetrievalManifestMode.ENFORCE,
        )
        out = query_research(
            FakeSupabaseClient(
                canned_reads={
                    "documents": [
                        {
                            "date": legacy.as_of_date,
                            "document_key": legacy.document_key,
                            "payload": {"headline": "ok"},
                        }
                    ]
                }
            ),
            run_date=date(2026, 8, 26),
            document_key=legacy.document_key,
            phase="research_edit",
            retrieval_pin=pin,
        )
        assert "error" in out
        assert "as_of_date required" in out["error"]

    def test_document_access_resolves_through_manifest(self) -> None:
        legacy = _macro_legacy_ref()
        loaded, manifest = _manifest_with_legacy(legacy=legacy)
        pin = build_retrieval_query_pin(
            manifest=manifest,
            state=loaded,
            mode=RetrievalManifestMode.ENFORCE,
        )
        client = FakeSupabaseClient(
            canned_reads={
                "documents": [
                    {
                        "date": legacy.as_of_date,
                        "document_key": legacy.document_key,
                        "payload": {"headline": "manifest ok"},
                    }
                ]
            }
        )
        allowed = query_research(
            client,
            run_date=date(2026, 8, 26),
            document_key=legacy.document_key,
            as_of_date=date.fromisoformat(legacy.as_of_date),
            phase="research_edit",
            retrieval_pin=pin,
        )
        assert allowed["payload"]["headline"] == "manifest ok"
        assert allowed["context_manifest_id"] == str(manifest.manifest_id)

        blocked = query_research(
            client,
            run_date=date(2026, 8, 26),
            document_key="equity",
            as_of_date=date(2026, 8, 20),
            phase="research_edit",
            retrieval_pin=pin,
        )
        assert "error" in blocked
        assert "not permitted" in blocked["error"]

    def test_shadow_records_visible_fallback_reason(self) -> None:
        legacy = _macro_legacy_ref()
        loaded, manifest = _manifest_with_legacy(legacy=legacy)
        pin = build_retrieval_query_pin(
            manifest=manifest,
            state=loaded,
            mode=RetrievalManifestMode.SHADOW,
        )
        out = query_research(
            FakeSupabaseClient(canned_reads={"documents": []}),
            run_date=date(2026, 8, 26),
            document_key="equity",
            as_of_date=date(2026, 8, 20),
            phase="research_edit",
            retrieval_pin=pin,
        )
        assert "retrieval_pin_shadow" in out
        assert "not permitted" in out["retrieval_pin_shadow"]

    def test_pre_call_manifest_persisted(self) -> None:
        legacy = _macro_legacy_ref()
        loaded, manifest = _manifest_with_legacy(legacy=legacy)
        store = RoleRetrievalManifestStore()
        record = persist_pre_call_role_manifest(
            store,
            run_id="run-wp144",
            attempt_id="attempt-h5",
            manifest=manifest,
            recorded_at=_TS,
        )
        loaded_row = store.pre_call_manifest_for_attempt(
            run_id="run-wp144",
            attempt_id="attempt-h5",
            role=manifest.role.value,
        )
        assert loaded_row == record
        assert loaded_row.estimated_tokens == manifest.estimated_tokens
        assert loaded_row.state_version_id == manifest.state_version_id

    def test_estimated_tokens_linked_without_manifest_mutation(self) -> None:
        legacy = _macro_legacy_ref()
        loaded, manifest = _manifest_with_legacy(legacy=legacy)
        store = RoleRetrievalManifestStore()
        persist_pre_call_role_manifest(
            store,
            run_id="run-wp144",
            attempt_id="attempt-h5",
            manifest=manifest,
            recorded_at=_TS,
        )
        before_hash = manifest.content_hash
        before_tokens = manifest.estimated_tokens
        usage = ActualProviderAttemptUsage(
            provider_attempt_id=uuid4(),
            prompt_tokens=1200,
            completion_tokens=300,
        )
        link = link_manifest_provider_tokens(
            store,
            manifest=manifest,
            usage=usage,
            recorded_at=_TS,
        )
        assert link.estimated_tokens == before_tokens
        assert link.actual_prompt_tokens == 1200
        assert manifest.content_hash == before_hash
        assert manifest.estimated_tokens == before_tokens
        links = store.token_links_for_manifest(manifest.manifest_id)
        assert len(links) == 1
        assert links[0].link_id == link.link_id

    def test_retriever_honors_pin(self) -> None:
        legacy = _macro_legacy_ref()
        loaded, manifest = _manifest_with_legacy(legacy=legacy)
        pin = build_retrieval_query_pin(
            manifest=manifest,
            state=loaded,
            mode=RetrievalManifestMode.ENFORCE,
        )
        retriever = ResearchRetriever(
            client=FakeSupabaseClient(
                canned_reads={
                    "documents": [
                        {
                            "date": legacy.as_of_date,
                            "document_key": legacy.document_key,
                            "payload": {"headline": "via retriever"},
                        }
                    ]
                }
            ),
            run_date=date(2026, 8, 26),
            phase="research_edit",
            retrieval_pin=pin,
        )
        out = retriever.fetch_prior_document(
            legacy.document_key,
            as_of_date=date.fromisoformat(legacy.as_of_date),
        )
        assert out == {"headline": "via retriever"}

    def test_default_retrieval_manifest_mode_is_shadow(self) -> None:
        assert resolve_retrieval_manifest_mode() is RetrievalManifestMode.SHADOW


@pytest.mark.unit
class TestRetrievalTransientRetry:
    """Disconnect / PGRST002 / 502 retry 3× before the Error contract (#3299)."""

    def _flaky_documents(self, failures: int) -> FakeSupabaseClient:
        import httpx

        client = FakeSupabaseClient(
            canned_reads={
                "documents": [
                    {
                        "date": "2026-06-19",
                        "document_key": "macro",
                        "payload": {"headline": "Fri macro"},
                    },
                ]
            }
        )
        state = {"attempts": 0}
        orig_table = client.table

        def _table(name: str):  # type: ignore[no-untyped-def]
            query = orig_table(name)
            inner = query.execute

            def _execute():  # type: ignore[no-untyped-def]
                state["attempts"] += 1
                if state["attempts"] <= failures:
                    raise httpx.ReadTimeout(
                        "The read operation timed out",
                        request=httpx.Request("GET", "https://x.supabase.co/rest/v1/t"),
                    )
                return inner()

            query.execute = _execute  # type: ignore[method-assign]
            return query

        client.table = _table  # type: ignore[method-assign]
        client.retry_attempts = state  # type: ignore[attr-defined]
        return client

    def test_query_research_retries_then_returns(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import time

        monkeypatch.setattr(time, "sleep", lambda _s: None)
        client = self._flaky_documents(failures=2)
        out = query_research(
            client,
            run_date=date(2026, 6, 20),
            document_key="macro",
            as_of_date=date(2026, 6, 19),
        )
        assert out["payload"] == {"headline": "Fri macro"}
        assert client.retry_attempts["attempts"] == 3  # type: ignore[attr-defined]

    def test_query_research_gives_error_after_three_attempts(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import time

        monkeypatch.setattr(time, "sleep", lambda _s: None)
        client = self._flaky_documents(failures=10)
        out = query_research(
            client,
            run_date=date(2026, 6, 20),
            document_key="macro",
            as_of_date=date(2026, 6, 19),
        )
        assert "error" in out
        assert client.retry_attempts["attempts"] == 3  # type: ignore[attr-defined]


class _FakeArchiveStore:
    """In-memory StorageBackend double for archive read-through tests (#3792)."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, data: bytes) -> None:
        self.objects[key] = data

    def get(self, key: str) -> bytes:
        return self.objects[key]

    def delete(self, key: str) -> None:
        del self.objects[key]

    def list_keys(self, prefix: str) -> list[str]:
        return sorted(k for k in self.objects if k.startswith(prefix))


def _seed_document_pointer(
    client: FakeSupabaseClient,
    store: _FakeArchiveStore,
    *,
    workspace: str,
    key: str,
    date_str: str,
    payload: dict[str, object],
) -> None:
    """Archive *payload* into *store* and register the pointer row (#3792)."""
    import hashlib
    import json

    from digiquant.ops.checkpoint_archive import compress_payload
    from digiquant.ops.checkpoint_archive import document_key as archive_document_key

    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    stored = compress_payload(raw)
    r2_key = archive_document_key(workspace, date_str, key)
    store.put(r2_key, stored)
    client.canned_reads.setdefault("archive_objects", []).append(
        {
            "source_table": "documents",
            "source_key": {
                "workspace_id": workspace,
                "document_key": key,
                "date": date_str,
            },
            "r2_key": r2_key,
            "sha256": hashlib.sha256(stored).hexdigest(),
            "size": len(stored),
            "owner": "house",
        }
    )


@pytest.mark.unit
class TestQueryResearchArchiveReadthrough:
    """Archived older versions read through R2 instead of degrading as missing (#3792)."""

    def test_archived_fallback_reads_through_r2(self) -> None:
        house = str(house_workspace_id())
        payload = {"headline": "archived Thu macro"}
        client = FakeSupabaseClient(
            canned_reads={
                "documents": [
                    {
                        "date": "2026-06-18",
                        "document_key": "macro",
                        "payload": None,
                    }
                ]
            }
        )
        store = _FakeArchiveStore()
        _seed_document_pointer(
            client,
            store,
            workspace=house,
            key="macro",
            date_str="2026-06-18",
            payload=payload,
        )
        out = query_research(
            client,
            run_date=date(2026, 6, 20),
            document_key="macro",
            as_of_date=date(2026, 6, 19),
            store=store,
        )
        assert out["payload"] == payload
        assert out["as_of_date"] == "2026-06-18"

    def test_archived_fallback_without_pointer_stays_missing(self) -> None:
        client = FakeSupabaseClient(
            canned_reads={
                "documents": [
                    {
                        "date": "2026-06-18",
                        "document_key": "macro",
                        "payload": None,
                    }
                ]
            }
        )
        out = query_research(
            client,
            run_date=date(2026, 6, 20),
            document_key="macro",
            as_of_date=date(2026, 6, 19),
            store=_FakeArchiveStore(),
        )
        assert out == {"error": "no research row found for 'macro' as of 2026-06-19"}


@pytest.mark.unit
class TestSearchResearch:
    """#4436: the filterable, paginated, R2-read-through research search tool."""

    def _client(self) -> FakeSupabaseClient:
        return FakeSupabaseClient(
            canned_reads={
                "documents": [
                    {
                        "date": "2026-06-19",
                        "document_key": "deep-dives/AAPL",
                        "title": "Apple deep dive",
                        "doc_type": "deep-dive",
                        "category": "equity",
                        "segment": "equity",
                        "sector": "Technology",
                        "run_type": "baseline",
                        "content": "x" * 600,
                        "payload": {"thesis": "services margin"},
                        "workspace_id": str(house_workspace_id()),
                    },
                    {
                        "date": "2026-06-19",
                        "document_key": "macro",
                        "title": "Macro board",
                        "doc_type": "macro",
                        "category": "macro",
                        "segment": "macro",
                        "sector": None,
                        "run_type": "baseline",
                        "content": "short",
                        "payload": {"regime": "tight"},
                        "workspace_id": str(house_workspace_id()),
                    },
                    {
                        "date": "2026-05-01",
                        "document_key": "deep-dives/AAPL",
                        "title": "Apple prior",
                        "doc_type": "deep-dive",
                        "category": "equity",
                        "segment": "equity",
                        "sector": "Technology",
                        "run_type": "baseline",
                        "content": "prior body",
                        "payload": {"thesis": "old"},
                        "workspace_id": str(house_workspace_id()),
                    },
                ]
            }
        )

    def test_default_single_day_baseline_documents(self) -> None:
        out = search_research(self._client(), run_date=date(2026, 6, 19))
        assert out["dataset"] == "documents"
        assert out["run_type"] == "baseline"
        assert out["date_from"] == "2026-06-19"
        assert out["date_to"] == "2026-06-19"
        keys = {row["document_key"] for row in out["rows"]}
        assert keys == {"deep-dives/AAPL", "macro"}

    def test_include_prior_spans_history(self) -> None:
        out = search_research(
            self._client(),
            run_date=date(2026, 6, 19),
            document_key="deep-dives/AAPL",
            include_prior=True,
        )
        assert out["include_prior"] is True
        assert out["date_from"] is None
        assert {row["date"] for row in out["rows"]} == {"2026-06-19", "2026-05-01"}

    def test_date_range_filter(self) -> None:
        out = search_research(
            self._client(),
            run_date=date(2026, 6, 19),
            date_from=date(2026, 5, 1),
            date_to=date(2026, 6, 19),
        )
        assert out["row_count"] == 3

    def test_no_lookahead_past_anchor(self) -> None:
        out = search_research(
            self._client(),
            run_date=date(2026, 5, 15),
            date_to=date(2026, 6, 30),
            include_prior=True,
        )
        # Upper bound clamps to the anchor; the 2026-06-19 rows are excluded.
        assert out["date_to"] == "2026-05-15"
        assert {row["date"] for row in out["rows"]} == {"2026-05-01"}

    def test_future_as_of_date_cannot_read_past_run_date(self) -> None:
        # A caller-supplied future ``as_of_date`` must not widen the window past
        # ``run_date`` — run_date is the hard ceiling.
        out = search_research(
            self._client(),
            run_date=date(2026, 5, 15),
            as_of_date=date(2026, 6, 19),
            include_prior=True,
        )
        assert out["date_to"] == "2026-05-15"
        assert {row["date"] for row in out["rows"]} == {"2026-05-01"}

    def test_daily_snapshots_digest_blocked_for_blinded_phase(self) -> None:
        # ``daily_snapshots`` carries the digest payload, so the phase gate that
        # blinds ``documents/digest`` must apply to this dataset too.
        client = FakeSupabaseClient(
            canned_reads={
                "daily_snapshots": [
                    {"date": "2026-06-19", "snapshot": {"one_line_summary": "H5-BLINDED"}}
                ]
            }
        )
        blocked = search_research(
            client,
            run_date=date(2026, 6, 19),
            dataset="daily_snapshots",
            retrieval_phase="h5_analyst",
        )
        assert blocked["row_count"] == 0

        visible = search_research(
            client,
            run_date=date(2026, 6, 19),
            dataset="daily_snapshots",
            retrieval_phase="h1_thesis",
        )
        assert visible["row_count"] == 1

    def test_sector_filter(self) -> None:
        out = search_research(self._client(), run_date=date(2026, 6, 19), sector="Technology")
        assert out["row_count"] == 1
        assert out["rows"][0]["document_key"] == "deep-dives/AAPL"

    def test_subject_filter_matches_title(self) -> None:
        out = search_research(self._client(), run_date=date(2026, 6, 19), subject="Apple")
        assert out["row_count"] == 1
        assert out["rows"][0]["document_key"] == "deep-dives/AAPL"

    def test_doc_type_filter(self) -> None:
        out = search_research(self._client(), run_date=date(2026, 6, 19), doc_type="macro")
        assert out["row_count"] == 1
        assert out["rows"][0]["document_key"] == "macro"

    def test_segment_alias_resolves_to_document_key(self) -> None:
        out = search_research(self._client(), run_date=date(2026, 6, 19), segment="macro")
        assert out["row_count"] == 1
        assert out["rows"][0]["document_key"] == "macro"

    def test_full_content_returns_untruncated_body(self) -> None:
        out = search_research(
            self._client(),
            run_date=date(2026, 6, 19),
            document_key="deep-dives/AAPL",
            full_content=True,
        )
        assert len(out["rows"][0]["content"]) == 600
        assert "content_truncated" not in out["rows"][0]

    def test_preview_truncates_large_content(self) -> None:
        out = search_research(
            self._client(), run_date=date(2026, 6, 19), document_key="deep-dives/AAPL"
        )
        row = out["rows"][0]
        assert len(row["content"]) == 500
        assert row["content_truncated"] is True

    def test_pagination_limit_and_offset(self) -> None:
        page1 = search_research(self._client(), run_date=date(2026, 6, 19), limit=1, offset=0)
        assert page1["limit"] == 1
        assert page1["row_count"] == 1
        assert len(page1["rows"]) == 1
        page2 = search_research(self._client(), run_date=date(2026, 6, 19), limit=1, offset=1)
        assert page2["row_count"] == 1
        assert page2["rows"][0]["document_key"] != page1["rows"][0]["document_key"]

    def test_limit_is_capped_at_500(self) -> None:
        out = search_research(self._client(), run_date=date(2026, 6, 19), limit=9999)
        assert out["limit"] == 500

    def test_unknown_dataset_returns_error(self) -> None:
        out = search_research(self._client(), run_date=date(2026, 6, 19), dataset="price_history")
        assert "error" in out and "unknown dataset" in out["error"]

    def test_portfolio_dataset_blocked_for_blinded_phase(self) -> None:
        out = search_research(
            self._client(),
            run_date=date(2026, 6, 19),
            dataset="positions",
            retrieval_phase="h5_analyst",
        )
        assert "error" in out and "portfolio" in out["error"]

    def test_portfolio_dataset_allowed_for_pm(self) -> None:
        client = FakeSupabaseClient(
            canned_reads={
                "positions": [
                    {
                        "date": "2026-06-19",
                        "ticker": "AAPL",
                        "weight_pct": 4.0,
                        "workspace_id": str(house_workspace_id()),
                    }
                ]
            }
        )
        out = search_research(
            client, run_date=date(2026, 6, 19), dataset="positions", retrieval_phase="h7_pm"
        )
        assert out["row_count"] == 1
        assert out["rows"][0]["ticker"] == "AAPL"

    def test_decision_log_uses_run_date_column_and_run_id(self) -> None:
        client = FakeSupabaseClient(
            canned_reads={
                "decision_log": [
                    {
                        "run_date": "2026-06-19",
                        "run_id": "r1",
                        "ticker": "AAPL",
                        "stance": "long",
                        "status": "open",
                        "alpha": 0.01,
                        "reflection": "ok",
                    },
                    {
                        "run_date": "2026-06-19",
                        "run_id": "r2",
                        "ticker": "MSFT",
                        "stance": "flat",
                        "status": "closed",
                        "alpha": -0.02,
                        "reflection": "no",
                    },
                ]
            }
        )
        out = search_research(
            client,
            run_date=date(2026, 6, 19),
            dataset="decision_log",
            run_id="r1",
            retrieval_phase="h7_pm",
        )
        assert out["row_count"] == 1
        assert out["rows"][0]["ticker"] == "AAPL"

    def test_documents_archived_payload_hydrated_from_r2(self) -> None:
        payload = {"thesis": "hydrated from r2"}
        store = _FakeArchiveStore()
        client = FakeSupabaseClient(
            canned_reads={
                "documents": [
                    {
                        "date": "2026-06-19",
                        "document_key": "macro",
                        "doc_type": "macro",
                        "run_type": "baseline",
                        "content": "body",
                        "payload": None,
                        "workspace_id": str(house_workspace_id()),
                    }
                ]
            },
            store={},
        )
        # Patch the archive store resolver into the fake client's store path.
        import digiquant.dashboard.research_retrieval.queries as q

        orig = q.read_archived_document

        def _fake_read(_client, _store, *, workspace_id, document_key, date_str):
            return payload

        q.read_archived_document = _fake_read  # type: ignore[assignment]
        try:
            out = search_research(
                client,
                run_date=date(2026, 6, 19),
                document_key="macro",
                store=store,
            )
        finally:
            q.read_archived_document = orig  # type: ignore[assignment]
        assert out["rows"][0]["payload"] == payload

    def test_blinded_phase_drops_blocked_document(self) -> None:
        client = FakeSupabaseClient(
            canned_reads={
                "documents": [
                    {
                        "date": "2026-06-19",
                        "document_key": "digest",
                        "content": "secret",
                        "payload": {},
                        "workspace_id": str(house_workspace_id()),
                    }
                ]
            }
        )
        out = search_research(client, run_date=date(2026, 6, 19), retrieval_phase="h5_analyst")
        assert out["row_count"] == 0
