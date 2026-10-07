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

import ast
import inspect
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

import digiquant.tool_refusals as tool_refusals  # noqa: E402
import digisearch.trackers_ingest as trackers_ingest  # noqa: E402
from digiquant.data.luxalgo.attribution import (  # noqa: E402
    LUXALGO_TRACKERS_DATA_CAVEATS,
    LUXALGO_TRACKERS_DATA_LICENSE,
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

#: Every source file that states a trackers data licence on a surface a model
#: reads. The old guard only looked at ``trackers_ingest.py``; PR #5203 fixed one
#: file and left four more asserting the same claim, which is why the check is
#: surface-wide.
DATA_LICENSE_CLAIM_FILES = (
    "digiquant/src/digiquant/data/luxalgo/__init__.py",
    "digiquant/src/digiquant/data/luxalgo/agent_tools.py",
    "digiquant/src/digiquant/data/luxalgo/attribution.py",
    "digiquant/src/digiquant/data/luxalgo/client.py",
    "digiquant/src/digiquant/data/luxalgo/entitlements.py",
    "digiquant/src/digiquant/mcp_server.py",
    "digiquant/src/digiquant/orchestrator_tools.py",
    "digisearch/src/digisearch/trackers_ingest.py",
    "digisearch/src/digisearch/trackers_wave2_ingest.py",
)

#: Prose that states the same claim. Doc comments are read by the next agent to
#: edit the file, so an unqualified line here propagates.
DATA_LICENSE_CLAIM_DOCS = (
    "digiquant/AGENTS.md",
    "digisearch/ARCHITECTURE.md",
)

#: A CC0 claim is only *qualified* if it names **both** per-family limits. The
#: markers are deliberately the vocabulary a reader needs, not the caveat
#: function's own wording, so a file cannot pass by carrying the caveat
#: somewhere far away — the file-scoped guard this replaces did exactly that
#: and passed vacuously on ``trackers_wave2_ingest.py``, whose only "short
#: volume" token was a dataset id.
CONGRESS_TRADES_LIMIT_MARKERS = ("13107", "congress-trades", "congress trades", "congress_trades")
SHORT_VOLUME_LIMIT_MARKERS = ("FINRA", "short-volume", "short volume", "short_volume")

#: Doc comments and Markdown may satisfy the requirement by *pointing* at the
#: classifier instead of restating the law, so the rule stays readable in prose.
POINTER_MARKERS = (
    "DIG-1464",
    "DIG-1472",
    "caveat",
    "classified",
    "classification",
    "two families",
)

#: A family marker only counts as a *qualification* when a limit is asserted
#: near it. Without this, ``trackers_wave2_ingest.py`` passed on an incidental
#: "congress-trades spike" lineage note and a "FINRA" in a row-schema key —
#: both markers present, neither saying the licence fails to cover the family.
#:
#: Matched with word boundaries rather than substrings: bare ``in`` matching let
#: "unlimited", "clearly" and "delimitation" each read as an assertion of a
#: limit, which is the same vacuity one token in.
LIMIT_SIGNALS = re.compile(
    r"\b(?:clear\w*|waiv\w*|restrict\w*|unresolved|refus\w*|limit\w*|cannot|"
    r"does not|not a clearance|prohibited)\b",
    re.IGNORECASE,
)

#: Characters around a family marker in which a limit must be asserted.
LIMIT_WINDOW = 160

#: Backstop against a *runaway* claim unit, not against length. The real
#: longest unit in the surface list is a ~3.9k-char module docstring, so the
#: cap sits well above it: its job is to catch a parser that swallowed a whole
#: document (a Markdown-fence bug produced units of exactly that shape), not
#: to second-guess a long paragraph that states its limits correctly.
MAX_CLAIM_CHARS = 6000

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


#: Values that state the licence or one family's limit *by design*. Exempted
#: structurally — by the constant they are assigned to — so a new bare string
#: cannot buy its way past the guard the way a nearby marker used to.
EXEMPT_CLAIM_CONSTANTS = frozenset(
    {"LUXALGO_TRACKERS_DATA_LICENSE", "LUXALGO_TRACKERS_DATA_CAVEATS"}
)


def _exempted_string_nodes(tree: ast.Module) -> set[int]:
    """``id()`` of string nodes that are the classified constants themselves."""
    exempt: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(t, ast.Name) and t.id in EXEMPT_CLAIM_CONSTANTS for t in targets):
            continue
        value = node.value
        for child in ast.walk(value) if value is not None else ():
            if isinstance(child, ast.Constant) and isinstance(child.value, str):
                exempt.add(id(child))
    return exempt


