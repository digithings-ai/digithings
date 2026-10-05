"""Unit tests for the zammad MCP disclosure policy (DIG-1063).

The contract under test is the one Security asked for: masked by default, and
an unmask override that cannot be set without a named human who accepted the
risk. Everything here runs on an explicit env mapping — no test may depend on
the ambient environment.
"""

from __future__ import annotations

import pytest

from scripts.zammad_mcp import privacy

pytestmark = pytest.mark.unit

MASKED = {privacy.DISCLOSURE_ENV: "masked"}
UNMASKED_NO_APPROVER = {privacy.DISCLOSURE_ENV: "unmasked"}
UNMASKED = {
    privacy.DISCLOSURE_ENV: "unmasked",
    privacy.APPROVER_ENV: "CTO (demo session, accepted 2026-10-05)",
}
EMPTY: dict[str, str] = {}


def test_default_is_masked():
    assert privacy.disclosure_mode(EMPTY) == privacy.MASKED
    assert privacy.is_masked(EMPTY) is True


@pytest.mark.parametrize(
    "env",
    [
        EMPTY,
        MASKED,
        {privacy.DISCLOSURE_ENV: ""},
        {privacy.DISCLOSURE_ENV: "MASkED"},
        {privacy.DISCLOSURE_ENV: "unmask"},
        {privacy.DISCLOSURE_ENV: "true"},
        {privacy.DISCLOSURE_ENV: "1"},
        {privacy.DISCLOSURE_ENV: "yes"},
        UNMASKED_NO_APPROVER,
        {privacy.DISCLOSURE_ENV: "unmasked", privacy.APPROVER_ENV: "  "},
    ],
)
def test_everything_that_is_not_a_signed_override_resolves_to_masked(env):
    # Fails closed: a deploy typo, a truthy-looking value, or an unmask with no
    # approver all stay masked.
    assert privacy.disclosure_mode(env) == privacy.MASKED


@pytest.mark.parametrize(
    "env",
    [EMPTY, MASKED, {privacy.DISCLOSURE_ENV: "nope"}, UNMASKED_NO_APPROVER],
)
def test_unmask_blocker_always_explains_itself(env):
    # A refused override must leave a reason behind, so the mask does not look
    # like a silent degradation.
    reason = privacy.unmask_blocker(env)
    assert reason
    assert privacy.DISCLOSURE_ENV in reason


def test_unmask_is_allowed_with_a_named_approver():
    assert privacy.unmask_blocker(UNMASKED) is None
    assert privacy.disclosure_mode(UNMASKED) == privacy.UNMASKED
    assert privacy.is_masked(UNMASKED) is False


def test_customer_label_carries_the_id_and_no_personal_data():
    for env in (EMPTY, MASKED, UNMASKED_NO_APPROVER):
        label = privacy.customer_label("jane.doe@example.test", 7, env=env)
        assert label == "customer #7"
        assert "jane" not in label
        assert "@" not in label
        assert "example.test" not in label


def test_customer_label_reads_the_id_from_an_expanded_payload():
    expanded = {"id": 7, "email": "jane.doe@example.test", "firstname": "Jane"}
    assert privacy.customer_label(expanded, env=EMPTY) == "customer #7"


def test_customer_label_digest_is_stable_and_carries_no_name():
    first = privacy.customer_label("jane.doe@example.test", env=EMPTY)
    second = privacy.customer_label("jane.doe@example.test", env=EMPTY)
    other = privacy.customer_label("max@example.test", env=EMPTY)
    assert first == second  # grouping across calls still works
    assert first != other
    assert "jane" not in first and "@" not in first
    assert len(first) == len(privacy.PSEUDONYM_PREFIX) + 8


def test_customer_label_is_empty_when_there_is_no_customer():
    assert privacy.customer_label("-", env=EMPTY) == ""
    assert privacy.customer_label(None, env=EMPTY) == ""
    assert privacy.customer_label({}, env=EMPTY) == ""
    assert privacy.customer_label("", env=EMPTY) == ""


def test_customer_label_treats_a_bare_number_as_an_id():
    # An aggregate ranking's `value` for a customer is the stringified id.
    assert privacy.customer_label("7", env=EMPTY) == "customer #7"


