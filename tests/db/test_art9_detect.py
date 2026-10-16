"""Art. 9 detection: the eight special categories, screened by field name.

Leaf L1 of DIG-1071. Leaf L0 (DIG-1070) put the registry in `digibase/art9.py`;
this file covers the half that decides *whether a category is present in a
payload*. Nothing here masks, redacts or emits an audit event — that is leaf L2
(`tests/db/test_art9_request_mask.py`).

Two claims are pinned by this file, and both are the honest ones:

- **All eight categories have field-name coverage.** One test per category, each
  tripping its own §5.5 field names.
- **None has free-text coverage.** `screen_text` finds high-precision *identifier
  values* (NHS numbers, BRCA markers, rs-IDs) and nothing else. Counsel ruled
  prose detection of beliefs, opinions, sex life and union membership
  unavailable in v1 (§5.6): no regex detects those in prose with usable
  precision. `test_prose_beliefs_are_not_detected` is load-bearing — do not make
  it pass by loosening a pattern.

The load-bearing test for the matching *technique* is
`test_substring_rule_is_deliberately_broad`. Field names are matched as
lowercased substrings, the same rule `digibase.audit` already uses, so
`healthcheck_url` and `medical_billing_code` trip alongside `diagnosis`. That is
a known, accepted trade-off: leaf L13 (`tests/db/test_art9_false_positives.py`)
owns the false-positive battery and settles the policy. Narrowing the match here
to exact keys would delete the evidence L13 needs.

Why L1 does not mask: masking is leaf L2. `redacted` is `None` in this leaf on
every path, including `mask`.
"""

from __future__ import annotations

import dataclasses
import importlib
import re
import time
from collections.abc import Iterator
from typing import Any

import pytest

from digibase import __all__ as _digibase_all
from digibase import art9

_digibase = importlib.import_module("digibase")

pytestmark = pytest.mark.unit

#: §5.5 in table order. This tuple — not `ART9_CATEGORIES`, which is an unordered
#: frozenset — is the order `ScreenResult.categories` reports.
CATEGORY_ORDER = (
    "health",
    "genetic",
    "biometric",
    "racial_or_ethnic_origin",
    "political_opinions",
    "religious_or_philosophical_beliefs",
    "trade_union_membership",
    "sex_life_or_sexual_orientation",
)

#: §5.5 field names, per category.
FIELD_NAMES: dict[str, tuple[str, ...]] = {
    "health": ("diagnosis", "health_status", "medical"),
    "genetic": ("genotype", "genetic", "dna", "snp"),
    "biometric": ("biometric",),
    "racial_or_ethnic_origin": ("ethnicity", "race"),
    "political_opinions": ("political", "party_affiliation"),
    "religious_or_philosophical_beliefs": ("religion", "religious", "philosophical"),
    "trade_union_membership": ("union_membership", "trade_union"),
    "sex_life_or_sexual_orientation": ("sexual_orientation", "sex_life"),
}


# ── helpers ──────────────────────────────────────────────────────────────────


def _walk_values(payload: Any, seen: set[int] | None = None) -> list[Any]:
    """Every value reachable from ``payload``, depth-first, cycles guarded.

    Used by the `reason`-never-carries-the-value test, which has to check the
    reason against every string in the payload rather than the one it guessed.
    """
    seen = set() if seen is None else seen
    marker = id(payload)
    if marker in seen:
        return []
    seen.add(marker)

    if isinstance(payload, dict):
        # Values only, never keys: a category id in `reason` is not the matched
        # value, so `{"biometric": ...}` must not read as a leak of "biometric".
        children: list[Any] = []
        for value in payload.values():
            children.append(value)
            children.extend(_walk_values(value, seen))
        return children
    if isinstance(payload, (list, tuple)):
        children = []
        for item in payload:
            children.append(item)
            children.extend(_walk_values(item, seen))
        return children
    return []


# ── 1. one test per category ─────────────────────────────────────────────────