def _cc0_claims(text: str, *, python: bool = True) -> list[tuple[str, str]]:
    """Every place ``text`` asserts the CC0 licence, as ``(kind, snippet)``.

    Claim-scoped on purpose. The guard this replaces asked "does this file
    mention CC0 *and* some marker anywhere", which a bare note 400 characters
    from a ``13107`` reference passes — the reader of the note sees the claim
    and none of the limits.

    A claim is one **thing a reader reads**: a string constant, a docstring, a
    contiguous ``#`` comment block, or a Markdown paragraph. Comment blocks and
    paragraphs are grouped because a reader reads the block; checking each line
    separately reports the explanation of the caveat machinery as violations of
    it.
    """
    claims: list[tuple[str, str]] = []
    lines = text.splitlines()
    in_fence = False
    if python:
        try:
            tree = ast.parse(text)
        except SyntaxError:  # pragma: no cover - a non-Python claim file
            tree = None
        if tree is not None:
            exempt = _exempted_string_nodes(tree)
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and "CC0" in node.value
                    and id(node) not in exempt
                ):
                    claims.append(("string", " ".join(node.value.split())))
    block: list[str] = []
    start = 0

    def flush() -> list[tuple[str, str]]:
        found = _block_claims(block, start, comment=python) if block else []
        block.clear()
        return found

    for lineno, raw in enumerate((*lines, ""), start=1):
        stripped = raw.strip()
        if not python:
            # Markdown: a paragraph is the run of non-blank lines a reader takes
            # in, so accumulate before flushing. Fenced blocks are structure,
            # not prose — a directory tree is not a claim, and accumulating one
            # ran the claim unit thousands of characters past any real
            # statement until the length cap caught it.
            if stripped.startswith("```"):
                in_fence = not in_fence
                claims.extend(flush())
                continue
            if in_fence:
                continue
            # A bullet starts its own claim. Treating a whole blank-line-free
            # list as one paragraph made a tool-inventory bullet hundreds of
            # characters long past any statement of the licence.
            if stripped.startswith(("- ", "* ", "+ ")) and not stripped.startswith("---"):
                claims.extend(flush())
                start = lineno
            if stripped:
                if not block:
                    start = lineno
                block.append(stripped)
            else:
                claims.extend(flush())
            continue
        if stripped.startswith("#") or (block and not stripped):
            if not block:
                start = lineno
            block.append(stripped.lstrip("# ").strip())
            continue
        claims.extend(flush())
    claims.extend(flush())
    return claims


def _block_claims(block: list[str], start: int, *, comment: bool) -> list[tuple[str, str]]:
    body = " ".join(part for part in block if part)
    if "CC0" not in body:
        return []
    kind = "comment" if comment else "para"
    # A block is a claim because a reader reads the whole thing. Without a cap
    # that lets a qualified opening line launder an arbitrarily long bare tail,
    # which is file-scoped co-occurrence rebuilt one unit up. Oversized blocks
    # are reported rather than passed.
    if len(body) > MAX_CLAIM_CHARS:
        return [(f"{kind}:{start}+oversized", body[:MAX_CLAIM_CHARS])]
    return [(f"{kind}:{start}", body)]


def _family_is_qualified(low: str, markers: tuple[str, ...]) -> bool:
    """True when some marker asserts a limit, not merely names the family."""
    for marker in markers:
        start = 0
        while (at := low.find(marker.lower(), start)) != -1:
            window = low[max(0, at - LIMIT_WINDOW) : at + len(marker) + LIMIT_WINDOW]
            if LIMIT_SIGNALS.search(window):
                return True
            start = at + 1
    return False