def test_customer_label_unmasked_restores_the_full_display():
    assert (
        privacy.customer_label("jane.doe@example.test", 7, env=UNMASKED)
        == "jane.doe@example.test (id 7)"
    )
    assert privacy.customer_label(None, 7, env=UNMASKED) == "(id 7)"
    assert privacy.customer_label("Ada Lovelace", None, env=UNMASKED) == "Ada Lovelace"


def test_organization_label_is_dropped_when_masked():
    assert privacy.organization_label("Example GmbH", env=EMPTY) == ""
    assert privacy.organization_label("Example GmbH", env=UNMASKED) == "Example GmbH"


def test_author_label_is_dropped_when_masked():
    # A customer-authored article carries the customer's own address here.
    assert privacy.author_label("jane.doe@example.test", env=EMPTY) == ""
    assert privacy.author_label("support@example.test", env=EMPTY) == ""
    assert privacy.author_label("jane.doe@example.test", env=UNMASKED) == "jane.doe@example.test"


def test_visible_articles_splits_internal_notes_only_when_masked():
    articles = [{"id": 1, "internal": True}, {"id": 2, "internal": False}]
    shown, hidden = privacy.visible_articles(articles, env=EMPTY)
    assert [a["id"] for a in shown] == [2]
    assert hidden == 1
    shown, hidden = privacy.visible_articles(articles, env=UNMASKED)
    assert [a["id"] for a in shown] == [1, 2]
    assert hidden == 0


def test_pseudonym_guard_recognises_its_own_output():
    assert privacy.is_pseudonym("customer #7") is True
    assert privacy.is_pseudonym("customer #unknown") is True
    assert privacy.is_pseudonym("jane.doe@example.test") is False
    assert privacy.is_pseudonym("") is False


def test_no_label_emits_a_bare_or_unknown_placeholder():
    """A masked label always carries an identifier: an id or an 8-char digest."""
    for value in (None, {}, "", "-", "-", "   "):
        label = privacy.customer_label(value, env=EMPTY)
        assert label == "", f"{value!r} should render no customer line, got {label!r}"
    for value, cid in ((None, 7), ("", 7), ("-", 9), ("jane.doe@example.test", None)):
        label = privacy.customer_label(value, cid, env=EMPTY)
        suffix = label.removeprefix(privacy.PSEUDONYM_PREFIX)
        assert label.startswith(privacy.PSEUDONYM_PREFIX)
        assert suffix, f"{value!r}/{cid!r} produced an empty suffix"
        assert suffix not in ("?", "unknown", ""), f"{value!r}/{cid!r} -> {label!r}"
        if not (suffix.isdigit() or (cid is None and len(suffix) == 8)):
            raise AssertionError(f"{value!r}/{cid!r} -> {label!r}")


def test_masked_notice_names_the_placeholder_and_forbids_guessing():
    assert privacy.PSEUDONYM_PREFIX in privacy.MASKED_NOTICE
    assert "Never guess or reconstruct a name" in privacy.MASKED_NOTICE


def test_mode_reads_the_process_environment_by_default(monkeypatch):
    monkeypatch.setenv(privacy.DISCLOSURE_ENV, "unmasked")
    monkeypatch.setenv(privacy.APPROVER_ENV, "CTO")
    assert privacy.disclosure_mode() == privacy.UNMASKED
    monkeypatch.delenv(privacy.APPROVER_ENV)
    assert privacy.disclosure_mode() == privacy.MASKED
    monkeypatch.delenv(privacy.DISCLOSURE_ENV)
    assert privacy.disclosure_mode() == privacy.MASKED


# --- one render, one decision -----------------------------------------------
# privacy re-reads the environment on each call, so a render that asks twice can
# in principle disagree with itself. These tests pin that the formatter threads a
# single resolved mode through one render.


def test_disclosure_mode_is_stable_across_calls_when_env_is_fixed():
    for _ in range(5):
        assert privacy.disclosure_mode(EMPTY) == privacy.MASKED
        assert privacy.is_masked(EMPTY) is True


def test_mode_argument_overrides_the_environment():
    """`env=` wins over the ambient environment, so tests can pin a mode."""
    assert privacy.disclosure_mode(UNMASKED) == privacy.UNMASKED
    assert privacy.disclosure_mode(MASKED) == privacy.MASKED
    assert privacy.disclosure_mode(EMPTY) == privacy.MASKED