@pytest.mark.parametrize("category", CATEGORY_ORDER)
def test_field_names_trip_their_category(category: str) -> None:
    """Every §5.5 field name of one category screens to exactly that category."""
    names = FIELD_NAMES[category]
    assert names, f"{category} has no field names in §5.5"

    for name in names:
        result = art9.screen_request({name: "value"})

        assert result.categories == (category,), name
        assert result.decision == "refuse", name
        assert result.reason == f"art9:{category}:field_name", name


def test_all_eight_categories_are_covered() -> None:
    """No category matches nothing, and nothing matches outside the registry."""
    covered: set[str] = set()
    for category in CATEGORY_ORDER:
        for name in FIELD_NAMES[category]:
            covered.update(art9.screen_request({name: "value"}).categories)

    assert covered == set(art9.ART9_CATEGORIES)


def test_category_order_and_registry_are_the_same_eight_ids() -> None:
    """`ART9_CATEGORIES` is a frozenset; `category_order` is where the order lives.

    If a ninth id joins the frozenset and not the tuple, every result would quietly
    stop being able to report it. This test is the tripwire.
    """
    assert art9.category_order == CATEGORY_ORDER
    assert set(art9.category_order) == set(art9.ART9_CATEGORIES)


def test_the_published_field_names_are_section_5_5_verbatim() -> None:
    """`field_names` is the spec table, not a widened version of it.

    Leaf L13 changes this, and it should have to change this test with it.
    """
    assert {k: tuple(v) for k, v in art9.field_names.items()} == FIELD_NAMES


def test_every_value_pattern_maps_to_a_real_category() -> None:
    """A pattern keyed to a category outside the registry would be unreachable."""
    for category, signal in art9.value_patterns:
        assert category in art9.ART9_CATEGORIES, (category, signal)
        assert signal and signal == signal.lower(), (category, signal)


def test_all_eight_categories_reported_in_registry_order() -> None:
    """One payload holding all eight: `categories` is in §5.5 table order."""
    payload = {
        name: "value" for category in reversed(CATEGORY_ORDER) for name in FIELD_NAMES[category]
    }

    result = art9.screen_request(payload)

    assert result.categories == CATEGORY_ORDER
    assert result.reason == "art9:health:field_name"


def test_category_order_is_table_order_not_insertion_order() -> None:
    """`categories` order is canonical, so dict insertion order cannot leak."""
    payload = {
        "sex_life": "x",
        "trade_union": "x",
        "religion": "x",
        "political": "x",
        "race": "x",
        "biometric": "x",
        "dna": "x",
        "medical": "x",
    }

    assert art9.screen_request(payload).categories == CATEGORY_ORDER


def test_field_name_matching_is_case_insensitive() -> None:
    """`DiAgnOsIs` screens the same as `diagnosis` — same rule as `audit`."""
    assert art9.screen_request({"DiAgnOsIs": "value"}).categories == ("health",)
    assert art9.screen_request({"Patient_DIAGNOSIS_CODE": "x"}).categories == ("health",)


def test_non_string_keys_are_matched_as_text() -> None:
    """A non-string key is screened through `str()` rather than crashing."""
    result = art9.screen_request({1: "x", ("medical",): "y"})

    assert result.categories == ("health",)


# ── 2. identifier patterns ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "expected_reason"),
    [
        ("NHS number: 943 476 5919", "art9:health:nhs_number"),
        ("nhs no. 9434765919", "art9:health:nhs_number"),
        ("medical record number 4471902", "art9:health:record_number"),
        ("date of birth: 1974-03-11", "art9:health:date_of_birth"),
        ("DOB 11/03/1974", "art9:health:date_of_birth"),
        ("BRCA1 positive", "art9:genetic:brca_marker"),
        ("brca2 variant found", "art9:genetic:brca_marker"),
        ("see dbSNP rs4988235", "art9:genetic:rs_id"),
        ("chr17:43124095:G>T", "art9:genetic:genotype_call"),
        ("c.68_69delAG", "art9:genetic:genotype_call"),
        ("biometric template descriptor v2", "art9:biometric:biometric_template"),
        ("minutiae extracted from the scan", "art9:biometric:biometric_template"),
    ],
)
def test_identifier_patterns(value: str, expected_reason: str) -> None:
    """High-precision identifier values are found without any key hint."""
    result = art9.screen_text(value)

    assert result.categories, value
    assert result.reason == expected_reason, value
    assert result.decision == "refuse", value


