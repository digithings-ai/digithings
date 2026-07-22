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


def _patch(ops: list[dict[str, object]]) -> DocumentPatch:
    return DocumentPatch.model_validate(
        {
            "date": "2026-07-22",
            "prior_date": "2026-07-21",
            "target_document_key": "inst-institutional-flows",
            "status": "updated",
            "ops": ops,
        }
    )


@pytest.mark.unit
class TestMergeAppendTokenAndClamps:
    """#1641 regressions — RFC 6901 ``-`` append token + fail-soft list indices.

    Exact defect signatures from runs 29846393424 / 29925232768:
    ``invalid literal for int() with base 10: '-'``, ``list assignment index out of
    range``, ``duplicate set on path '/material_findings/-' in one patch``.
    """

    def test_set_on_append_token_appends(self) -> None:
        from digiquant.olympus.edit_mode import apply_ops

        doc = apply_ops(
            {"material_findings": [{"t": "old"}]},
            [{"op": "set", "path": "/material_findings/-", "value": {"t": "new"}}],
        )
        assert [f["t"] for f in doc["material_findings"]] == ["old", "new"]

    def test_two_sets_on_append_token_are_sequential_appends(self) -> None:
        result = merge_document_patch(
            {"material_findings": ["a"]},
            _patch(
                [
                    {"op": "set", "path": "/material_findings/-", "value": "b"},
                    {"op": "set", "path": "/material_findings/-", "value": "c"},
                ]
            ),
        )
        assert result.materialized["material_findings"] == ["a", "b", "c"]

    def test_duplicate_set_on_concrete_path_still_rejected(self) -> None:
        with pytest.raises(MergeError, match="duplicate set"):
            merge_document_patch(
                {"headline": "x"},
                _patch(
                    [
                        {"op": "set", "path": "/headline", "value": "y"},
                        {"op": "set", "path": "/headline", "value": "z"},
                    ]
                ),
            )

    def test_set_past_end_index_appends_instead_of_index_error(self) -> None:
        from digiquant.olympus.edit_mode import apply_ops

        doc = apply_ops(
            {"notable_filings": ["a", "b"]},
            [{"op": "set", "path": "/notable_filings/7", "value": "c"}],
        )
        assert doc["notable_filings"] == ["a", "b", "c"]

    def test_append_via_append_token_targets_the_list_itself(self) -> None:
        from digiquant.olympus.edit_mode import apply_ops

        doc = apply_ops(
            {"material_findings": ["a"]},
            [{"op": "append", "path": "/material_findings/-", "value": "b"}],
        )
        assert doc["material_findings"] == ["a", "b"]

    def test_remove_append_token_pops_last_and_oor_is_noop(self) -> None:
        from digiquant.olympus.edit_mode import apply_ops

        doc = apply_ops(
            {"xs": ["a", "b", "c"]},
            [
                {"op": "remove", "path": "/xs/-"},
                {"op": "remove", "path": "/xs/9"},
            ],
        )
        assert doc["xs"] == ["a", "b"]

    def test_mid_path_append_token_addresses_last_element(self) -> None:
        from digiquant.olympus.edit_mode import apply_ops

        doc = apply_ops(
            {"material_findings": [{"note": "old1"}, {"note": "old2"}]},
            [{"op": "set", "path": "/material_findings/-/note", "value": "patched"}],
        )
        assert doc["material_findings"][-1]["note"] == "patched"

    def test_unresolvable_op_raises_merge_error_not_raw_crash(self) -> None:
        with pytest.raises(MergeError):
            merge_document_patch(
                {"headline": "x"},
                _patch([{"op": "set", "path": "/headline/3", "value": "y"}]),
            )
