"""Content-freeze detection and provenance (#1749, #1751) — the pure ``edit_mode`` half.

An edit-mode merge can succeed structurally and change nothing: the model emits ``set`` ops
whose values already hold, or declares ``status="skipped"``. The pipeline then republished the
byte-identical body under the run date marked ``source="today"``, which

  * showed a ``today`` freshness badge over content up to six days old (#1749),
  * reset the §5.3.2 staleness clock so the documented 7-day hard cap could never fire — the
    material half of #1749, and
  * left no telemetry trace at all, so the freeze was discoverable only by hashing payloads in
    SQL after the fact (#1751).

The production shapes these tests encode are real, from the 2026-07-31 review:
``sector-healthcare`` byte-identical on 07-28/07-29/07-31 with a 6-op delta row claiming
``status="updated"``, and ``alt-politician-signals`` publishing five rows carrying one body
across seven days (07-17 → 07-24) at ``gap_days=1`` every run.

The Atlas-side surfaces (freshness badge, diagnostics ``breakdown``, published delta row)
are in ``tests/dq/research/test_content_freeze_surfaces.py``. They import Atlas phases, which
pull ``digigraph`` → ``openai``, and only ``tests/dq/research/conftest.py`` gates collection on
that being installed — so an Atlas import from *this* directory is a collection error in the
``digiquant`` CI lane rather than a skip.
"""

from __future__ import annotations

from datetime import date

import pytest
from digiquant.dashboard.edit_mode import DocumentPatch, PatchOp, PriorPublished, merge_document_patch
from digiquant.dashboard.edit_mode.content_identity import (
    UNCHANGED_FLAG_KEY,
    UNCHANGED_SINCE_KEY,
    bodies_match,
    clear_unchanged,
    mark_unchanged,
    prior_content_date,
)
from digiquant.dashboard.edit_mode.resolve import resolve_edit_mode

from .test_edit_mode import _FakePriorLoader

# The six ops production's 2026-07-31 ``document-deltas/sector-healthcare`` row carried, every
# one of them setting a value the body already held.
_HEALTHCARE_BODY = {
    "segment": "sector-healthcare",
    "date": "2026-07-29",
    "headline": "Healthcare holds its bid",
    "bias": "bullish",
    "relative_strength_vs_spy": "outperforming",
    "sub_segment_leader": "Biotech",
    "driver_confirmation_count": 2,
    "conviction": "medium",
}
_NOOP_OPS = [
    PatchOp(op="set", path="/headline", value="Healthcare holds its bid", reason="Updated market"),
    PatchOp(op="set", path="/bias", value="bullish", reason="Continued outperformance"),
    PatchOp(op="set", path="/relative_strength_vs_spy", value="outperforming", reason="XLV v SPY"),
    PatchOp(op="set", path="/sub_segment_leader", value="Biotech", reason="Biotech leads"),
    PatchOp(op="set", path="/driver_confirmation_count", value=2, reason="Two drivers"),
    PatchOp(op="set", path="/conviction", value="medium", reason="Unchanged conviction"),
]


def _patch(ops: list[PatchOp], *, status: str = "updated") -> DocumentPatch:
    return DocumentPatch(
        schema_version="1.0",
        date=date(2026, 7, 31),
        prior_date=date(2026, 7, 29),
        target_document_key="sector-healthcare",
        status=status,  # type: ignore[arg-type]
        ops=ops,
    )


@pytest.mark.unit
class TestMergeDetectsContentIdentity:
    def test_six_noop_set_ops_report_content_unchanged(self) -> None:
        """The exact production shape: ops_applied=6 AND content_changed=False, together.

        ``ops_applied`` counts ops SUBMITTED, which is why it was never a freeze signal. Both
        numbers are true at once and the pair is the disclosure.
        """
        result = merge_document_patch(dict(_HEALTHCARE_BODY), _patch(_NOOP_OPS))
        assert result.merge_stats.ops_applied == 6
        assert result.merge_stats.content_changed is False

    def test_a_real_change_reports_content_changed(self) -> None:
        ops = [*_NOOP_OPS[:5], PatchOp(op="set", path="/conviction", value="high")]
        result = merge_document_patch(dict(_HEALTHCARE_BODY), _patch(ops))
        assert result.merge_stats.content_changed is True

    def test_skipped_status_reports_content_unchanged(self) -> None:
        """A model-declared skip is the cleaner instance: 13 production delta rows say this."""
        result = merge_document_patch(dict(_HEALTHCARE_BODY), _patch([], status="skipped"))
        assert result.merge_stats.ops_applied == 0
        assert result.merge_stats.content_changed is False

    def test_the_date_key_alone_is_not_content(self) -> None:
        """``date`` is overwritten with the run date right after the merge, so comparing it
        would make every body look changed and the detector would never fire."""
        prior = dict(_HEALTHCARE_BODY)
        later = {**_HEALTHCARE_BODY, "date": "2026-07-31"}
        assert bodies_match(prior, later) is True

    def test_inherited_markers_are_not_content(self) -> None:
        """``prior`` is raw JSONB: once a chain is marked, ``apply_ops`` copies the markers
        into ``materialized``. If they counted as content, the second frozen day would read
        as a change and the chain would reset every other run."""
        marked = {**_HEALTHCARE_BODY, UNCHANGED_FLAG_KEY: True, UNCHANGED_SINCE_KEY: "2026-07-28"}
        result = merge_document_patch(marked, _patch(_NOOP_OPS))
        assert result.merge_stats.content_changed is False

    def test_an_op_writing_a_marker_path_cannot_forge_a_change(self) -> None:
        """Nothing rejects such an op — the segment models are ``extra="ignore"``, so the
        schema validator lets it through. Excluding the keys from the comparison is what
        stops it from resetting the staleness clock."""
        marked = {**_HEALTHCARE_BODY, UNCHANGED_FLAG_KEY: True, UNCHANGED_SINCE_KEY: "2026-07-17"}
        ops = [PatchOp(op="set", path=f"/{UNCHANGED_SINCE_KEY}", value="2026-07-31")]
        result = merge_document_patch(marked, _patch(ops))
        assert result.merge_stats.content_changed is False