@pytest.mark.parametrize(
    "value",
    [
        "2024-01-15T09:30:00Z",
        "order 1024 shipped on 2024-01-15",
        "call +44 20 7946 0958",
        "BRCA10 is a different gene",
        "see chapter 2 of the variable course outline",
        "template rendered",
        "the policy document",
    ],
)
def test_identifier_patterns_do_not_fire_on_ordinary_text(value: str) -> None:
    """Bare dates, phone numbers, lookalike words and bare `template` stay allowed.

    Each of these is a near miss for one pattern: an unlabelled ISO date, a bare
    phone number, `BRCA10`, the `rs` inside `course`, `template` without a
    biometric label, and `policy` for `political`.
    """
    result = art9.screen_text(value)

    assert result.categories == (), value
    assert result.decision == "allow", value


def test_identifier_value_under_a_neutral_key_is_screened() -> None:
    """A value is screened on its own merits; the key only has to be neutral."""
    result = art9.screen_request({"notes": "genotype call chr7:117559590:G>A"})

    assert result.categories == ("genetic",)
    assert result.reason == "art9:genetic:genotype_call"


def test_field_name_signal_wins_over_identifier_in_the_same_category() -> None:
    """A sensitive key outranks a regex hit, so `reason` is stable per payload."""
    result = art9.screen_request({"diagnosis": "NHS number: 943 476 5919"})

    assert result.categories == ("health",)
    assert result.reason == "art9:health:field_name"


def test_screen_text_finds_no_category_in_neutral_prose() -> None:
    """No key, no category: this is the `screen_text` contract."""
    result = art9.screen_text("quarterly revenue rose by four percent")

    assert result.categories == ()
    assert result.redacted is None
    assert result.decision == "allow"
    assert result.reason == "art9:no_match"


@pytest.mark.parametrize(
    ("pattern_name", "payload"),
    [
        ("_genotype_call_re", "c." + "9" * 40_000),
        ("_date_of_birth_re", "date of birth" + " " * 40_000),
        ("_nhs_number_re", "health number" + " " * 40_000),
        ("_record_number_re", "medical record number" + " " * 40_000),
    ],
)
def test_value_patterns_stay_linear_on_long_non_matching_input(
    pattern_name: str, payload: str
) -> None:
    """The identifier patterns must be linear, not quadratic, in input length.

    Each payload is a pattern's own label followed by filler that cannot complete
    a match, which is the worst case: `re` then retries every way of splitting
    the tail. A label whose optional separator was written `\s*[:#]?\s*` — two
    adjacent optional-ish quantifiers — made that split ambiguous and the
    attempt quadratic. Measured against that form: `_genotype_call_re` and
    `_date_of_birth_re` took 8.4 s and 5.4 s on 16 kB and passed 15 s on 32 kB,
    `_nhs_number_re` took 4.9 s on 32 kB, all roughly 4x per doubling.

    This is a denial-of-service test, not a speed test. These patterns run on
    caller-supplied request text and nothing upstream caps the length, so one
    long string is enough to pin a worker; a request body is a list, so it
    multiplies. The ceiling is set so a quadratic regression fails in seconds
    rather than hanging the suite, while the fixed patterns keep a wide margin.
    """
    pattern = getattr(art9, pattern_name)

    started = time.perf_counter()
    assert pattern.search(payload) is None  # worst case: no match
    elapsed = time.perf_counter() - started

    assert elapsed < 1.0, f"{pattern_name} took {elapsed:.3f}s on a 40k-char miss"


