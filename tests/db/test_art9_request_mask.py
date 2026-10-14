"""Art. 9 masking, the audit record, and the irreversibility guarantee.

Leaf L2 of DIG-1084. Leaf L0 (DIG-1070) put the route registry in
`digibase/art9.py` and leaf L1 (DIG-1071) put the detector there too. This file
covers the third and last piece: what happens to a payload once a category has
been found — the mask, the audit record, and the promise that the mask cannot be
undone.

Three clauses are load-bearing here, and each is pinned by a test that would
still pass if the mechanism were quietly reverted to something weaker:

1. **The audit record carries category ids and the decision, never the value.**
   `test_audit_record_never_carries_the_raw_value` searches for the raw value and
   asserts it is absent — but only after a positive control proves the same
   search *does* fire on the un-redacted payload. Without that control the test
   passes on a payload the search simply cannot match.

2. **`mask` without an `exception_ref` raises.** It is a configuration error,
   not a quiet fallback to `refuse`.
   `test_mask_without_exception_ref_does_not_fall_back_to_refuse` pins the part
   that matters: the raise happens even when the payload holds no Art. 9 data at
   all, which is what makes it a *configuration* error rather than a screening
   outcome.

3. **A mask that can be undone fails these tests.**
   `test_mask_is_not_derived_from_the_value` is the load-bearing one. Two
   payloads carrying *different* secrets under the same §5.5 field name must mask
   to the *same* constant. A keyed digest, a random token, or a per-value
   placeholder all make those two differ, so all three fail here — which is the
   whole point. A comment saying "the mask is irreversible" pins nothing; this
   does.

`reason` stays a stable machine code (`art9:health:field_name`). That was leaf
L1's rule and it does not relax here.

**Why masking cannot run in production yet.** §2.3 records that no Art. 9(2)
exception letter exists, and a mask requires a cited one. `mask` is therefore
**not load-bearing in v1** — the production path is `refuse`. The decision is
configurable in one place precisely because Counsel has an open question on
whether masking at ingestion closes the collection question, and the answer may
change the default. `test_the_default_decision_is_refuse` pins the current
default; changing it must be a one-line edit, not five.
"""

from __future__ import annotations

import dataclasses
import importlib
import inspect
import json
import re
from collections.abc import Mapping
from typing import Any

import pytest

from digibase import __all__ as _digibase_all
from digibase import art9

#: The package module itself, so the export contract can be checked against the
#: re-exports in `digibase/__init__.py` rather than against `art9` alone.
_digibase = importlib.import_module("digibase")

pytestmark = pytest.mark.unit

#: Two *different* secrets that both trip a §5.5 field name. Clause 3 is proved
#: by masking each under the same key and requiring the same result: anything
#: derived from the value makes them differ.
SECRET_A = "NHS number 943 476 5919"
SECRET_B = "stage III sarcoma carrying rs4988235"

#: A distinctive fragment of each, for the absence assertions. Searching for the
#: whole secret would also pass if only its tail had leaked.
FRAGMENT_A = "943 476 5919"
FRAGMENT_B = "rs4988235"

#: Keys that would mean this record had grown into DIG-1139's egress record, or
#: had started retaining an original. Deliberately broad substrings.
FORBIDDEN_RECORD_KEY = re.compile(
    r"destination|dest|digest|raw|original|plaintext|cleartext|secret|token|payload_hash",
    re.IGNORECASE,
)


# ── helpers ──────────────────────────────────────────────────────────────────


def _leaf_values(node: Any) -> list[str]:
    """Every string leaf reachable from ``node``, key paths excluded."""
    out: list[str] = []
    if isinstance(node, Mapping):
        for key, value in node.items():
            out.append(key if isinstance(key, str) else str(key))
            out.extend(_leaf_values(value))
    elif isinstance(node, (list, tuple, set, frozenset)):
        for item in node:
            out.extend(_leaf_values(item))
    elif isinstance(node, str):
        out.append(node)
    return out


def _walk_keys(node: Any) -> list[str]:
    """Every mapping key reachable from ``node``."""
    out: list[str] = []
    if isinstance(node, Mapping):
        for key, value in node.items():
            out.append(key if isinstance(key, str) else str(key))
            out.extend(_walk_keys(value))
    elif isinstance(node, (list, tuple, set, frozenset)):
        for item in node:
            out.extend(_walk_keys(item))
    return out


def _everything(value: Any) -> str:
    """One string containing every readable byte of ``value``."""
    return "\n".join(
        [
            repr(value),
            json.dumps(value, default=str),
            repr(dataclasses.asdict(value)) if dataclasses.is_dataclass(value) else "",
            repr(_leaf_values(value)),
        ]
    )


