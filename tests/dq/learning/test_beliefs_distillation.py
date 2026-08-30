"""Beliefs distillation — on-demand learning loop (Olympus #930, spec §11.1)."""

from __future__ import annotations

from datetime import date
from typing import (
    Any,  # score:allow untyped any — scored-lint: heterogeneous fake-row / fixture dicts
)

import pytest
from digiquant.olympus.atlas.phases.preflight import (
    PreflightReflectDeps,
    build_preflight_reflect_node,
)
from digiquant.olympus.atlas.state import AtlasResearchState
from digiquant.olympus.learning.beliefs_distillation import (
    DAILY_BELIEFS_MAX_TOKENS,
    DEFAULT_BELIEFS_BACKLOG,
    beliefs_backlog_threshold,
    count_unfolded_resolved_decisions,
    distill_beliefs,
    resolve_beliefs_fold_mode,
    should_distill_beliefs,
)

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient


def _resolved_row(*, row_id: str, folded: bool = False) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": row_id,
        "run_id": "11111111-2222-3333-4444-555555555555",
        "run_date": "2026-04-10",
        "ticker": "AAPL",
        "stance": "buy",
        "conviction": 3,
        "thesis": "t",
        "benchmark": "SPY",
        "holding_days": 5,
        "status": "resolved",
        "reflection": "lesson",
    }
    if folded:
        row["beliefs_folded_at"] = "2026-04-20T00:00:00+00:00"
    return row


@pytest.mark.unit
class TestBeliefsTrigger:
    def test_operator_refresh_scope_forces_full_rewrite(self) -> None:
        assert should_distill_beliefs(refresh_scope="beliefs", backlog_count=0) is True
        assert resolve_beliefs_fold_mode(refresh_scope="beliefs", backlog_count=0) == "full"

    def test_daily_house_run_always_short_folds(self) -> None:
        """WP-I: house daily path folds even with an empty decision_log backlog."""
        assert should_distill_beliefs(refresh_scope="none", backlog_count=0) is True
        assert resolve_beliefs_fold_mode(refresh_scope="none", backlog_count=0) == "short"
        threshold = beliefs_backlog_threshold()
        assert threshold == DEFAULT_BELIEFS_BACKLOG
        assert should_distill_beliefs(refresh_scope="none", backlog_count=threshold) is True
        assert resolve_beliefs_fold_mode(refresh_scope="none", backlog_count=threshold) == "short"

    def test_backlog_above_threshold_is_full_fold(self) -> None:
        threshold = beliefs_backlog_threshold()
        assert should_distill_beliefs(refresh_scope="none", backlog_count=threshold + 1) is True
        assert (
            resolve_beliefs_fold_mode(refresh_scope="none", backlog_count=threshold + 1) == "full"
        )

    def test_count_unfolded_resolved_decisions(self) -> None:
        rows = [_resolved_row(row_id=f"r{i}") for i in range(3)]
        rows.append(_resolved_row(row_id="folded", folded=True))
        client = FakeSupabaseClient(canned_reads={"decision_log": rows})
        assert count_unfolded_resolved_decisions(client) == 3


