"""Unit tests for digigraph two-tier context compaction (#399)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any  # score:allow untyped any — OpenAI-style message fixtures

import pytest
from digigraph.compaction import (
    COMPACTION_SUMMARY_TAG,
    CompactionConfig,
    CompactionEvent,
    apply_tier1_truncation,
    apply_tier2_summarisation,
    compact_messages,
    compaction_config_from_env,
    estimate_tokens,
    load_workspace_json,
    maybe_truncate_tool_payload,
    wrap_execute_tool_for_tier1,
)


def _big_tool(content: str, tool_call_id: str = "tc1") -> dict[str, Any]:
    return {"role": "tool", "tool_call_id": tool_call_id, "content": content}


def _msg(role: str, content: str) -> dict[str, Any]:
    return {"role": role, "content": content}


@pytest.fixture()
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("DIGI_RUN_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.mark.unit
class TestCompactionConfig:
    def test_defaults_match_issue_shape(self) -> None:
        cfg = CompactionConfig()
        assert cfg.enabled is True
        assert cfg.token_threshold == 80_000
        assert cfg.keep_recent_messages == 10
        assert cfg.tier1_truncation_kb == 2
        assert cfg.summary_model == "digi/fast"

    def test_env_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DIGI_COMPACTION_ENABLED", "0")
        monkeypatch.setenv("DIGI_COMPACTION_TOKEN_THRESHOLD", "1000")
        monkeypatch.setenv("DIGI_COMPACTION_KEEP_RECENT", "3")
        monkeypatch.setenv("DIGI_COMPACTION_TIER1_KB", "1")
        monkeypatch.setenv("DIGI_COMPACTION_SUMMARY_MODEL", "digi/fast")
        cfg = compaction_config_from_env()
        assert cfg.enabled is False
        assert cfg.token_threshold == 1000
        assert cfg.keep_recent_messages == 3
        assert cfg.tier1_truncation_kb == 1
        assert cfg.summary_model == "digi/fast"


@pytest.mark.unit
class TestTier1Truncation:
    def test_truncates_old_large_tool_results_and_offloads(self, workspace: Path) -> None:
        big = "X" * 3000  # > 2KB
        messages = [
            _msg("system", "sys"),
            _msg("user", "q1"),
            {"role": "assistant", "content": None, "tool_calls": []},
            _big_tool(big, "call_old"),
            _msg("user", "q2"),
            _big_tool(big, "call_recent"),
        ]
        cfg = CompactionConfig(keep_recent_messages=2, tier1_truncation_kb=2)
        view, refs = apply_tier1_truncation(
            messages, cfg, session_id="sess-a", workspace=workspace / "sess-a" / "workspace"
        )
        # Oldest tool result truncated; the one inside the recent window stays intact.
        assert view[3]["content"].startswith("[truncated — full result in workspace/")
        assert "msg_call_old.json" in view[3]["content"]
        assert view[5]["content"] == big
        assert len(refs) == 1
        loaded = load_workspace_json(refs[0])
        assert loaded["content"] == big
        # Input list must not be mutated (non-destructive).
        assert messages[3]["content"] == big

    def test_skips_when_disabled(self, workspace: Path) -> None:
        big = "Y" * 4000
        messages = [_big_tool(big), _msg("user", "keep")]
        cfg = CompactionConfig(enabled=True, keep_recent_messages=0, tier1_truncation_kb=2)
        # enabled path truncates when keep=0 (everything eligible)
        view, refs = apply_tier1_truncation(
            messages, cfg, session_id="s", workspace=workspace / "s" / "workspace"
        )
        assert view[0]["content"].startswith("[truncated")
        assert refs

    def test_wrap_execute_tool_for_tier1_preserves_model_visible_content(
        self, workspace: Path
    ) -> None:
        """Same-turn wrap must not stub content — digillm needs the payload to answer.

        Regression: project-mode RAG with DIGI_RUN_DATA_DIR used to replace digisearch
        JSON (>2 KB) with a workspace stub before digillm injected it, so the model
        synthesized answers from stubs alone.
        """
        cfg = CompactionConfig(tier1_truncation_kb=1)
        refs: list[str] = []
        payload = "Z" * 2000

        def execute(_name: str, _args: dict) -> dict[str, str]:
            return {"content": payload, "rag_sources": []}

        wrapped = wrap_execute_tool_for_tier1(
            execute,
            config=cfg,
            session_id="wrap",
            workspace=workspace / "wrap" / "workspace",
            refs_out=refs,
        )
        out = wrapped("digisearch", {"query": "x"})
        assert isinstance(out, dict)
        assert out["content"] == payload
        assert refs
        assert load_workspace_json(refs[0])["content"] == payload

    def test_maybe_truncate_still_stubs_for_prior_turn_lists(self, workspace: Path) -> None:
        """Prior-turn tier-1 truncation (apply_tier1 / maybe_truncate) still stubs."""
        stub, ref = maybe_truncate_tool_payload(
            "Z" * 2000,
            config=CompactionConfig(tier1_truncation_kb=1),
            session_id="prior",
            msg_id="old_tool",
            workspace=workspace / "prior" / "workspace",
        )
        assert stub.startswith("[truncated — full result in workspace/")
        assert ref is not None
        assert load_workspace_json(ref)["content"] == "Z" * 2000


@pytest.mark.unit
class TestTier2Summarisation:
    def test_triggers_when_over_token_threshold(self, workspace: Path) -> None:
        # Build a transcript well over a low threshold; keep last 2 intact.
        older = [_msg("user", f"old-{i}-" + ("a" * 200)) for i in range(8)]
        recent = [_msg("user", "recent-1"), _msg("assistant", "recent-2")]
        messages = older + recent
        cfg = CompactionConfig(
            token_threshold=50,
            keep_recent_messages=2,
            summary_model="digi/fast",
        )
        assert estimate_tokens(messages) > cfg.token_threshold

        def fake_summarise(msgs: list[dict[str, Any]], *, model: str) -> str:
            assert model == "digi/fast"
            assert len(msgs) == 8
            return "SUMMARY_OF_OLD"

        view, evicted, ref = apply_tier2_summarisation(
            messages,
            cfg,
            session_id="t2",
            workspace=workspace / "t2" / "workspace",
            event_id="evt1",
            summarise=fake_summarise,
        )
        assert evicted == 8
        assert ref is not None
        assert COMPACTION_SUMMARY_TAG in view[0]["content"]
        assert "SUMMARY_OF_OLD" in view[0]["content"]
        assert view[-2:] == recent
        # Evicted originals recoverable from workspace.
        blob = load_workspace_json(ref)
        assert len(blob["messages"]) == 8
        assert blob["messages"][0]["content"].startswith("old-0-")

    def test_does_not_trigger_under_threshold(self, workspace: Path) -> None:
        messages = [_msg("user", "short"), _msg("assistant", "ok")]
        cfg = CompactionConfig(token_threshold=80_000, keep_recent_messages=1)
        view, evicted, ref = apply_tier2_summarisation(
            messages, cfg, session_id="t2", workspace=workspace / "t2" / "workspace"
        )
        assert view == messages
        assert evicted == 0
        assert ref is None

    def test_summary_tag_not_re_summarised(self, workspace: Path) -> None:
        prior_summary = _msg(
            "user",
            f"{COMPACTION_SUMMARY_TAG} already compacted once",
        )
        older = [_msg("user", "evict-me-" + ("b" * 400)) for _ in range(4)]
        recent = [_msg("assistant", "tail")]
        messages = [prior_summary, *older, *recent]
        cfg = CompactionConfig(token_threshold=10, keep_recent_messages=1)

        def fake_summarise(msgs: list[dict[str, Any]], *, model: str) -> str:
            # Prior summary must not appear in the eviction set.
            assert all(COMPACTION_SUMMARY_TAG not in m["content"] for m in msgs)
            return "new-summary"

        view, evicted, _ref = apply_tier2_summarisation(
            messages,
            cfg,
            session_id="tag",
            workspace=workspace / "tag" / "workspace",
            summarise=fake_summarise,
        )
        assert evicted == 4
        # Prior summary preserved; new summary injected; recent kept.
        assert any(
            COMPACTION_SUMMARY_TAG in m["content"] and "already compacted" in m["content"]
            for m in view
        )
        assert any("new-summary" in m["content"] for m in view)
        assert view[-1] == recent[0]


@pytest.mark.unit
class TestCompactMessagesOrchestration:
    def test_tier1_runs_before_tier2(self, workspace: Path) -> None:
        """Large old tool results are truncated first; tier-2 then summarises stubs + text."""
        big = "PAYLOAD-" + ("p" * 4000)
        messages = [
            _msg("system", "sys"),
            _big_tool(big, "old_tool"),
            *[_msg("user", f"turn-{i}-" + ("c" * 300)) for i in range(6)],
            _msg("user", "keep-a"),
            _msg("assistant", "keep-b"),
        ]
        cfg = CompactionConfig(
            token_threshold=100,
            keep_recent_messages=2,
            tier1_truncation_kb=2,
            summary_model="digi/fast",
        )
        seen_evicted: list[dict[str, Any]] = []

        def fake_summarise(msgs: list[dict[str, Any]], *, model: str) -> str:
            seen_evicted.extend(msgs)
            # Tier-1 must already have replaced the large tool body.
            tool_msgs = [m for m in msgs if m.get("role") == "tool"]
            assert tool_msgs
            assert tool_msgs[0]["content"].startswith("[truncated")
            return "tier2-summary"

        result = compact_messages(
            messages,
            cfg,
            session_id="orch",
            workspace=workspace / "orch" / "workspace",
            summarise=fake_summarise,
        )
        assert result.event is not None
        assert result.event.tier1_truncated >= 1
        assert result.event.tier2_triggered is True
        assert result.event.tier2_evicted_count > 0
        assert result.event.tokens_after < result.event.tokens_before
        # Originals preserved on the result (non-destructive).
        assert result.original_messages[1]["content"] == big
        assert any(COMPACTION_SUMMARY_TAG in m.get("content", "") for m in result.llm_messages)

    def test_disabled_returns_copy_without_event(self) -> None:
        messages = [_msg("user", "hi")]
        result = compact_messages(messages, CompactionConfig(enabled=False))
        assert result.event is None
        assert result.llm_messages == messages
        assert result.llm_messages is not messages

    def test_event_shape_for_langgraph_state(self, workspace: Path) -> None:
        messages = [
            _big_tool("Q" * 3000, "t1"),
            _msg("user", "u"),
        ]
        cfg = CompactionConfig(keep_recent_messages=1, tier1_truncation_kb=2, token_threshold=10)
        result = compact_messages(
            messages,
            cfg,
            session_id="evt",
            workspace=workspace / "evt" / "workspace",
            summarise=lambda msgs, *, model: "s",
        )
        assert result.event is not None
        payload = result.event.model_dump()
        # WorkflowState stores this dict under `_compaction_event`.
        restored = CompactionEvent.model_validate(payload)
        assert restored.tier1_truncated >= 1
        assert restored.summary_tag == COMPACTION_SUMMARY_TAG


@pytest.mark.unit
class TestResumeAfterCompaction:
    def test_session_resume_reloads_offloaded_payloads(self, workspace: Path) -> None:
        """After compaction, a resumed session can recover originals from workspace refs."""
        big = json.dumps({"prices": list(range(500)), "note": "AAPL history"})
        messages = [
            _msg("system", "sys"),
            _big_tool(big, "prices_1"),
            *[_msg("user", f"hist-{i}-" + ("d" * 250)) for i in range(5)],
            _msg("user", "latest"),
        ]
        cfg = CompactionConfig(
            token_threshold=80,
            keep_recent_messages=1,
            tier1_truncation_kb=1,
            summary_model="digi/fast",
        )
        result = compact_messages(
            messages,
            cfg,
            session_id="resume",
            workspace=workspace / "resume" / "workspace",
            summarise=lambda msgs, *, model: "compacted-history",
        )
        event = result.event
        assert event is not None
        # Simulate resume: load tier-1 + tier-2 blobs from the event (not from llm_messages).
        recovered_tools = [load_workspace_json(r)["content"] for r in event.tier1_refs]
        assert big in recovered_tools
        assert event.tier2_evicted_ref is not None
        evicted = load_workspace_json(event.tier2_evicted_ref)["messages"]
        assert any(isinstance(m.get("content"), str) and "hist-0-" in m["content"] for m in evicted)
        # LLM view must not retain the full price history.
        joined = " ".join(str(m.get("content", "")) for m in result.llm_messages)
        assert big not in joined


@pytest.mark.unit
class TestMaybeTruncate:
    def test_under_threshold_unchanged(self) -> None:
        stub, ref = maybe_truncate_tool_payload(
            "small",
            config=CompactionConfig(tier1_truncation_kb=2),
            session_id=None,
        )
        assert stub == "small"
        assert ref is None

    def test_no_workspace_keeps_full_payload(self) -> None:
        """Without run_data_dir, truncation must not drop the only copy."""
        big = "W" * 4000
        stub, ref = maybe_truncate_tool_payload(
            big,
            config=CompactionConfig(tier1_truncation_kb=1),
            session_id=None,
            workspace=None,
        )
        assert stub == big
        assert ref is None