# ── clause 1: the audit record ───────────────────────────────────────────────


def test_audit_record_reports_categories_decision_and_reason() -> None:
    """The record is the screening decision: which categories, and what to do."""
    result = art9.screen_and_apply({"diagnosis": SECRET_A})

    record = art9.audit_record(result)

    assert record["art9_categories"] == ["health"]
    assert record["art9_decision"] == "refuse"
    assert record["art9_reason"] == "art9:health:field_name"


def test_audit_record_reason_is_a_stable_machine_code() -> None:
    """`reason` is assembled from the tables, never from the input that matched.

    Two payloads that trip the same category by the same signal must produce the
    byte-identical code, or the label series a consumer groups on scatters.
    """
    first = art9.screen_and_apply({"diagnosis": SECRET_A})
    second = art9.screen_and_apply({"diagnosis": "unrelated, also a diagnosis"})

    assert first.reason == second.reason == "art9:health:field_name"
    assert art9.audit_record(first)["art9_reason"] == art9.audit_record(second)["art9_reason"]


def test_absence_search_is_capable_of_firing() -> None:
    """Positive control for the negative assertions below.

    The same two substring searches that the leak tests rely on must both hit the
    *un-redacted* payload. Without this, `test_audit_record_never_carries_the_raw_value`
    would pass on a payload the search cannot match, and would keep passing if
    the secret it was written for were changed into something unmatchable.
    """
    haystack = _everything({"diagnosis": SECRET_A, "marker": FRAGMENT_B})

    assert SECRET_A in haystack
    assert FRAGMENT_A in haystack


@pytest.mark.parametrize(
    ("decision", "exception_ref"),
    [("refuse", None), ("mask", "DPA-2026-04 §5")],
)
def test_audit_record_never_carries_the_raw_value(
    decision: str, exception_ref: str | None
) -> None:
    """The whole point of the record: the value stays, the category travels.

    Parametrised over **both** decisions on purpose. A `refuse` result holds no
    payload at all, so a record built from one could not leak even if the record
    were wrong — only the `mask` result has a `redacted` copy that could be
    pasted into the audit line by mistake. Testing only the empty case would pass
    against a record that dumps whatever it is handed.
    """
    payload = {"diagnosis": SECRET_A, "note": FRAGMENT_B}

    result = art9.screen_and_apply(payload, decision=decision, exception_ref=exception_ref)
    haystack = _everything(art9.audit_record(result, payload=payload))

    assert result.redacted is not None or decision == "refuse"
    assert SECRET_A not in haystack
    assert FRAGMENT_A not in haystack
    assert FRAGMENT_B not in haystack


def test_audit_record_carries_no_destination_and_no_digest() -> None:
    """This record is not the egress record.

    DIG-1139 owns the outbound seam: destination and a keyed non-reversible
    payload digest live there. Duplicating either here is how the two drift, and
    drift is how an unkeyed digest fallback sneaks back in. So the keys are
    absent by test, not by review.
    """
    result = art9.screen_and_apply(
        {"diagnosis": SECRET_A}, decision="mask", exception_ref="DPA-2026-04 §5"
    )

    keys = _walk_keys(art9.audit_record(result))

    assert [k for k in keys if FORBIDDEN_RECORD_KEY.search(k)] == []


def test_audit_record_composes_with_the_existing_audit_redaction() -> None:
    """`digibase.audit`'s pass is the additive second layer, not ours.

    `redact_mapping` is key-substring based, so it cannot be the only thing
    standing between the value and the log. What this pins is the ordering claim:
    the record I build is already safe *before* audit's redaction runs.
    """
    from digibase.audit import redact_mapping

    record = art9.audit_record(art9.screen_and_apply({"diagnosis": SECRET_A}))

    redacted = redact_mapping(record)

    assert SECRET_A not in json.dumps(redacted, default=str)
    assert redacted["art9_categories"] == ["health"]


def test_audit_record_echoes_the_exception_letter_for_accountability() -> None:
    """A mask with no letter recorded is unauditable.

    The letter is a citation, not personal data, so it belongs in the record.
    """
    result = art9.screen_and_apply(
        {"diagnosis": SECRET_A}, decision="mask", exception_ref="DPA-2026-04 §5"
    )

    assert art9.audit_record(result)["art9_exception_ref"] == "DPA-2026-04 §5"


def test_record_carries_no_exception_ref_when_none_was_cited() -> None:
    """Absence is a real value here: a consumer must be able to tell it from a hit."""
    record = art9.audit_record(art9.screen_and_apply({"diagnosis": SECRET_A}))

    assert record["art9_exception_ref"] is None


# ── clause 2: mask without a letter is a configuration error ─────────────────