def test_grouped_separators_match_exactly_what_the_ambiguous_ones_did() -> None:
    """Fixing the backtracking must not change which strings match.

    The ReDoS fix is a rewrite, and a rewrite of a matching rule is a silent
    behaviour change unless something pins the language. These are the two forms
    side by side: the ambiguous one that shipped first, and the grouped one that
    replaced it. They must agree on every case here — the labelled forms that
    must match, and the near misses that must not.
    """
    ambiguous = {
        "_nhs_number_re": re.compile(
            r"\b(?:nhs|health)\s*(?:record\s*)?(?:number|no\.?|#)\s*[:#]?\s*\d[\d\s-]{7,}\d",
            re.IGNORECASE,
        ),
        "_record_number_re": re.compile(
            r"\b(?:medical|patient|health)\s*(?:record|file)\s*(?:number|no\.?|#)"
            r"\s*[:#]?\s*\d[\d\s-]{4,}\d",
            re.IGNORECASE,
        ),
        "_date_of_birth_re": re.compile(
            r"\b(?:date\s*of\s*birth|birth\s*date|d\.?o\.?b\.?)\s*[:#=]?\s*"
            r"(?:(?:19|20)\d{2}[-/.](?:0?[1-9]|1[0-2])[-/.](?:0?[1-9]|[12]\d|3[01])"
            r"|(?:0?[1-9]|[12]\d|3[01])[-/.](?:0?[1-9]|1[0-2])[-/.](?:19|20)\d{2})",
            re.IGNORECASE,
        ),
        "_genotype_call_re": re.compile(
            r"\b(?:(?:chr)?[0-9]{1,2}|x|y|mt)[:.][0-9]+[:. ]?[acgt]*[acgt]>[acgt]"
            r"|c\.[0-9]+_?[0-9]*(?:del|dup|ins|inv|[acgt]>)[a-z]*",
            re.IGNORECASE,
        ),
    }
    cases = [
        # labelled record numbers, in every separator style the old form allowed
        "NHS number: 943 476 5919",
        "NHS number 9434765919",
        "nhs no. 943 476 5919",
        "nhs #943 476 5919",
        "health record number 12345678",
        "NHS record number : 943 476 5919",
        "medical record number 4471902",
        "medical record no: 4471902",
        "patient file #4471-902",
        # dates of birth, labelled and bare
        "date of birth: 1984-03-11",
        "date of birth 11/03/1984",
        "date of birth =1984.3.1",
        "birth date: 1984-03-11",
        "d.o.b 1984-03-11",
        "dob: 11/03/1984",
        # genotype calls
        "chr17:43124095:G>T",
        "c.68_69delAG",
        "c.68delAG",
        "X:1234C>T",
        "mt.1A>G",
        # near misses that must stay misses
        "healthcheck_url",
        "the meeting is on 1984-03-11",
        "a phone number 943 476 5919",
        "policy number 12345678",
        "version 2.1.0",
        "c. is short for circa",
        "c.",
        "date of birth ",
        "NHS number ",
    ]

    for name, old in ambiguous.items():
        new = getattr(art9, name)
        for case in cases:
            assert bool(old.search(case)) == bool(new.search(case)), (
                f"{name} changed its verdict on {case!r}"
            )

    # Guard the guard: if every case missed, agreement would be vacuous.
    assert any(any(old.search(case) for case in cases) for old in ambiguous.values())


# ── 3. prose detection is not available in v1 ────────────────────────────────


@pytest.mark.parametrize(
    "prose",
    [
        "I am a member of the Labour party and I vote Labour every time.",
        "I am Catholic and my philosophical views are secular.",
        "I am a member of the transport workers union.",
        "I am gay and my sex life is my own business.",
        "I have type 2 diabetes and a heart condition.",
        "I am mixed race, Nigerian and English.",
        "I am a member of the chess club and the rota committee.",
        "I take a knee for the anthem every game.",
    ],
)
def test_prose_beliefs_are_not_detected(prose: str) -> None:
    """0/8 by free text, by design (§5.6). Loosening a pattern to pass breaks this.

    All eight categories are named in prose here and none trips. If a future leaf
    adds prose coverage it must first revise §5.6 with Counsel — not quietly widen
    a pattern here and let the eight-category claim in the docs drift.
    """
    result = art9.screen_text(prose)

    assert result.categories == (), prose
    assert result.decision == "allow", prose


# ── 4. the substring rule is deliberately broad ──────────────────────────────


