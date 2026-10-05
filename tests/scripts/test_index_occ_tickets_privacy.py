"""Unit tests for the ``occ_tickets`` disclosure policy (DIG-1210).

The defect this pins: the OCC tenant fans out over the whole ``occ_tickets``
index on every question, behind an anonymous ungated embed, and the index was
built with full customer emails, resolved customer display names, article
``from`` addresses and every ``[internal]`` staff note intact. The prompt told
the model that was expected.

What is asserted here is the contract, not the shape of the code: masked by
default, one switch shared with the zammad MCP tools, no customer identity or
internal note in the indexed text or metadata, and the ``#4944`` demo rendering
recoverable only through a switch that names the human accepting the risk.

Every test passes an explicit ``env`` mapping. No test may depend on the
ambient environment — a developer with ``ZAMMAD_MCP_CUSTOMER_DISCLOSURE``
exported must still see these pass.
"""

from __future__ import annotations

import re

import pytest

from scripts.index_occ_tickets import build_ticket_chunks
from scripts.zammad_mcp import privacy

pytestmark = pytest.mark.unit

MASKED = {privacy.DISCLOSURE_ENV: "masked"}
EMPTY: dict[str, str] = {}
UNMASKED_NO_APPROVER = {privacy.DISCLOSURE_ENV: "unmasked"}
UNMASKED = {
    privacy.DISCLOSURE_ENV: "unmasked",
    privacy.APPROVER_ENV: "CTO (demo session, accepted 2026-10-05)",
}

#: Real Zammad field names, one per shape that leaks. Nothing in this file may
#: contain a real address from the committed snapshot — fixtures are `.test`
#: and `.invalid`, per the synthetic-fixture rule.
CUSTOMER_EMAIL = "jane.doe@customer.test"
STAFF_EMAIL = "agent@sitaas.invalid"
ARTICLE_FROM_EMAIL = "reply.from@customer.test"

EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")

TICKET = {
    "id": 231,
    "number": "28312",
    "title": "Rechnung fehlt",
    "customer": CUSTOMER_EMAIL,
    "customer_id": 7,
    "organization": "Müller GmbH",
    "owner": STAFF_EMAIL,
    "state": "offen",
    "group": "Vertrieb",
    "priority": "2 normal",
    "created_at": "2026-10-01T09:00:00Z",
    "updated_at": "2026-10-01T10:00:00Z",
}

CUSTOM_ARTICLE = {
    "id": 401,
    "type": "email",
    "sender": "Customer",
    "from": ARTICLE_FROM_EMAIL,
    "subject": "Rechnung fehlt",
    "body": "<p>Meine Rechnung fehlt seit drei Wochen.</p>",
    "created_at": "2026-10-01T09:12:00Z",
    "internal": False,
}

INTERNAL_ARTICLE = {
    "id": 402,
    "type": "note",
    "sender": "Agent",
    "from": STAFF_EMAIL,
    "subject": "",
    "body": "<p>INTERNAL: ask billing whether the SEPA mandate lapsed.</p>",
    "created_at": "2026-10-01T10:00:00Z",
    "internal": True,
}


def _articles(*extra: dict) -> list[dict]:
    return [CUSTOM_ARTICLE, *extra]


def _texts(chunks) -> str:
    return "\n".join(chunk.content for chunk in chunks)


def _all_metadata(chunks) -> str:
    return "\n".join(repr(chunk.metadata) for chunk in chunks)


# --- the default path: masked -------------------------------------------------


def test_default_masks_customer_email():
    chunks = build_ticket_chunks(TICKET, _articles(), env=EMPTY)
    assert chunks
    blob = _texts(chunks) + _all_metadata(chunks)
    assert CUSTOMER_EMAIL not in blob


def test_default_withholds_resolved_display_name():
    chunks = build_ticket_chunks(TICKET, _articles(), customer_name="Jane Doe", env=EMPTY)
    blob = _texts(chunks) + _all_metadata(chunks)
    assert "Jane Doe" not in blob


def test_default_drops_organization():
    chunks = build_ticket_chunks(TICKET, _articles(), env=EMPTY)
    assert all("Müller GmbH" not in repr(c.metadata) for c in chunks)


def test_default_drops_the_from_line():
    """A customer-authored article carries their own address in ``from``.

    Masking only the ``Customer:`` header would be cosmetic while this line
    still renders the address on the same screen.
    """
    chunks = build_ticket_chunks(TICKET, _articles(), env=EMPTY)
    assert "From:" not in _texts(chunks)
    assert ARTICLE_FROM_EMAIL not in _texts(chunks)