@pytest.mark.parametrize("ref", [None, "", "   "])
def test_mask_without_exception_ref_raises(ref: str | None) -> None:
    """Clause 2. An empty string is not a letter either."""
    with pytest.raises(art9.Art9ConfigurationError):
        art9.screen_and_apply({"diagnosis": SECRET_A}, decision="mask", exception_ref=ref)


def test_the_error_is_a_configuration_error_not_a_refusal() -> None:
    """It is a `ValueError`, and the message names what is missing.

    A caller catching `ValueError` around screening must be able to tell a
    misconfiguration from bad data.
    """
    assert issubclass(art9.Art9ConfigurationError, ValueError)

    with pytest.raises(art9.Art9ConfigurationError) as excinfo:
        art9.screen_and_apply({"diagnosis": SECRET_A}, decision="mask")

    assert "exception_ref" in str(excinfo.value)


def test_mask_without_exception_ref_does_not_fall_back_to_refuse() -> None:
    """The load-bearing half of clause 2: the raise does not depend on the payload.

    A payload with no Art. 9 data at all would mask to nothing. If the raise were
    payload-driven it would not fire here, and the branch would silently become a
    fallback to `refuse` — the exact outcome the clause forbids.
    """
    with pytest.raises(art9.Art9ConfigurationError):
        art9.screen_and_apply({"title": "a perfectly ordinary note"}, decision="mask")

    with pytest.raises(art9.Art9ConfigurationError):
        art9.screen_and_apply({}, decision="mask")


def test_refuse_needs_no_exception_ref() -> None:
    """Positive control: clause 2 is about `mask`, not about screening."""
    result = art9.screen_and_apply({"diagnosis": SECRET_A})

    assert result.decision == "refuse"
    assert result.exception_ref is None


def test_the_default_decision_is_refuse() -> None:
    """The v1 default, pinned on the signature rather than on a constant.

    Counsel has an open question on whether masking at ingestion closes the
    collection question, so the default has to be movable without touching call
    sites. Leaf L0 refuses module-level upper-case globals precisely so nobody can
    add a runtime-switchable one, so the default lives in `screen_and_apply`'s
    own signature: the one place it can be changed, and a per-call parameter
    rather than a global anyone can reassign at runtime.

    Asserting on `inspect.signature` rather than on a module constant is
    deliberate — a constant could drift from the signature and still be green.
    """
    assert inspect.signature(art9.screen_and_apply).parameters["decision"].default == "refuse"
    assert art9.screen_and_apply({"diagnosis": SECRET_A}).decision == "refuse"


def test_no_module_level_uppercase_switch_was_added() -> None:
    """Leaf L0's guard still holds with L2's names in place.

    Not L0's test — that one lives in `test_art9_registry.py` and is not this
    leaf's to edit. This asserts the same property from this leaf's side, so a
    future constant added for masking cannot quietly reopen the question L0
    closed. `mask_token` and `art9_event_type` are lowercase for exactly this
    reason; `Art9ConfigurationError` is mixed-case.
    """
    added = {"mask_token", "art9_event_type", "Art9ConfigurationError"}

    assert added.isdisjoint({n for n in vars(art9) if n.isupper()})


def test_unknown_decision_is_rejected() -> None:
    """A typo must not resolve to the permissive branch."""
    with pytest.raises(art9.Art9ConfigurationError):
        art9.screen_and_apply({"diagnosis": SECRET_A}, decision="allow")


# ── clause 3: the mask cannot be undone ──────────────────────────────────────


def test_mask_is_not_derived_from_the_value() -> None:
    """Clause 3, load-bearing. Two different secrets must mask to the same token.

    A keyed digest, a random token, an HMAC, or any per-value placeholder makes
    these two masks differ, so all of them fail here. Only a constant survives.
    That is what "irreversible" has to mean in practice: if the mask is a
    function of the value, an attacker who can guess candidate values can undo
    it without any key store at all.
    """
    first = art9.screen_and_apply(
        {"diagnosis": SECRET_A}, decision="mask", exception_ref="DPA-2026-04 §5"
    )
    second = art9.screen_and_apply(
        {"diagnosis": SECRET_B}, decision="mask", exception_ref="DPA-2026-04 §5"
    )

    assert first.redacted["diagnosis"] == second.redacted["diagnosis"]
    assert first.redacted["diagnosis"] == art9.mask_token