@pytest.mark.unit
class TestTheStalenessClock:
    """#1749's material half: a no-op republish used to reset ``gap_days`` to 1 forever."""

    def _prior(self, *, published: date, unchanged_since: str | None) -> PriorPublished:
        payload = dict(_HEALTHCARE_BODY)
        if unchanged_since is not None:
            payload[UNCHANGED_FLAG_KEY] = True
            payload[UNCHANGED_SINCE_KEY] = unchanged_since
        return PriorPublished(
            date=published,
            document_key="alt-politician-signals",
            payload=payload,
            content_date=prior_content_date(payload, published),
        )

    def _mode(self, prior: PriorPublished, run_date: date) -> str:
        return resolve_edit_mode(
            artifact_key=("segment", "alt-politician-signals"),
            run_date=run_date,
            prior_loader=_FakePriorLoader(prior),
            triage=None,
        )

    def test_frozen_chain_trips_the_hard_cap(self) -> None:
        """``alt-politician-signals``, reproduced. Five rows, one body, 07-17 → 07-24. On
        07-25 the gap from the CONTENT date is 8 > 7, so the documented cap forces ``full``."""
        prior = self._prior(published=date(2026, 7, 24), unchanged_since="2026-07-17")
        assert prior.content_date == date(2026, 7, 17)
        assert self._mode(prior, date(2026, 7, 25)) == "full"

    def test_the_unmarked_prior_is_the_defect_this_replaces(self) -> None:
        """Same row without the marker: ``gap_days`` is 1 and the cap stays silent. This is
        the pre-#1749 behaviour, and it is also what every already-published row still does —
        the markers are prospective, so no existing frozen chain trips the cap on day one."""
        prior = self._prior(published=date(2026, 7, 24), unchanged_since=None)
        assert prior.content_date == date(2026, 7, 24)
        assert self._mode(prior, date(2026, 7, 25)) == "edit"

    def test_a_frozen_chain_still_edits_before_the_cap(self) -> None:
        """The §5.3.1 boundary. Content identity alone must NOT force regeneration — the spec
        rejects that. Six days frozen still resolves to ``edit``; only elapsed days decide."""
        prior = self._prior(published=date(2026, 7, 22), unchanged_since="2026-07-17")
        assert self._mode(prior, date(2026, 7, 23)) == "edit"

    def test_malformed_marker_falls_back_to_the_publish_date(self) -> None:
        payload = {**_HEALTHCARE_BODY, UNCHANGED_SINCE_KEY: "not-a-date"}
        assert prior_content_date(payload, date(2026, 7, 24)) == date(2026, 7, 24)

    def test_absent_marker_falls_back_to_the_publish_date(self) -> None:
        assert prior_content_date(dict(_HEALTHCARE_BODY), date(2026, 7, 24)) == date(2026, 7, 24)


@pytest.mark.unit
class TestMarking:
    def test_mark_propagates_rather_than_resets(self) -> None:
        """Three consecutive frozen runs must all report the ORIGINAL freeze date. Resetting
        to ``prior.date`` each run is exactly the bug — it is how the clock stayed at 1."""
        chain_start = date(2026, 7, 17)
        prior = dict(_HEALTHCARE_BODY)
        prior_date = chain_start
        for run in (date(2026, 7, 21), date(2026, 7, 22), date(2026, 7, 23)):
            body = dict(prior)
            body["date"] = run.isoformat()
            mark_unchanged(body, prior=prior, prior_date=prior_date)
            assert body[UNCHANGED_SINCE_KEY] == chain_start.isoformat()
            prior, prior_date = body, run

    def test_clear_breaks_the_chain(self) -> None:
        """``apply_ops`` copies the prior body, so without this a marker set once would ride
        forward through every later real edit and permanently understate the content date."""
        body = {**_HEALTHCARE_BODY, UNCHANGED_FLAG_KEY: True, UNCHANGED_SINCE_KEY: "2026-07-17"}
        clear_unchanged(body)
        assert UNCHANGED_FLAG_KEY not in body
        assert UNCHANGED_SINCE_KEY not in body
