"""Counsel's statements of law are accurate (DIG-1479 task C1).

``digiquant.tool_refusals`` and two DIG-1251 comments stated 5 U.S.C.
13107(c)(1)(B) too broadly: they said obtaining or using a congressional
financial-disclosure report is unlawful "for any purpose other than
news-and-communications-media dissemination". The news-media carve-out in
(c)(1)(B) attaches to the **commercial-purpose** limb only. Using a 13107
report for a commercial purpose is unlawful unless you are news and
communications media disseminating to the general public; (c)(1)(A) is the
separate intent-to-sell limb. The outcome here is unchanged — digithings is a
commercial service and is refused either way — but the statement of law is
not, and the repo will be public in early 2027.

Also pinned by this file:

* the two CTO cross-references DIG-1479 requires. ``tool_refusals`` must say
  that the refusal covers the ``digifetch_congress_trades`` **tool surface**
  and that the LuxAlgo trackers path carries the same data class by business
  decision dated 2026-10-06 against Counsel's advice. ``trackers_ingest``
  must carry the same note next to its entry point.
* the trackers **data** licence, now classified (DIG-1464). Security read the
  upstream ``LICENSE`` on 2026-10-06: CC0-1.0, sha256
  ``a2010f343487d3f7618affe54f789f5487602331c0a8d03f49e9a7c547cf0499``. That
  resolves the licence question and **sharpens** the statute one: the licence is
  a copyright waiver by the affirmer and cannot waive 13107(c)(1)(B). Every
  user-visible trackers claim must therefore carry the licence *and* the two
  per-family limits, because a payload saying only "CC0" implies permission for
  congress-trades and short-volume alike, and neither has it.
* the refusals themselves: ``digifetch_congress_trades`` stays refused, no
  subset re-admits it, and ``live_search`` stays off for the alt-data segment.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

import digiquant.tool_refusals as tool_refusals  # noqa: E402
import digisearch.trackers_ingest as trackers_ingest  # noqa: E402
from digiquant.data.luxalgo.attribution import (  # noqa: E402
    LUXALGO_TRACKERS_DATA_CAVEATS,
    attribution_fields_for,
)
from digiquant.data.luxalgo.entitlements import TOOL_NOTES  # noqa: E402
from digiquant.data.luxalgo.models import (  # noqa: E402
    LUXALGO_TRACKERS_ALLOWED_DATASETS,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL_REFUSALS_PY = REPO_ROOT / "digiquant/src/digiquant/tool_refusals.py"
TRACKERS_INGEST_PY = REPO_ROOT / "digisearch/src/digisearch/trackers_ingest.py"
PHASE1_ALTDATA_PY = REPO_ROOT / "digiquant/src/digiquant/research/phases/phase1_altdata.py"
GLOOMBERB_AGENT_TOOLS_PY = REPO_ROOT / "digiquant/src/digiquant/data/gloomberb/agent_tools.py"

#: Every file that states a trackers data licence on a surface a model reads.
#: The old guard only looked at ``trackers_ingest.py``; PR #5203 fixed one file
#: and left four more asserting the same claim, which is why the check is
#: surface-wide.
DATA_LICENSE_CLAIM_FILES = (
    "digisearch/src/digisearch/trackers_ingest.py",
    "digisearch/src/digisearch/trackers_wave2_ingest.py",
    "digiquant/src/digiquant/data/luxalgo/attribution.py",
    "digiquant/src/digiquant/data/luxalgo/entitlements.py",
    "digiquant/src/digiquant/mcp_server.py",
    "digiquant/src/digiquant/orchestrator_tools.py",
)

#: The overstatement DIG-1479 removed. Any file still asserting it is wrong.
OVERSTATED_FRAGMENT = "for any purpose other than"

#: Clause anchors the corrected statements must cite so the law is traceable.
CLAUSES_CITED_ANYWHERE = ("13107", "13105")


def test_the_overstatement_is_gone_from_the_refusal_module() -> None:
    """(c)(1)(B)'s carve-out is commercial-purpose-scoped, not purpose-wide."""
    doc = inspect.getdoc(tool_refusals) or ""
    assert OVERSTATED_FRAGMENT not in doc
    assert "13107" in doc
    assert "commercial purpose" in doc or "commercial-purpose" in doc


def test_the_refusal_module_cites_the_clauses_it_relies_on() -> None:
    """A legal refusal must name the clauses so a reader can check them."""
    doc = inspect.getdoc(tool_refusals) or ""
    for clause in ("13107(a)", "(b)(2)(C)", "(c)(1)(B)", "(c)(2)", "13105(l)"):
        assert clause in doc, f"the refusal docstring must cite {clause}"


def test_the_overstatement_is_gone_from_the_phase1_altdata_comment() -> None:
    """The DIG-1251 containment comment must not restate the law wrongly."""
    source = PHASE1_ALTDATA_PY.read_text(encoding="utf-8")
    assert OVERSTATED_FRAGMENT not in source
    assert "live_search=False" in source
    assert "13107" in source


def test_the_overstatement_is_gone_from_the_gloomberb_comment() -> None:
    """Same overstatement, DIG-1251, in the Gloomberb tool subsets."""
    source = GLOOMBERB_AGENT_TOOLS_PY.read_text(encoding="utf-8")
    assert OVERSTATED_FRAGMENT not in source
    assert "digifetch_congress_trades" in source