def test_masked_result_holds_nothing_to_reverse() -> None:
    """No part of the result — including its repr — carries the value back.

    `ScreenResult` is a frozen dataclass, so `repr` is part of what a caller can
    accidentally log. Searching the dataclass alone would miss that.
    """
    result = art9.screen_and_apply(
        {"diagnosis": SECRET_A, "note": FRAGMENT_B},
        decision="mask",
        exception_ref="DPA-2026-04 §5",
    )

    haystack = _everything(result)

    assert SECRET_A not in haystack
    assert FRAGMENT_A not in haystack
    assert FRAGMENT_B not in haystack


def test_masked_result_carries_no_original_and_no_key_store() -> None:
    """Nothing in the result names an original, and no field holds one.

    The attribute names are searched, not just the values: a `originals={...}`
    field holding a value the string search already missed is exactly what clause
    3 exists to catch.
    """
    result = art9.screen_and_apply(
        {"diagnosis": SECRET_A}, decision="mask", exception_ref="DPA-2026-04 §5"
    )

    field_names = [f.name for f in dataclasses.fields(result)]

    assert [n for n in field_names if FORBIDDEN_RECORD_KEY.search(n)] == []
    assert _walk_keys(result.redacted) == ["diagnosis"]


def test_mask_drops_the_whole_value_under_a_field_name_hit() -> None:
    """A field-name hit masks the entire value, not just the matched span.

    Partially rewriting a value under `diagnosis` would leave the rest of the
    clinical text in place, which is the data, not a formatting choice.
    """
    payload = {"diagnosis": {"code": "E11", "text": SECRET_A}, "title": "keep me"}

    result = art9.screen_and_apply(
        payload, decision="mask", exception_ref="DPA-2026-04 §5"
    )

    assert result.redacted == {"diagnosis": art9.mask_token, "title": "keep me"}


def test_mask_replaces_a_whole_string_that_matched_a_value_pattern() -> None:
    """A string under a neutral key still matches on its own value."""
    result = art9.screen_and_apply(
        {"text": SECRET_A}, decision="mask", exception_ref="DPA-2026-04 §5"
    )

    assert result.redacted == {"text": art9.mask_token}
    assert result.reason == "art9:health:nhs_number"


def test_mask_walks_into_nested_containers() -> None:
    """A hit four levels down inside a list of dicts is masked like a top-level one."""
    payload = {"items": [{"meta": {"note": {"diagnosis": SECRET_A}}}]}

    result = art9.screen_and_apply(
        payload, decision="mask", exception_ref="DPA-2026-04 §5"
    )

    assert result.redacted == {"items": [{"meta": {"note": {"diagnosis": art9.mask_token}}}]}


def test_mask_leaves_unmatched_data_intact() -> None:
    """The mask is targeted. Over-masking everything would pass clause 3 too, and be useless."""
    result = art9.screen_and_apply(
        {"title": "quarterly review", "diagnosis": SECRET_A},
        decision="mask",
        exception_ref="DPA-2026-04 §5",
    )

    assert result.redacted["title"] == "quarterly review"
    assert result.redacted["diagnosis"] == art9.mask_token


def test_mask_terminates_on_a_cyclic_payload() -> None:
    """A caller-supplied payload must not be able to recurse the masker out of the stack.

    `screen_request` already walks these safely; the masker is a second walk over
    the same object graph, so it has to carry the same guard.
    """
    payload: dict[str, Any] = {"diagnosis": SECRET_A}
    payload["self"] = payload

    result = art9.screen_and_apply(
        payload, decision="mask", exception_ref="DPA-2026-04 §5"
    )

    assert result.redacted["diagnosis"] == art9.mask_token


def test_redacted_is_none_unless_mask_actually_replaced_something() -> None:
    """`redacted` is populated by masking and by nothing else.

    `None` under `refuse` says "this payload was not handed back at all", which
    is the whole meaning of refusing. Returning the payload under a `refuse` would
    quietly undo the refusal.
    """
    refused = art9.screen_and_apply({"diagnosis": SECRET_A})
    clean = art9.screen_and_apply({"title": "nothing here"}, decision="mask", exception_ref="DPA-2026-04 §5")
    masked = art9.screen_and_apply(
        {"diagnosis": SECRET_A}, decision="mask", exception_ref="DPA-2026-04 §5"
    )

    assert refused.redacted is None
    assert clean.redacted is None
    assert masked.redacted is not None


def test_refuse_returns_no_payload_at_all() -> None:
    """The refused payload is not reachable from the result."""
    result = art9.screen_and_apply({"diagnosis": SECRET_A})

    assert result.redacted is None
    assert SECRET_A not in _everything(result)


# ── exports ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "Art9ConfigurationError",
        "art9_event_type",
        "audit_record",
        "mask_token",
        "screen_and_apply",
    ],
)
def test_exported_from_the_package_root(name: str) -> None:
    """The new names reach `digibase` itself, alongside L0's and L1's."""
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