def _names_a_family(low: str) -> bool:
    """True when the snippet names either limited family at all."""
    return _family_is_qualified(low, CONGRESS_TRADES_LIMIT_MARKERS) or _family_is_qualified(
        low, SHORT_VOLUME_LIMIT_MARKERS
    )


def _missing_limits(snippet: str) -> list[str]:
    """Which per-family limits this snippet omits, or ``[]`` if it is qualified."""
    # Case-insensitive so prose that opens a sentence ("Two families need…")
    # is not reported for missing a pointer it does carry.
    low = snippet.lower()
    missing: list[str] = []
    if not _family_is_qualified(low, CONGRESS_TRADES_LIMIT_MARKERS):
        missing.append("congress-trades/13107")
    if not _family_is_qualified(low, SHORT_VOLUME_LIMIT_MARKERS):
        missing.append("short-volume/FINRA")
    # A pointer lets prose defer the law to the classifier instead of restating
    # it, but it is a *pointer*, not a licence: it must name a family and
    # assert a limit alongside the reference. Accepting a bare pointer word
    # ("caveat", "DIG-1464", "classified") as qualification on its own was
    # MAJOR in review — a claim saying "CC0 records cleared for any use; no
    # caveat applies" asserted the opposite of a limit and passed.
    if not missing:
        return []
    if any(marker.lower() in low for marker in POINTER_MARKERS) and LIMIT_SIGNALS.search(low):
        if _names_a_family(low):
            return []
    return missing


def test_no_cc0_claim_is_left_unqualified() -> None:
    """Every CC0 claim, on every surface, carries both per-family limits.

    This is the defect DIG-1464 was filed against — the licence boundary guard
    next to these strings covers indicator *source code* and the entitlement
    note states a data licence with no carve-out, so a reader concludes the
    position is covered. The first version of this test compared whole files,
    which reproduced the same failure one level up: it passed vacuously on
    ``trackers_wave2_ingest.py``, where "short-volume" occurs only as a
    dataset id, and it kept passing when a bare claim was injected into a file
    that mentioned the statute elsewhere.
    """
    unqualified: list[str] = []
    for rel in (*DATA_LICENSE_CLAIM_FILES, *DATA_LICENSE_CLAIM_DOCS):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        for kind, snippet in _cc0_claims(text, python=rel.endswith(".py")):
            if kind.endswith("+oversized"):
                unqualified.append(
                    f"{rel} [{kind}]: claim unit exceeds MAX_CLAIM_CHARS "
                    f"({MAX_CLAIM_CHARS}) — split it so each unit is checked"
                )
                continue
            missing = _missing_limits(snippet)
            if missing:
                unqualified.append(f"{rel} [{kind}] missing {', '.join(missing)}: {snippet[:90]}")
    assert not unqualified, "unqualified CC0 claims:\n  " + "\n  ".join(sorted(unqualified))


def test_the_license_constant_stays_the_bare_licence_id() -> None:
    """F2: the licence constant is exempt from the guard, so pin it directly.

    ``LUXALGO_TRACKERS_DATA_LICENSE`` is the one string the claim guard cannot
    see — it is exempt *by design*, because it **is** the classified licence.
    Exemption without a pin is a hole: the constant is interpolated into every
    trackers payload, so widening it to "CC0-1.0 public records, cleared for
    any purpose including congress-trades and short-volume" would restate the
    two limits this work exists to qualify, and every guard here would pass.
    The caveat half of the exemption is covered by the two tests below; this
    covers the licence half.
    """
    assert LUXALGO_TRACKERS_DATA_LICENSE == "CC0-1.0", (
        "the licence constant must stay the bare identifier; qualification "
        "belongs in LUXALGO_TRACKERS_DATA_CAVEATS, never here"
    )