def test_tool_refusals_carries_the_dig_1479_cross_reference() -> None:
    """CTO merge gate: the refusal is tool-surface-scoped, and says so.

    The LuxAlgo trackers path carries the same data class and is in service by
    business decision dated 2026-10-06 against Counsel's advice. Without this
    note the repo looks like it holds a legal opinion it does not hold.
    """
    doc = inspect.getdoc(tool_refusals) or ""
    assert "2026-10-06" in doc
    assert "Counsel" in doc
    assert "business" in doc.lower()
    assert "DIG-1472" in doc or "DIG-1479" in doc
    assert "tool surface" in doc or "tool-surface" in doc


def test_trackers_ingest_entry_point_carries_the_dig_1472_cross_reference() -> None:
    """Same note next to the ingest that still runs, per DIG-1479."""
    source = TRACKERS_INGEST_PY.read_text(encoding="utf-8")
    assert "DIG-1472" in source
    assert "Counsel" in source
    assert "business decision" in source or "business owner" in source


def test_trackers_ingest_states_the_classified_licence_and_its_limit() -> None:
    """DIG-1464 closed: the licence is CC0-1.0 *and* 13107(c) still bites.

    Reverses the old guard, which forbade any licence word while the question
    was open. The claim is verified now, so the file must say so — and the
    verification must not become the thing that misleads, which is why the
    statutory limit is asserted in the same breath.
    """
    doc = inspect.getdoc(trackers_ingest) or ""
    assert "CC0-1.0" in doc
    assert "a2010f343487d3f7618affe54f789f5487602331c0a8d03f49e9a7c547cf0499" in doc, (
        "the classification must cite the artefact it was read from"
    )
    assert "13107(c)(2)" in doc, "the copyright waiver cannot cure a statutory use limit"
    assert "DIG-1472" in doc and "not a clearance" in doc
    for stale in ("Do not assert a licence", "is unverified", "No licence is asserted"):
        assert stale not in doc, f"the withhold-pending-classification posture is stale: {stale}"


def test_no_user_visible_cc0_claim_is_left_unqualified() -> None:
    """The whole surface, not one file: a CC0 claim must carry its limits.

    This is the defect DIG-1464 was filed against — the licence boundary guard
    next to these strings covers indicator *source code* and the entitlement
    note states a data licence with no carve-out, so a reader concludes the
    position is covered. Every trackers-facing string that says CC0 must also
    name both per-family limits, or say why it does not apply.
    """
    unqualified: list[str] = []
    for rel in DATA_LICENSE_CLAIM_FILES:
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        if "CC0" not in text:
            continue
        if not any(marker in text for marker in ("13107", "FINRA", "short-volume")):
            unqualified.append(rel)
    assert not unqualified, (
        "these files claim CC0 for trackers data without a per-family limit: "
        + ", ".join(sorted(unqualified))
    )


def test_the_trackers_caveats_cover_exactly_the_two_limited_families() -> None:
    """Congress-trades is refused by statute; short-volume is unresolved.

    Both are in the dataset allowlist, so neither can be dropped by refusing to
    answer. The other four are public records with no open question.
    """
    assert set(LUXALGO_TRACKERS_DATA_CAVEATS) == {"congress-trades", "short-volume"}
    assert all(d in LUXALGO_TRACKERS_ALLOWED_DATASETS for d in LUXALGO_TRACKERS_DATA_CAVEATS)


def test_every_trackers_tool_note_carries_the_caveat() -> None:
    """Attribution is per-tool, so the per-family caveat must be unconditional."""
    for tool in (
        "luxalgo_trackers_datasets",
        "luxalgo_trackers_latest",
        "luxalgo_trackers_ticker",
    ):
        note = TOOL_NOTES[tool]
        assert "13107" in note, tool
        assert "FINRA" in note, tool
        fields = attribution_fields_for(tool)
        assert "13107" in fields["license_note"], tool
        assert "FINRA" in fields["license_note"], tool


def test_trackers_ingest_entry_point_is_still_exported() -> None:
    """The ingest stays in service; task A of DIG-1479 was cancelled."""
    assert "ingest_congress_trades" in trackers_ingest.__all__
    assert callable(trackers_ingest.ingest_congress_trades)


def test_the_refused_tool_is_still_refused() -> None:
    """No task in DIG-1479 touched a refusal. ``REFUSED_TOOLS`` is unchanged."""
    assert "digifetch_congress_trades" in tool_refusals.REFUSED_TOOLS
    assert tool_refusals.is_refused("digifetch_congress_trades") is True


def test_the_refused_tool_stays_out_of_every_subset() -> None:
    """DIG-1251: its absence from a subset is deliberate, not an oversight."""
    import digiquant.data.gloomberb.agent_tools as gloomberb

    subsets = [
        getattr(gloomberb, name)
        for name in dir(gloomberb)
        if name.endswith("TOOLS")
        and isinstance(getattr(gloomberb, name), (frozenset, set, tuple, list))
    ]
    assert subsets, "no gloomberb tool subsets found; the guard is vacuous"
    for subset in subsets:
        assert "digifetch_congress_trades" not in subset, subset


def test_the_luxalgo_trackers_tools_are_not_in_refused_tools() -> None:
    """The datasets are in service by business decision; the tools stay callable."""
    for name in (
        "luxalgo_trackers_datasets",
        "luxalgo_trackers_latest",
        "luxalgo_trackers_ticker",
    ):
        assert tool_refusals.is_refused(name) is False, name


@pytest.mark.parametrize("clause", CLAUSES_CITED_ANYWHERE)
def test_a_clause_anchor_is_findable_in_the_refusal_module(clause: str) -> None:
    """Sanity: the statute citation survived the rewrite."""
    assert clause in TOOL_REFUSALS_PY.read_text(encoding="utf-8")