@pytest.mark.parametrize(
    ("key", "expected_category"),
    [
        ("medical_billing_code", "health"),
        ("family_medical_leave", "health"),
        ("pre_diagnosis_note", "health"),
        ("dna_sequence_length", "genetic"),
        ("political_alerts", "political_opinions"),
        ("grace_period", "racial_or_ethnic_origin"),
        ("payroll_trade_union_deduction", "trade_union_membership"),
        ("philosophical", "religious_or_philosophical_beliefs"),
    ],
)
def test_substring_rule_is_deliberately_broad(key: str, expected_category: str) -> None:
    """The `audit.py` substring rule trips these, and L1 must not narrow it.

    `grace_period` (contains `race`), `family_medical_leave`, `undiagnosed`,
    `dna_sequence_length` and `payroll_trade_union_deduction` are ordinary-looking
    keys that trip anyway, and they are here on purpose. Leaf L13 owns the
    false-positive battery (`tests/db/test_art9_false_positives.py`): it decides
    which of these are narrowed, replaced or accepted. Narrowing here — the
    obvious way to make a test go green — would delete the evidence L13 needs.

    Note `healthcheck_url` does **not** trip: §5.5 lists `health_status`, not
    `health`, so a substring match on the shorter word would invent a category
    entry the spec does not have.
    """
    result = art9.screen_request({key: "value"})

    assert result.categories == (expected_category,), key
    assert result.decision == "refuse", key


@pytest.mark.parametrize(
    "key",
    ["healthcheck_url", "trades", "membership_tier", "religiosity", "undiagnosed"],
)
def test_keys_whose_substrings_are_not_section_5_5_names_stay_allowed(key: str) -> None:
    """The rule is substring-over-the-§5.5-list, not substring-over-the-English.

    Each of these is one character away from a needle — `healthcheck_url` from
    `health_status`, `trades` from `trade_union`, `undiagnosed` from `diagnosis`,
    `religiosity` from `religion`, `membership_tier` from `union_membership` —
    and none contains a §5.5 name, so none is an Art. 9 category. Adding
    `health`, `trade`, `diagnos`, `religio` or `membership` as needles would fix
    those five and break this test, which is why the list is §5.5 verbatim.
    """
    result = art9.screen_request({key: "value"})

    assert result.categories == (), key
    assert result.decision == "allow", key


def test_a_key_may_trip_more_than_one_category() -> None:
    """`medical_religion` is both health and belief; both are reported."""
    result = art9.screen_request({"medical_religion": "value"})

    assert result.categories == ("health", "religious_or_philosophical_beliefs")
    assert result.reason == "art9:health:field_name"


# ── 5. reason is a code, never a value ───────────────────────────────────────


@pytest.mark.parametrize(
    "payload",
    [
        {"diagnosis": "stage IV metastatic carcinoma"},
        {"notes": "NHS number: 943 476 5919"},
        {"dna": "rs4988235"},
        {"religion": "Sunni Muslim"},
        {"nested": [{"biometric": "minutiae template"}]},
    ],
)
def test_reason_never_carries_the_matched_value(payload: dict[str, Any]) -> None:
    """`reason` is a stable code: the matched value must not be in it.

    A reason string ends up in logs, metrics labels and error envelopes. If it
    ever carried the value it matched, the audit trail would itself become a copy
    of the Art. 9 row it refused.
    """
    values = [v for v in _walk_values(payload) if isinstance(v, str) and v.strip()]
    assert values, "a payload with no string value proves nothing"

    result = art9.screen_request(payload)

    assert result.reason.startswith("art9:")
    assert result.reason.count(":") == 2, result.reason
    for value in values:
        assert value not in result.reason, result.reason