def test_a_pointer_word_alone_cannot_qualify_a_cc0_claim() -> None:
    """F1: the pointer bypass must not swallow the check it stands in for.

    The claim-scoped rewrite left ``POINTER_MARKERS`` returning ``[]`` before
    any family marker or limit signal was examined, so the bare word
    "caveat" — or a bare ticket reference — marked a claim qualified. These
    are the reviewer's exploits: each states the **opposite** of a limit and
    must be reported as unqualified.
    """
    exploits = (
        # "clear" is a limit signal in this vocabulary; with no family named
        # and the word "caveat" present, the old rule returned [].
        "Trackers rows are CC0-1.0 public records cleared for any use; no caveat applies.",
        "Trackers rows are CC0-1.0; see DIG-1464.",
        "Trackers rows are CC0-1.0, classified by Security.",
        "CC0-1.0 caveat: cleared for any use.",
        "CC0-1.0 public records; no limitation applies.",
    )
    for exploit in exploits:
        assert _missing_limits(exploit) == [
            "congress-trades/13107",
            "short-volume/FINRA",
        ], f"the guard was bypassed by a pointer word: {exploit!r}"

    # A pointer is still allowed to carry prose that names a family and
    # asserts a limit — that is the pattern the real surfaces use.
    pointer_ok = (
        "Trackers rows are CC0-1.0 dumps, but the grant does not clear "
        "congress-trades (13107(c)) or short-volume (FINRA terms prohibit "
        "redistribution); see DIG-1464 for the classifier."
    )
    assert _missing_limits(pointer_ok) == []


def test_the_guard_would_catch_a_bare_claim() -> None:
    """Prove the guard is claim-scoped: it must fail on an injected claim.

    A guard that cannot fail is how DIG-1318 and DIG-1464 happened. This test
    runs the same check against a synthetic file so a future refactor cannot
    quietly weaken it back into co-occurrence.
    """
    bare = 'NOTE = "Trackers rows are CC0 public records."\n'
    qualified = (
        'NOTE = ("Trackers rows are CC0-1.0 dumps. The grant does not clear '
        'congress-trades (13107(c)) or short-volume (FINRA terms unresolved).")\n'
    )
    assert [m for _, s in _cc0_claims(bare) for m in _missing_limits(s)]
    assert not [m for _, s in _cc0_claims(qualified) for m in _missing_limits(s)]

    # The exact vacuity the file-scoped guard had: a module whose docstring
    # asserts CC0 while listing the dataset ids, including "short-volume".
    # The old guard passed this because the id is spelled in the file.
    wave2 = (
        '"""luxalgo market-trackers-data wave-2 CC0-1.0 dumps -> index (#4849)."""\n'
        'DATASETS = ("short-volume", "lda", "usaspending")\n'
    )
    assert [m for _, s in _cc0_claims(wave2) for m in _missing_limits(s)] == [
        "congress-trades/13107",
        "short-volume/FINRA",
    ]
    # One limit is not both, and naming a family is not asserting a limit:
    # "incl. short-volume" is a dataset id, not a statement about its terms.
    assert _missing_limits("CC0-1.0 dumps, incl. short-volume") == [
        "congress-trades/13107",
        "short-volume/FINRA",
    ]
    # Asserting one limit does not qualify the other family.
    assert _missing_limits("CC0-1.0 dumps. congress-trades is restricted by 13107(c)(1)(B).") == [
        "short-volume/FINRA"
    ]


def test_the_data_caveat_fails_closed_on_an_unknown_family() -> None:
    """A misspell must not clear the limit it was meant to carry.

    ``dataset`` is currently dead — no production caller passes it — so a
    future caller will get this wrong first time. Returning ``""`` for a name
    that is not in the map would hand back a clean note.
    """
    from digiquant.data.luxalgo.attribution import trackers_data_caveat

    assert "13107" in trackers_data_caveat("congress-trades")
    assert "FINRA" in trackers_data_caveat("short-volume")
    for misspell in ("congress_trades", "Congress-Trades", "", "unfunded-trades"):
        note = trackers_data_caveat(misspell)
        assert "13107" in note and "FINRA" in note, (
            f"{misspell!r} must not render a clean note: {note!r}"
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