@pytest.mark.unit
class TestBeliefsDistillation:
    def test_distill_writes_beliefs_document(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from digiquant.olympus.learning import beliefs_distillation as mod

        rows = [_resolved_row(row_id=f"r{i}") for i in range(2)]
        client = FakeSupabaseClient(canned_reads={"decision_log": rows})
        client.store["decision_log"] = [dict(r) for r in rows]

        monkeypatch.setattr(
            mod,
            "_run_beliefs_llm",
            lambda **_kw: mod.BeliefsBlob(
                schema_version="1.0",
                date=date(2026, 4, 26),
                body="Distilled beliefs body.",
            ),
        )

        written = distill_beliefs(
            client=client,
            run_date=date(2026, 4, 26),
            run_type="delta",
            lessons=rows,
            active_theses=[],
        )

        assert written is True
        docs = client.store.get("documents", [])
        assert len(docs) == 1
        doc = docs[0]
        assert doc["document_key"] == "beliefs"
        assert doc["doc_type"] == "Beliefs"
        assert doc["payload"]["doc_type"] == "beliefs"
        assert doc["payload"]["body"] == "Distilled beliefs body."
        for row in client.store["decision_log"]:
            assert row.get("beliefs_folded_at") is not None

    def test_short_fold_publishes_carry_when_no_unfolded_rows(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """WP-I: empty lesson day still writes a same-date beliefs document."""
        from digiquant.olympus.learning import beliefs_distillation as mod

        prior_body = "Yesterday's durable beliefs about duration risk."
        prior = {
            "date": "2026-04-25",
            "document_key": "beliefs",
            "doc_type": "Beliefs",
            "payload": {"doc_type": "beliefs", "body": prior_body, "schema_version": "1.0"},
        }
        client = FakeSupabaseClient(canned_reads={"decision_log": [], "documents": [prior]})

        def _must_not_call_llm(**_kw: Any) -> mod.BeliefsBlob:
            raise AssertionError("empty-lesson short fold must not call the LLM")

        monkeypatch.setattr(mod, "_run_beliefs_llm", _must_not_call_llm)

        written = distill_beliefs(
            client=client,
            run_date=date(2026, 4, 26),
            run_type="delta",
            lessons=[],
            active_theses=[],
            fold_mode="short",
        )

        assert written is True
        docs = client.store.get("documents", [])
        assert len(docs) == 1
        body = docs[0]["payload"]["body"]
        assert "No new resolved lessons" in body
        assert prior_body in body
        assert docs[0]["date"] == "2026-04-26"
        assert docs[0]["document_key"] == "beliefs"

    def test_short_fold_llm_gets_prior_body_and_todays_lessons(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from digiquant.olympus.learning import beliefs_distillation as mod

        rows = [_resolved_row(row_id="r0")]
        prior_body = "Prior beliefs body."
        prior = {
            "date": "2026-04-25",
            "document_key": "beliefs",
            "doc_type": "Beliefs",
            "payload": {"doc_type": "beliefs", "body": prior_body, "schema_version": "1.0"},
        }
        client = FakeSupabaseClient(canned_reads={"decision_log": rows, "documents": [prior]})
        client.store["decision_log"] = [dict(r) for r in rows]
        captured: dict[str, Any] = {}

        def _capture(**kw: Any) -> mod.BeliefsBlob:
            captured.update(kw)
            return mod.BeliefsBlob(
                schema_version="1.0",
                date=date(2026, 4, 26),
                body="Short fold of today's lesson.",
            )

        monkeypatch.setattr(mod, "_run_beliefs_llm", _capture)

        written = distill_beliefs(
            client=client,
            run_date=date(2026, 4, 26),
            run_type="delta",
            lessons=rows,
            active_theses=[{"thesis_id": "t1"}],
            fold_mode="short",
        )

        assert written is True
        assert captured["fold_mode"] == "short"
        assert captured["prior_body"] == prior_body
        assert captured["lessons"] == rows
        assert captured.get("max_tokens") == DAILY_BELIEFS_MAX_TOKENS

    def test_full_rewrite_omits_short_fold_token_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from digiquant.olympus.learning import beliefs_distillation as mod

        rows = [_resolved_row(row_id="r0")]
        client = FakeSupabaseClient(canned_reads={"decision_log": rows})
        client.store["decision_log"] = [dict(r) for r in rows]
        captured: dict[str, Any] = {}

        def _capture(**kw: Any) -> mod.BeliefsBlob:
            captured.update(kw)
            return mod.BeliefsBlob(
                schema_version="1.0",
                date=date(2026, 4, 26),
                body="Full rewrite body.",
            )

        monkeypatch.setattr(mod, "_run_beliefs_llm", _capture)

        written = distill_beliefs(
            client=client,
            run_date=date(2026, 4, 26),
            run_type="delta",
            lessons=rows,
            active_theses=[{"thesis_id": "t1"}],
            fold_mode="full",
        )

        assert written is True
        assert captured["fold_mode"] == "full"
        assert captured.get("max_tokens") in (None, 0)
        assert client.store["documents"][0]["payload"]["body"] == "Full rewrite body."

    def test_distill_marks_only_lessons_passed_to_llm(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from digiquant.olympus.learning import beliefs_distillation as mod

        all_rows = [_resolved_row(row_id=f"r{i}") for i in range(5)]
        client = FakeSupabaseClient(canned_reads={"decision_log": all_rows})
        client.store["decision_log"] = [dict(r) for r in all_rows]
        subset = all_rows[:2]

        monkeypatch.setattr(
            mod,
            "_run_beliefs_llm",
            lambda **_kw: mod.BeliefsBlob(
                schema_version="1.0",
                date=date(2026, 4, 26),
                body="Distilled beliefs body.",
            ),
        )

        distill_beliefs(
            client=client,
            run_date=date(2026, 4, 26),
            run_type="delta",
            lessons=subset,
            active_theses=[],
        )

        folded = [r for r in client.store["decision_log"] if r.get("beliefs_folded_at")]
        unfolded = [r for r in client.store["decision_log"] if not r.get("beliefs_folded_at")]
        assert len(folded) == 2
        assert len(unfolded) == 3
        assert {r["id"] for r in folded} == {"r0", "r1"}

    def test_chain_entry_daily_short_fold_writes_without_backlog(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from digiquant.olympus.atlas.graph import AtlasInput
        from digiquant.olympus.learning import beliefs_distillation as mod

        client = FakeSupabaseClient(canned_reads={"decision_log": []})

        def _must_not_call_llm(**_kw: Any) -> mod.BeliefsBlob:
            raise AssertionError("empty-backlog daily fold must not call the LLM")

        monkeypatch.setattr(mod, "_run_beliefs_llm", _must_not_call_llm)
        written = mod.run_beliefs_distillation_if_triggered(
            client=client,
            atlas_input=AtlasInput(
                run_date=date(2026, 4, 26),
                refresh_scope="none",
                watchlist=("AAPL",),
            ),
            run_type="delta",
        )
        assert written is True
        docs = client.store.get("documents", [])
        assert len(docs) == 1
        assert docs[0]["document_key"] == "beliefs"
        assert "No new resolved lessons" in docs[0]["payload"]["body"]


@pytest.mark.unit
class TestPreflightReflectDaily:
    def test_atlas_graph_includes_preflight_reflect_when_wired(self) -> None:
        from digiquant.olympus.atlas.graph import AtlasGraphDeps, build_atlas_graph
        from digiquant.olympus.atlas.phases.preflight import PreflightDeps
        from digiquant.olympus.atlas.state import AtlasConfigBundle

        client = FakeSupabaseClient()
        deps = AtlasGraphDeps(
            preflight=PreflightDeps(
                client=client,
                config_loader=lambda: AtlasConfigBundle(watchlist=["AAPL"]),
            ),
            preflight_reflect=PreflightReflectDeps(client=client),
        )
        graph = build_atlas_graph(deps=deps, watchlist=("AAPL",))
        names = set(graph.get_graph().nodes.keys())
        assert "preflight-reflect" in names
        assert "learning/beliefs-distillation" not in names

    def test_preflight_reflect_node_still_resolves_pending(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from digiquant.olympus.atlas.phases import preflight as preflight_module

        called: dict[str, int] = {"resolve": 0}

        def stub_resolve(
            *, client: Any, run_date: Any, reflector: Any, workspace_id: Any = None
        ) -> int:
            called["resolve"] += 1
            return 0

        monkeypatch.setattr(preflight_module, "resolve_pending", stub_resolve)

        client = FakeSupabaseClient()
        node = build_preflight_reflect_node(PreflightReflectDeps(client=client))
        node(AtlasResearchState(run_type="delta", run_date=date(2026, 4, 26)))
        assert called["resolve"] == 1


@pytest.mark.unit
class TestChainBeliefsWiring:
    def test_refresh_scope_beliefs_runs_distillation_only(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from digiquant.olympus.atlas.graph import AtlasInput
        from digiquant.olympus.hermes import chain as chain_mod

        calls: dict[str, int] = {"beliefs": 0, "atlas": 0}

        def _stub_beliefs(**_kw: Any) -> bool:
            calls["beliefs"] += 1
            return True

        def _stub_atlas(*_a: Any, **_k: Any) -> Any:
            calls["atlas"] += 1
            return object()

        monkeypatch.setattr(chain_mod, "run_beliefs_distillation_if_triggered", _stub_beliefs)
        monkeypatch.setattr(chain_mod, "build_atlas_graph", _stub_atlas)

        from digiquant.olympus.atlas.testing.simulator import simulated_pipeline

        with simulated_pipeline(watchlist=("AAPL",)) as run:
            chain_mod.run_atlas_then_hermes(
                atlas_input=AtlasInput(
                    run_date=date(2026, 4, 26),
                    refresh_scope="beliefs",
                    watchlist=("AAPL",),
                ),
                deps=chain_mod.ChainDeps(atlas=run.deps, hermes=run.hermes_deps),
            )

        assert calls["beliefs"] == 1
        assert calls["atlas"] == 0

    def test_daily_hermes_graph_excludes_phase9_evolution(self) -> None:
        from digiquant.olympus.hermes.graph import build_hermes_phases_thesis

        names = [p.name for p in build_hermes_phases_thesis(watchlist=["AAPL"])]
        assert "phase9_evolution" not in names
        assert "beliefs_distillation" not in names