def test_reason_codes_are_stable_across_repeated_calls() -> None:
    """Same payload, same reason — no set or dict iteration order leaking out."""
    payload = {"religion": "x", "medical": "y", "dna": "z"}

    reasons = {art9.screen_request(payload).reason for _ in range(50)}

    assert reasons == {"art9:health:field_name"}


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        # Two value patterns in one category. `min` over a set with a tie falls
        # back to set iteration order, which is hash-seed randomised, so these
        # two emitted different codes per process: art9:genetic:genotype_call vs
        # art9:genetic:brca_marker on one seed, the other way round on the next.
        # `reason` keys a metric label, so that scatters the series.
        pytest.param(
            {"note": "BRCA1 positive, c.68_69delAG confirmed"},
            "art9:genetic:brca_marker",
            id="two-genetic-patterns",
        ),
        pytest.param(
            {"note": "NHS number: 943 476 5919, date of birth 1974-03-11"},
            "art9:health:date_of_birth",
            id="two-health-patterns",
        ),
    ],
)
def test_reason_tie_breaks_deterministically(payload: dict[str, Any], expected: str) -> None:
    """The winner among tied hits must not depend on the process hash seed.

    Run under several ``PYTHONHASHSEED`` values to be meaningful; the assertion
    inside the test pins the tie-break rule, this pins which signal it picks.
    """
    assert art9.screen_request(payload).reason == expected


# ── 6. decisions ─────────────────────────────────────────────────────────────


def test_decision_defaults_to_refuse_on_any_hit() -> None:
    """Counsel §2.4: `refuse` is the default; nothing flips it at import time."""
    result = art9.screen_request({"medical": "x"})

    assert result.decision == "refuse"
    assert result.exception_ref is None


def test_clean_payload_is_allowed() -> None:
    """No category present is an allow, not a mask."""
    result = art9.screen_request({"order_id": "A-1", "total": 12, "paid": True, "note": None})

    assert result.categories == ()
    assert result.decision == "allow"
    assert result.reason == "art9:no_match"
    assert result.exception_ref is None


def test_mask_is_reachable_only_with_an_exception_ref() -> None:
    """`mask` without a letter is unrepresentable here, so it cannot be returned."""
    assert art9.screen_request({"medical": "x"}).decision == "refuse"
    masked = art9.screen_request({"medical": "x"}, exception_ref="dpa-2026-014:art9-2b")
    assert masked.decision == "mask"


def test_exception_ref_is_echoed_on_every_decision() -> None:
    """The caller can always see which letter it relied on."""
    ref = "dpa-2026-014:art9-2b"

    for payload in ({"medical": "x"}, {"order_id": "A-1"}):
        assert art9.screen_request(payload, exception_ref=ref).exception_ref == ref
    assert art9.screen_text("rs4988235", exception_ref=ref).exception_ref == ref


def test_empty_exception_ref_is_treated_as_absent() -> None:
    """An empty ref names no Art. 9(2) letter, so it does not unlock `mask`."""
    assert art9.screen_request({"medical": "x"}, exception_ref="").decision == "refuse"


def test_redacted_is_none_in_this_leaf() -> None:
    """Masking is leaf L2: `redacted` stays None here even on `mask`.

    Pinned so that a future leaf which starts populating `redacted` has to update
    this test, rather than have the mask contract change underneath L2's
    irreversibility work.
    """
    assert art9.screen_request({"medical": "x"}).redacted is None
    masked = art9.screen_request({"medical": "x"}, exception_ref="dpa-2026-014:art9-2b")
    assert masked.redacted is None


# ── 7. screen_request traversal ──────────────────────────────────────────────


def test_screen_request_walks_nested_dicts() -> None:
    """Deep nesting is walked to the leaf."""
    payload = {"a": {"b": {"c": {"d": {"medical": "x"}}}}}

    assert art9.screen_request(payload).categories == ("health",)


def test_screen_request_walks_lists_of_dicts_and_nested_lists() -> None:
    """Lists are containers, not scalars: every item is screened."""
    payload = {"orders": [{"lines": [{"item": "pen"}]}, {"lines": [{"item": {"dna": "x"}}]}]}

    assert art9.screen_request(payload).categories == ("genetic",)


def test_screen_request_screens_the_top_level_payload_itself() -> None:
    """A bare mapping is screened, not just its values."""
    assert art9.screen_request({"race": "x"}).categories == ("racial_or_ethnic_origin",)


