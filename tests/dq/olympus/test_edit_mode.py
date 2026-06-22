"""Unit tests for digiquant.olympus.edit_mode (spec §4–§5, §16)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from digiquant.olympus.edit_mode import (
    DocumentPatch,
    MergeError,
    PatchOp,
    PriorLoader,
    PriorPublished,
    StubPriorDocumentFetcher,
    TriageSignal,
    artifact_document_key,
    merge_document_patch,
    resolve_edit_mode,
    stale_full_days,
)

_DELTA_EXAMPLE = (
    Path(__file__).resolve().parents[3]
    / "digiquant"
    / "src"
    / "digiquant"
    / "olympus"
    / "atlas"
    / "templates"
    / "delta-request.example.json"
)


class _FakePriorLoader(PriorLoader):
    def __init__(self, prior: PriorPublished | None) -> None:
        self._prior = prior

    def load(self, artifact_key: tuple[str, str], run_date: date) -> PriorPublished | None:
        del artifact_key, run_date
        return self._prior


def _macro_prior(*, prior_date: date) -> PriorPublished:
    return PriorPublished(
        date=prior_date,
        document_key="macro",
        payload={
            "market_data": {"VIX": 20.0},
            "segment_biases": {"macro": {"bias": "Bullish"}},
            "narrative": {"macro": "old narrative"},
            "actionable": ["old action"],
        },
    )


@pytest.mark.unit
class TestResolveEditMode:
    def test_no_prior_returns_full(self) -> None:
        mode = resolve_edit_mode(
            artifact_key=("segment", "macro"),
            run_date=date(2026, 6, 20),
            prior_loader=_FakePriorLoader(None),
            triage=TriageSignal(mode="stale"),
        )
        assert mode == "full"

    def test_prior_quiet_triage_returns_skip(self) -> None:
        prior = _macro_prior(prior_date=date(2026, 6, 19))
        mode = resolve_edit_mode(
            artifact_key=("segment", "macro"),
            run_date=date(2026, 6, 20),
            prior_loader=_FakePriorLoader(prior),
            triage=TriageSignal(mode="quiet"),
        )
        assert mode == "skip"

    def test_prior_stale_triage_returns_edit(self) -> None:
        prior = _macro_prior(prior_date=date(2026, 6, 19))
        mode = resolve_edit_mode(
            artifact_key=("segment", "macro"),
            run_date=date(2026, 6, 20),
            prior_loader=_FakePriorLoader(prior),
            triage=TriageSignal(mode="stale"),
        )
        assert mode == "edit"

    def test_force_full_rewrite_returns_full(self) -> None:
        prior = _macro_prior(prior_date=date(2026, 6, 19))
        mode = resolve_edit_mode(
            artifact_key=("segment", "macro"),
            run_date=date(2026, 6, 20),
            prior_loader=_FakePriorLoader(prior),
            triage=TriageSignal(mode="stale"),
            force_full_rewrite=True,
        )
        assert mode == "full"

    def test_stale_gap_exceeds_env_returns_full(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OLYMPUS_STALE_FULL_DAYS", "7")
        prior = _macro_prior(prior_date=date(2026, 6, 1))
        mode = resolve_edit_mode(
            artifact_key=("segment", "macro"),
            run_date=date(2026, 6, 20),
            prior_loader=_FakePriorLoader(prior),
            triage=TriageSignal(mode="stale"),
        )
        assert mode == "full"

    def test_stale_gap_within_env_returns_edit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OLYMPUS_STALE_FULL_DAYS", "7")
        prior = _macro_prior(prior_date=date(2026, 6, 14))
        mode = resolve_edit_mode(
            artifact_key=("segment", "macro"),
            run_date=date(2026, 6, 20),
            prior_loader=_FakePriorLoader(prior),
            triage=TriageSignal(mode="stale"),
        )
        assert mode == "edit"

    def test_stale_full_days_default_is_seven(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OLYMPUS_STALE_FULL_DAYS", raising=False)
        assert stale_full_days() == 7


@pytest.mark.unit
class TestMergeDocumentPatch:
    def test_golden_ops_from_delta_request_example(self) -> None:
        example = json.loads(_DELTA_EXAMPLE.read_text(encoding="utf-8"))
        prior = {
            "market_data": {"VIX": 20.0},
            "segment_biases": {"macro": {"bias": "Bullish"}},
            "narrative": {"macro": "old narrative"},
            "actionable": ["old action"],
        }
        patch = DocumentPatch(
            schema_version="1.0",
            date=date(2026, 4, 7),
            prior_date=date(2026, 4, 5),
            target_document_key="macro",
            status="updated",
            ops=[PatchOp.model_validate(op) for op in example["ops"]],
        )
        result = merge_document_patch(prior, patch)
        assert result.materialized["market_data"]["VIX"] == 26.4
        assert result.materialized["segment_biases"]["macro"]["bias"] == "Bearish"
        assert result.materialized["narrative"]["macro"].startswith("Update macro")
        assert result.materialized["actionable"] == [
            "Top action item 1 ...",
            "Top action item 2 ...",
        ]
        assert result.merge_stats.ops_applied == 4
        assert len(result.merge_stats.paths_touched) == 4

    def test_skipped_status_returns_prior_unchanged(self) -> None:
        prior = {"headline": "unchanged", "nested": {"a": 1}}
        patch = DocumentPatch(
            schema_version="1.0",
            date=date(2026, 6, 20),
            prior_date=date(2026, 6, 19),
            target_document_key="macro",
            status="skipped",
            skip_reason="quiet day",
            ops=[],
        )
        result = merge_document_patch(prior, patch)
        assert result.materialized == prior
        assert result.merge_stats.ops_applied == 0

    def test_duplicate_set_on_same_path_fails(self) -> None:
        prior = {"headline": "old"}
        patch = DocumentPatch(
            schema_version="1.0",
            date=date(2026, 6, 20),
            prior_date=date(2026, 6, 19),
            target_document_key="macro",
            status="updated",
            ops=[
                PatchOp(op="set", path="/headline", value="first"),
                PatchOp(op="set", path="/headline", value="second"),
            ],
        )
        with pytest.raises(MergeError, match="duplicate"):
            merge_document_patch(prior, patch)

    def test_baseline_date_alias_accepted(self) -> None:
        patch = DocumentPatch.model_validate(
            {
                "schema_version": "1.0",
                "doc_type": "document_delta",
                "date": "2026-06-20",
                "baseline_date": "2026-06-19",
                "target_document_key": "macro",
                "status": "skipped",
                "skip_reason": "quiet",
                "ops": [],
            }
        )
        assert patch.prior_date == date(2026, 6, 19)


@pytest.mark.unit
class TestEditModeTools:
    def test_artifact_document_key_segment(self) -> None:
        assert artifact_document_key(("segment", "macro")) == "macro"

    def test_artifact_document_key_namespaced(self) -> None:
        assert artifact_document_key(("analyst", "SPY")) == "analyst/SPY"

    def test_stub_fetch_prior_document(self) -> None:
        fetcher = StubPriorDocumentFetcher(
            {
                ("macro", None): {"headline": "full body"},
                ("macro", date(2026, 6, 19)): {"headline": "as of prior"},
            }
        )
        assert fetcher.fetch_prior_document("macro") == {"headline": "full body"}
        assert fetcher.fetch_prior_document("macro", as_of_date=date(2026, 6, 19)) == {
            "headline": "as of prior"
        }