def test_default_excludes_internal_articles_entirely():
    chunks = build_ticket_chunks(TICKET, _articles(INTERNAL_ARTICLE), env=EMPTY)
    assert len(chunks) == 1
    blob = _texts(chunks)
    assert "SEPA mandate" not in blob
    assert "INTERNAL" not in blob
    assert "[internal]" not in blob


def test_default_states_how_many_internal_notes_were_withheld():
    """The model must read the gap as withheld, not as missing data."""
    chunks = build_ticket_chunks(TICKET, _articles(INTERNAL_ARTICLE), env=EMPTY)
    assert "1 internal note(s) withheld" in _texts(chunks)


def test_default_withholds_every_article_when_all_are_internal():
    chunks = build_ticket_chunks(
        TICKET, [dict(INTERNAL_ARTICLE)], customer_name="Jane Doe", env=EMPTY
    )
    assert chunks == []


def test_explicit_masked_matches_the_default():
    """``masked`` and "unset" must be the same corpus, not two policies."""
    implicit = build_ticket_chunks(TICKET, _articles(INTERNAL_ARTICLE), env=EMPTY)
    explicit = build_ticket_chunks(TICKET, _articles(INTERNAL_ARTICLE), env=MASKED)
    assert [c.content for c in implicit] == [c.content for c in explicit]
    assert [c.metadata for c in implicit] == [c.metadata for c in explicit]


# --- one switch, shared with the MCP tools ------------------------------------


def test_unmask_without_an_approver_stays_masked():
    """The refusal is the whole point: a bare ``unmasked`` cannot be set by accident."""
    chunks = build_ticket_chunks(TICKET, _articles(INTERNAL_ARTICLE), env=UNMASKED_NO_APPROVER)
    blob = _texts(chunks) + _all_metadata(chunks)
    assert CUSTOMER_EMAIL not in blob
    assert len(chunks) == 1


@pytest.mark.parametrize(
    "env",
    [
        {privacy.DISCLOSURE_ENV: "UNMASKED"},
        {privacy.DISCLOSURE_ENV: "unmasked", privacy.APPROVER_ENV: "   "},
        {privacy.DISCLOSURE_ENV: "yes"},
        {privacy.DISCLOSURE_ENV: "1"},
        {privacy.DISCLOSURE_ENV: "unmasked", privacy.APPROVER_ENV: ""},
    ],
)
def test_near_miss_values_all_stay_masked(env):
    chunks = build_ticket_chunks(TICKET, _articles(), env=env)
    blob = _texts(chunks) + _all_metadata(chunks)
    assert CUSTOMER_EMAIL not in blob
    assert ARTICLE_FROM_EMAIL not in blob


def test_the_switch_is_the_one_the_mcp_tools_read():
    """AC: one switch, one accepted-risk owner — not a second one for the index.

    If DIG-1063's policy module ever grows a second knob, this fails and the
    index silently keeps its own opinion.
    """
    assert privacy.DISCLOSURE_ENV == "ZAMMAD_MCP_CUSTOMER_DISCLOSURE"
    assert privacy.APPROVER_ENV == "ZAMMAD_MCP_UNMASK_APPROVER"


# --- the demo override restores #4944 exactly ----------------------------------


def test_named_approver_restores_the_demo_rendering():
    chunks = build_ticket_chunks(
        TICKET,
        _articles(INTERNAL_ARTICLE),
        customer_name="Jane Doe",
        env=UNMASKED,
    )
    blob = _texts(chunks) + _all_metadata(chunks)
    assert len(chunks) == 2
    assert CUSTOMER_EMAIL in blob
    assert "Jane Doe" in blob
    assert "Müller GmbH" in blob
    assert "INTERNAL" in blob
    assert "[internal]" in _texts(chunks)
    assert f"From: {ARTICLE_FROM_EMAIL}" in _texts(chunks)
    assert "internal note(s) withheld" not in _texts(chunks)


# --- stability, so retrieval keeps working -------------------------------------


def test_pseudonym_is_stable_across_calls():
    """A pseudonym that changed per run would break grouping and the drill-down."""
    first = build_ticket_chunks(TICKET, _articles(), env=MASKED)
    second = build_ticket_chunks(TICKET, _articles(), env=MASKED)
    assert first[0].metadata["customer"] == second[0].metadata["customer"]
    assert first[0].metadata["customer"] == privacy.PSEUDONYM_PREFIX + "7"


def test_customer_id_survives_masking():
    """It is the drill-down key, not personal data — the same call DIG-1063 makes."""
    chunks = build_ticket_chunks(TICKET, _articles(), env=MASKED)
    assert chunks[0].metadata["customer_id"] == 7