def test_screen_request_delegates_a_bare_string_to_screen_text() -> None:
    """A string root is text, so it gets identifier screening, not key screening."""
    assert art9.screen_request("NHS number: 943 476 5919").categories == ("health",)
    assert art9.screen_request("nothing special here").decision == "allow"


@pytest.mark.parametrize("payload", [12, 3.5, True, None, b"medical"])
def test_screen_request_accepts_non_container_scalars(payload: Any) -> None:
    """Numbers, booleans, `None` and bytes are not walkable and are allowed."""
    result = art9.screen_request(payload)

    assert result.categories == ()
    assert result.decision == "allow"


def test_screen_request_survives_a_self_referential_payload() -> None:
    """A cycle must terminate, not recurse until the stack gives out."""
    payload: dict[str, Any] = {"id": "A-1"}
    payload["self"] = payload
    payload["rows"] = [payload]

    assert art9.screen_request(payload).decision == "allow"


def test_screen_request_survives_shared_subtrees() -> None:
    """The same object reached twice is screened once, not re-walked."""
    shared = {"medical": "x"}

    assert art9.screen_request({"a": shared, "b": shared}).categories == ("health",)


def test_screen_request_screens_an_ephemeral_stream_to_the_end() -> None:
    """A streamed payload must not fail open when its objects are freed.

    The cycle guard keys on ``id(node)``. A generator releases each dict as the
    walk rebinds, CPython recycles the address, and the next dict can collide on
    an id the set still holds — skipping it unscanned. With the hit last, that
    returned ``allow`` for a payload holding ``medical``. The guard must keep the
    objects it has seen alive so an id always means the object it was taken from.
    """
    filler = 59  # enough distinct dicts to force at least one address reuse

    def rows() -> Iterator[dict[str, Any]]:
        for i in range(filler):
            yield {f"filler_{i}": "v" * 40}
        yield {"medical": "x"}

    result = art9.screen_request(rows())

    assert result.categories == ("health",)
    assert result.decision == "refuse"
    assert result.reason == "art9:health:field_name"


# ── 8. the ScreenResult contract ─────────────────────────────────────────────


def test_screen_result_is_a_frozen_dataclass() -> None:
    """Frozen, and the field order is the published one."""
    result = art9.screen_request({"medical": "x"})

    assert dataclasses.is_dataclass(result)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.decision = "allow"  # type: ignore[misc]

    assert [f.name for f in dataclasses.fields(result)] == [
        "categories",
        "redacted",
        "decision",
        "reason",
        "exception_ref",
    ]


def test_categories_is_an_ordered_tuple_of_strings() -> None:
    """A tuple, not a set: callers index and print it."""
    result = art9.screen_request({"dna": "x", "medical": "y"})

    assert result.categories == ("health", "genetic")
    assert all(isinstance(category, str) for category in result.categories)


# ── 9. exports ───────────────────────────────────────────────────────────────


NEW_PUBLIC_NAMES = [
    "ScreenResult",
    "screen_request",
    "screen_text",
    "category_order",
    "field_names",
    "value_patterns",
    "no_match_reason",
]


@pytest.mark.parametrize("name", NEW_PUBLIC_NAMES)
def test_exported_from_art9(name: str) -> None:
    assert name in art9.__all__
    assert hasattr(art9, name)


@pytest.mark.parametrize("name", NEW_PUBLIC_NAMES)
def test_exported_from_the_package_root(name: str) -> None:
    """The new names reach `digibase` itself, alongside L0's registry."""
    assert name in _digibase.__all__
    assert name in _digibase_all
    assert getattr(_digibase, name) is getattr(art9, name)


def test_package_exports_are_sorted_and_unique() -> None:
    """`digibase.__all__` stays the sorted, duplicate-free list L0 left behind.

    Sorted in ruff's `__all__` style — constants, then classes, then functions —
    not plain ASCII order, which would interleave them.
    """

    def export_key(name: str) -> tuple[int, str]:
        if name.isupper():
            return (0, name)
        if name[:1].isupper():
            return (1, name)
        return (2, name)

    assert _digibase.__all__ == sorted(set(_digibase.__all__), key=export_key)