def test_article_index_is_the_position_in_the_original_thread():
    """Masking must not renumber a thread.

    ``article_index`` feeds the chunk id, so renumbering would orphan every id
    already written to Chroma and silently duplicate the corpus on re-index.
    """
    masked = build_ticket_chunks(TICKET, _articles(INTERNAL_ARTICLE), env=MASKED)
    assert [c.metadata["article_index"] for c in masked] == [1]
    unmasked = build_ticket_chunks(TICKET, _articles(INTERNAL_ARTICLE), env=UNMASKED)
    assert [c.metadata["article_index"] for c in unmasked] == [1, 2]
    assert unmasked[1].id == "zammad-231-2"


def test_identical_internal_and_public_articles_do_not_confuse_the_filter():
    """Two equal dicts where only one is internal must not both be withheld."""
    twin = {**INTERNAL_ARTICLE, "internal": False}
    chunks = build_ticket_chunks(TICKET, _articles(twin), env=MASKED)
    assert len(chunks) == 2


def test_sender_role_is_kept():
    """``sender`` is Zammad's role (``Customer``/``Agent``), not an address.

    Keeping it is what lets a reader follow a thread without an identity.
    """
    chunks = build_ticket_chunks(TICKET, _articles(), env=MASKED)
    assert chunks[0].metadata["sender"] == "Customer"
    assert "Article 1 (Customer/email)" in chunks[0].content


def test_owner_is_kept_because_an_owner_is_staff():
    chunks = build_ticket_chunks(TICKET, _articles(), env=MASKED)
    assert chunks[0].metadata["owner"] == STAFF_EMAIL


def test_empty_body_articles_are_still_skipped():
    empty = {**CUSTOM_ARTICLE, "id": 999, "body": "<p></p>"}
    assert build_ticket_chunks(TICKET, [empty], env=MASKED) == []


# --- the real production path: no ``env`` argument, read from os.environ --------
#
# These call ``build_ticket_chunks`` exactly as ``backfill`` does. They are
# deliberately kept separate from the ``env=`` group above: they fail on the
# pre-DIG-1210 code for the reason that matters — the email is *in the chunk* —
# rather than on a signature that did not exist yet.


@pytest.fixture
def clean_env(monkeypatch):
    monkeypatch.delenv(privacy.DISCLOSURE_ENV, raising=False)
    monkeypatch.delenv(privacy.APPROVER_ENV, raising=False)


def test_ambient_environment_leaks_nothing(clean_env):
    chunks = build_ticket_chunks(TICKET, _articles(INTERNAL_ARTICLE), customer_name="Jane Doe")
    blob = _texts(chunks) + _all_metadata(chunks)
    assert CUSTOMER_EMAIL not in blob
    assert ARTICLE_FROM_EMAIL not in blob
    assert "Jane Doe" not in blob
    assert "Müller GmbH" not in blob
    assert "INTERNAL" not in blob
    assert len(chunks) == 1


def test_ambient_environment_alone_cannot_unmask(clean_env, monkeypatch):
    monkeypatch.setenv(privacy.DISCLOSURE_ENV, "unmasked")
    chunks = build_ticket_chunks(TICKET, _articles(INTERNAL_ARTICLE))
    blob = _texts(chunks) + _all_metadata(chunks)
    assert CUSTOMER_EMAIL not in blob
    assert len(chunks) == 1


def test_ambient_environment_with_an_approver_unmasks(clean_env, monkeypatch):
    monkeypatch.setenv(privacy.DISCLOSURE_ENV, "unmasked")
    monkeypatch.setenv(privacy.APPROVER_ENV, "CTO (demo session, accepted 2026-10-05)")
    chunks = build_ticket_chunks(TICKET, _articles(INTERNAL_ARTICLE))
    blob = _texts(chunks) + _all_metadata(chunks)
    assert len(chunks) == 2
    assert CUSTOMER_EMAIL in blob
    assert "INTERNAL" in blob


def test_no_address_survives_into_the_masked_corpus(clean_env):
    """Belt and braces: no *customer* address, whatever field it came from.

    Asserting on named fields can pass while some other field still carries an
    address, which is exactly how the original defect looked. So this sweeps
    the whole chunk for address shapes and then requires every survivor to be
    the one field the policy deliberately keeps.
    """
    chunk = build_ticket_chunks(
        TICKET,
        [CUSTOM_ARTICLE, INTERNAL_ARTICLE],
        customer_name="Jane Doe",
    )[0]
    # The indexed text is the surface a visitor can be quoted, so it must be
    # address-free outright — bodies and titles are the recorded residual, and
    # this fixture's body/subject carry none.
    assert not EMAIL.search(chunk.content)
    survivors = {key: value for key, value in chunk.metadata.items() if EMAIL.search(str(value))}
    # ``owner`` is digithings staff, not customer data: the same call DIG-1063
    # makes for the MCP tools' ``Owner:`` line, because the model needs it to
    # answer "who handles this".
    assert survivors == {"owner": STAFF_EMAIL}


# --- addresses in free text (the part a metadata-only mask cannot reach) --------


def test_an_address_in_the_body_is_redacted():
    """A mail signature is where a customer's own address actually lives."""
    article = {
        **CUSTOM_ARTICLE,
        "body": "<p>Hallo, hier ist Hans Mueller. Meine Adresse ist "
        f"{CUSTOMER_EMAIL}. Bitte um Rueckruf.</p>",
    }
    chunks = build_ticket_chunks(TICKET, [article], env=MASKED)
    assert chunks
    assert CUSTOMER_EMAIL not in _texts(chunks)
    assert not EMAIL.search(chunks[0].content)
    assert "Bitte um Rueckruf" in chunks[0].content


def test_an_address_in_the_subject_is_redacted():
    article = {**CUSTOM_ARTICLE, "subject": f"Rechnung an {CUSTOMER_EMAIL}"}
    chunks = build_ticket_chunks(TICKET, [article], env=MASKED)
    assert CUSTOMER_EMAIL not in _texts(chunks)


def test_an_address_in_the_title_is_redacted():
    chunks = build_ticket_chunks(
        {**TICKET, "title": f"Rechnung fuer {CUSTOMER_EMAIL}"}, _articles(), env=MASKED
    )
    assert CUSTOMER_EMAIL not in _all_metadata(chunks)
    assert chunks[0].metadata["title"].startswith("Rechnung fuer email#")


def test_the_domain_does_not_survive():
    """For a B2B helpdesk the domain is the customer company, so a partial
    mask such as ``j***@sitaas.de`` would still identify. The address goes."""
    chunks = build_ticket_chunks(
        TICKET,
        [{**CUSTOM_ARTICLE, "body": f"<p>Mail an {CUSTOMER_EMAIL} bitte.</p>"}],
        env=MASKED,
    )
    assert "customer.test" not in _texts(chunks)


def test_redaction_keeps_the_same_address_grouped():
    """Two mentions of one address must not look like two people."""
    article = {
        **CUSTOM_ARTICLE,
        "body": f"<p>Von {CUSTOMER_EMAIL} an {CUSTOMER_EMAIL} geschrieben.</p>",
    }
    chunks = build_ticket_chunks(TICKET, [article], env=MASKED)
    pseudonyms = set(re.findall(r"email#[0-9a-f]{8}", chunks[0].content))
    assert len(pseudonyms) == 1


def test_redaction_is_idempotent():
    once = privacy.redact_addresses(f"write to {CUSTOMER_EMAIL}.", env=MASKED)
    twice = privacy.redact_addresses(once, env=MASKED)
    assert once == twice


def test_a_trailing_sentence_period_is_not_part_of_the_address():
    out = privacy.redact_addresses(f"Kontakt: {CUSTOMER_EMAIL}.", env=MASKED)
    assert out.endswith("."), "the sentence's full stop must survive"
    assert f"{CUSTOMER_EMAIL}." not in out


@pytest.mark.parametrize("value", ["", "no address here", "@", "a@b", "name@host"])
def test_redaction_leaves_unremarkable_text_alone(value):
    assert privacy.redact_addresses(value, env=MASKED) == value


def test_unmasked_keeps_the_body_address():
    article = {**CUSTOM_ARTICLE, "body": f"<p>Adresse: {CUSTOMER_EMAIL}</p>"}
    chunks = build_ticket_chunks(TICKET, [article], env=UNMASKED)
    assert CUSTOMER_EMAIL in chunks[0].content


def test_a_name_in_free_text_is_still_present():
    """The recorded residual, pinned so it cannot be lost in a refactor.

    375 of the 547 non-internal chunks in the committed snapshot carry a full
    customer display name in a mail signature. Closing that needs name
    detection, not a regex, and it is the CTO's decision (docs/adr/0031).
    """
    article = {
        **CUSTOM_ARTICLE,
        "body": f"<p>Hallo, hier ist Hans Mueller, meine Adresse ist {CUSTOMER_EMAIL}.</p>",
    }
    chunks = build_ticket_chunks(TICKET, [article], env=MASKED)
    assert "Hans Mueller" in chunks[0].content
    assert CUSTOMER_EMAIL not in chunks[0].content
