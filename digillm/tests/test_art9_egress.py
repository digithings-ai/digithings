"""Art. 9 egress screen: the last line of defence on the client object.

The in-process screens live on digibase's own ingest seams, so by construction
they never see a prompt that reaches a model another way: an MCP tool handler
holding a client from ``get_client_for_model``, or any caller driving the client
directly. This leaf installs the screen on the client itself, which is the only
place that covers every one of those.

The file is organised around three questions, each of which can fail
independently:

* **Uniformity.** Is every construction site screened -- including the ones behind
  the BYOK override, the cheaperinference direct client and the registered-base
  cache? A screen installed at four of five sites is a screen nobody can trust.
* **Honesty of the ledger.** Does the record distinguish "screened and clean"
  from "never screened", and does a refusal get recorded as a block rather than
  as a provider outage that never happened?
* **Non-interference.** The local MiniLM path does not go through digillm at all,
  and must stay that way; and a payload that finds nothing must reach the wire
  byte-identical.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice

import digillm
from digillm import client as client_mod
from digillm import egress_record as egress_record_mod
from digillm.egress_record import EgressCategoryId, EgressDecision
from digillm.overrides import reset_byok, set_byok

# Measured against the landed L1 (digibase art9.py, 620 lines), not from memory and
# not from the patterns' prose. "nhs number 485 777 3456" refuses with
# ('health',) / art9:health:nhs_number; "NHS 485 777 3456" allows; and
# "date of birth 1974-03-02" refuses with ('health',) / art9:health:date_of_birth.
# The health pattern needs the bare phrase immediately before the digits, which is
# why a test that merely asserted "a number was refused" would pass for the wrong
# reason -- "my nhs number is 485 777 3456" is ALLOWED, because the words between
# the phrase and the digits defeat the pattern. That gap is real and is L1's
# (DIG-1071) to own; digibase is leaf 2's file and is not this leaf's to change.
# It is recorded here rather than hidden: the corpus below is retargeted to a
# payload L1 actually refuses, so these tests exercise this leaf's wiring instead
# of L1's recall.
# CI runs this lane as ``pytest tests/ds/ -m unit`` / ``pytest digillm/tests
# -m unit``. Without a module-level marker pytest DESELECTS every test in
# this file and prints a green line having run nothing, so the whole
# suite would be invisible to CI while looking perfect locally.
pytestmark = pytest.mark.unit

REFUSING_MESSAGES = [{"role": "user", "content": "nhs number 485 777 3456"}]
CLEAN_MESSAGES = [{"role": "user", "content": "what is the weather in Rome"}]
EMBEDDING_REFUSAL = "date of birth 1974-03-02"
EMBEDDING_CLEAN = "the weather in Rome is mild"


def _completion(content: str = "ok") -> ChatCompletion:
    return ChatCompletion(
        id="chatcmpl-art9",
        choices=[
            Choice(
                index=0,
                finish_reason="stop",
                message=ChatCompletionMessage(content=content, role="assistant"),
            )
        ],
        created=0,
        model="gpt-4o-mini",
        object="chat.completion",
    )


def _fake_client() -> MagicMock:
    inner = MagicMock()
    inner.chat.completions.create.side_effect = lambda **kw: _completion()
    inner.embeddings.create.side_effect = lambda **kw: MagicMock(data=[MagicMock(embedding=[0.1])])
    return inner


def _records(tmp_path: Path) -> list[dict[str, Any]]:
    path = tmp_path / "records.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


@pytest.fixture
def screen(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install digibase's real screen, and prove afterwards that it was installed.

    An autouse test that asserts its own premise is what keeps a green run from
    meaning "the screen was never there".
    """
    _screen_before = client_mod._egress_screen
    from digibase.art9 import screen_request

    client_mod.set_egress_screen(screen_request)
    monkeypatch.setattr(
        client_mod,
        "get_egress_screen",
        lambda: __import__("digibase.art9", fromlist=["screen_request"]).screen_request,
    )
    assert client_mod.get_egress_screen() is not None
    yield
    # Restore the module's original sentinel, not ``None``: ``None`` is a
    # different state ("a screen is deliberately not installed"), so it would
    # make every later test in the session answer differently depending on
    # what ran first.
    client_mod._egress_screen = _screen_before


@pytest.fixture(autouse=True)
def _records_sink(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the JSONL egress sink at this test's own tmp dir.

    Autouse on purpose. The sink defaults to a path inside the checkout
    (``digiquant/results/egress/records.jsonl``), so a test that drives a
    completion without redirecting it writes production-shaped rows into the
    repository -- and a test that reads ``tmp_path`` without redirecting reads a
    file that was never written, which asserts green or fails for a reason that
    has nothing to do with the code under test. Both are the same mistake.

    The configured-env branch of ``default_sink_path`` is deliberately uncached
    (``_checkout_default_sink_path`` is the cached one), so setenv is enough.
    """
    monkeypatch.setenv(egress_record_mod.EGRESS_LOG_PATH_ENV, str(tmp_path / "records.jsonl"))


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear module-global state and neutralise provider env vars before each test.

    Same shape as the fixture in tests/test_digillm.py: the client cache is a module
    global, so without this a test can be handed a client another test cached -- and
    a screened one at that, which would make the next assertion pass for free.
    """
    digillm.clear_caches()
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-house")


# ── uniformity: every construction site is screened ────────────────────────────


def test_every_construction_site_returns_a_screened_client() -> None:
    """All five OpenAI constructions are wrapped, and the cache cannot undo it.

    Counted at the source rather than asserted per-branch: five sites is a fact
    about this file, and a sixth added later would silently go unscreened.

    Read with ``ast`` rather than by matching text. An earlier version required
    ``OpenAI(`` and ``screened_client(`` to share one physical line, which was
    true only until ``ruff format`` wrapped the argument onto its own line --
    the check then failed on a correct construction. Parsing states the real
    invariant (this call is an argument of that call) and cannot be defeated by
    line wrapping.
    """
    tree = ast.parse((Path(client_mod.__file__)).read_text())
    constructions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "OpenAI"
    ]
    assert len(constructions) == 5, [ast.dump(c) for c in constructions]
    wrapped = {
        id(arg)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "screened_client"
        for arg in node.args
    }
    for call in constructions:
        assert id(call) in wrapped, "an OpenAI() construction is not screened"


def test_get_client_returns_screened_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client_mod, "_client_cache", {})
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    with patch.object(client_mod, "OpenAI", side_effect=lambda **kw: _fake_client()):
        client = client_mod.get_client()
    assert isinstance(client, client_mod._ScreenedOpenAI)


def test_cached_client_is_screened_too(monkeypatch: pytest.MonkeyPatch) -> None:
    """The second caller must not receive an unwrapped object from the cache."""
    monkeypatch.setattr(client_mod, "_client_cache", {})
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    with patch.object(client_mod, "OpenAI", side_effect=lambda **kw: _fake_client()):
        first = client_mod.get_client()
        second = client_mod.get_client()
    assert first is second
    assert isinstance(second, client_mod._ScreenedOpenAI)


def test_byok_construction_is_screened(monkeypatch: pytest.MonkeyPatch) -> None:
    """The BYOK early return is a construction site too, not a special case."""
    monkeypatch.setattr(client_mod, "_client_cache", {})
    token = set_byok(api_key="sk-test", base_url="https://byok.example")
    try:
        with patch.object(client_mod, "OpenAI", side_effect=lambda **kw: _fake_client()):
            client = client_mod.get_client()
        assert isinstance(client, client_mod._ScreenedOpenAI)
    finally:
        reset_byok(token)


# ── the screen actually runs on the completions path ───────────────────────────


def test_clean_payload_reaches_the_wire_unchanged(screen: None) -> None:
    fake = _fake_client()
    with patch.object(client_mod, "OpenAI", side_effect=lambda **kw: fake):
        with patch.object(client_mod, "_client_cache", {}):
            digillm.completion("gpt-4o-mini", list(CLEAN_MESSAGES))
    sent = fake.chat.completions.create.call_args.kwargs["messages"]
    assert sent == CLEAN_MESSAGES


def test_refusing_completion_is_never_sent(screen: None) -> None:
    """The load-bearing assertion: a block stops the wire call, not just the record."""
    fake = _fake_client()
    with patch.object(client_mod, "OpenAI", side_effect=lambda **kw: fake):
        with patch.object(client_mod, "_client_cache", {}):
            with pytest.raises(client_mod.Art9EgressRefused):
                digillm.completion("gpt-4o-mini", list(REFUSING_MESSAGES))
    fake.chat.completions.create.assert_not_called()


def test_refusal_carries_the_category_and_never_the_value(screen: None) -> None:
    fake = _fake_client()
    with patch.object(client_mod, "OpenAI", side_effect=lambda **kw: fake):
        with patch.object(client_mod, "_client_cache", {}):
            with pytest.raises(client_mod.Art9EgressRefused) as caught:
                digillm.completion("gpt-4o-mini", list(REFUSING_MESSAGES))
    assert caught.value.categories == ("health",)
    # The reason is a stable machine code and travels into log aggregators, so it
    # must not be able to carry the matched digits.
    assert caught.value.reason == "art9:health:nhs_number"
    assert "485" not in str(caught.value)


def test_verdict_is_readable_off_the_client_by_any_caller(screen: None) -> None:
    """digisearch reads the verdict this way, without importing the exception type."""
    fake = _fake_client()
    client = client_mod.screened_client(fake)
    with pytest.raises(RuntimeError):
        client.chat.completions.create(model="gpt-4o-mini", messages=list(REFUSING_MESSAGES))
    decision, categories = client_mod.client_screen_fields(client)
    assert decision is EgressDecision.REFUSED
    assert categories == ("health",)


# ── the ledger tells the three facts apart ─────────────────────────────────────


def test_clean_call_is_recorded_as_screened_not_unscreened(screen: None, tmp_path: Path) -> None:
    monkey = Path(tmp_path)
    fake = _fake_client()
    with patch.object(client_mod, "OpenAI", side_effect=lambda **kw: fake):
        with patch.object(client_mod, "_client_cache", {}):
            digillm.completion("gpt-4o-mini", list(CLEAN_MESSAGES))
    rows = _records(monkey)
    assert rows, "no egress record was written"
    assert {r["decision"] for r in rows} == {"pass"}


def test_refusal_is_recorded_as_refused_not_failed(screen: None, tmp_path: Path) -> None:
    """A block is not a provider outage.

    Recording it as ``failed`` would tell every reader counting outcomes that the
    provider was unavailable, when in fact nothing was sent at all.
    """
    fake = _fake_client()
    with patch.object(client_mod, "OpenAI", side_effect=lambda **kw: fake):
        with patch.object(client_mod, "_client_cache", {}):
            with pytest.raises(client_mod.Art9EgressRefused):
                digillm.completion("gpt-4o-mini", list(REFUSING_MESSAGES))
    rows = _records(tmp_path)
    assert rows, "a refusal left no record at all"
    row = rows[0]
    assert row["decision"] == "refused"
    assert row["outcome"] == "refused"
    assert row["category_ids"] == ["health"]
    # Validator rule: "none" is reserved for a cache hit.
    assert row["destination"] != "none"


def test_refusal_is_not_retried(screen: None, tmp_path: Path) -> None:
    """One block, one attempt: the payload is unchanged, so a retry repeats it."""
    fake = _fake_client()
    with patch.object(client_mod, "OpenAI", side_effect=lambda **kw: fake):
        with patch.object(client_mod, "_client_cache", {}):
            with pytest.raises(client_mod.Art9EgressRefused):
                digillm.completion("gpt-4o-mini", list(REFUSING_MESSAGES))
    fake.chat.completions.create.assert_not_called()
    rows = _records(tmp_path)
    assert len([r for r in rows if r["decision"] == "refused"]) == 1


def test_unscreened_is_reported_when_no_screen_is_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without a screen the record says UNSCREENED rather than claiming a verdict.

    This is the one place the leaf deliberately degrades rather than fails closed,
    so it is pinned by a test: the difference between "screened, found nothing"
    and "never screened" is exactly what a data-subject request turns on.
    """
    monkeypatch.setattr(client_mod, "get_egress_screen", lambda: None)
    outcome = client_mod.screen_egress_payload("anything")
    assert outcome.decision is EgressDecision.UNSCREENED
    assert outcome.category_ids == ()
    assert outcome.reason == "egress_screen_unavailable"


def test_pass_requires_the_screen_to_have_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """PASS and UNSCREENED are different rows; the mapping is not a detail."""
    monkeypatch.setattr(client_mod, "get_egress_screen", lambda: None)
    unscreened = client_mod.screen_egress_payload("hello")
    from digibase.art9 import screen_request

    monkeypatch.setattr(client_mod, "get_egress_screen", lambda: screen_request)
    screened = client_mod.screen_egress_payload("hello")
    assert unscreened.decision is EgressDecision.UNSCREENED
    assert screened.decision is EgressDecision.PASS
    assert unscreened.decision is not screened.decision


# ── masking: unreachable today, and it must not lie when it is ────────────────


def test_mask_without_a_redaction_refuses_rather_than_sending_raw(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """digibase's screen returns redacted=None on every path today.

    Substituting None would send *less* than was screened and sending the
    original unmasked would be the failure this epic exists to prevent, so the
    honest answer is to refuse.
    """
    from digibase.art9 import ScreenResult, screen_request

    def fake_screen(payload: Any, *, exception_ref: str | None = None) -> Any:
        return ScreenResult(
            categories=("health",),
            redacted=None,
            decision="mask",
            reason="art9:health:nhs_number",
            exception_ref=exception_ref,
        )

    monkeypatch.setattr(client_mod, "get_egress_screen", lambda: fake_screen)
    with pytest.raises(client_mod.Art9EgressRefused) as caught:
        client_mod.screen_egress_payload(REFUSING_MESSAGES)
    assert caught.value.reason.endswith(":mask_without_redaction")
    assert caught.value.categories == ("health",)
    assert screen_request is not None  # the real screen is imported, not stubbed


def test_mask_with_a_redaction_substitutes_the_masked_copy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from digibase.art9 import ScreenResult

    redacted = [{"role": "user", "content": "[REDACTED]"}]

    def fake_screen(payload: Any, *, exception_ref: str | None = None) -> Any:
        return ScreenResult(
            categories=("health",),
            redacted=redacted,
            decision="mask",
            reason="art9:health:nhs_number",
            exception_ref="exception-1",
        )

    monkeypatch.setattr(client_mod, "get_egress_screen", lambda: fake_screen)
    fake = _fake_client()
    client = client_mod.screened_client(fake)
    client.chat.completions.create(model="gpt-4o-mini", messages=list(REFUSING_MESSAGES))
    sent = fake.chat.completions.create.call_args.kwargs["messages"]
    assert sent == redacted
    assert "485" not in json.dumps(sent)


# ── the decision vocabulary the wiring can actually reach (C4 requirement 2) ───


def test_category_enum_matches_digibase_category_order() -> None:
    """The category ids cross a package boundary; drift would be silent.

    ``ScreenResult.categories`` is a tuple of plain strings and
    ``EgressCategoryId`` is a StrEnum, so nothing at runtime would catch the two
    vocabularies drifting apart -- the record would simply gain a category the
    screen never produced.
    """
    from digibase.art9 import category_order

    assert tuple(c.value for c in EgressCategoryId) == tuple(category_order)
    assert set(EgressCategoryId) == set(category_order)


def test_only_honest_decisions_are_reachable_through_the_screen(screen: None) -> None:
    """The reachable subset, pinned at the seam rather than at the enum.

    The enum being closed is not the claim; the claim is that this wiring cannot
    produce MASKED without a redaction to justify it, and cannot produce a hit
    category without a screen that returned one.
    """
    reached = set()
    for messages in (CLEAN_MESSAGES, REFUSING_MESSAGES):
        fake = _fake_client()
        client = client_mod.screened_client(fake)
        try:
            client.chat.completions.create(model="gpt-4o-mini", messages=list(messages))
        except client_mod.Art9EgressRefused:
            pass
        decision, categories = client_mod.client_screen_fields(client)
        assert (categories == ()) == (decision is EgressDecision.PASS)
        reached.add(decision)

    assert reached == {EgressDecision.PASS, EgressDecision.REFUSED}
    # MASKED would need an exception_ref plumbed to the screen; nothing here
    # supplies one, so claiming the leaf reaches it would be false.
    assert EgressDecision.MASKED not in reached


def test_every_hit_carries_categories_because_the_validator_requires_it(
    screen: None,
) -> None:
    """A refusal row with no categories would be indistinguishable from a pass."""
    fake = _fake_client()
    client = client_mod.screened_client(fake)
    with pytest.raises(client_mod.Art9EgressRefused):
        client.chat.completions.create(model="gpt-4o-mini", messages=list(REFUSING_MESSAGES))
    decision, categories = client_mod.client_screen_fields(client)
    assert decision is EgressDecision.REFUSED
    assert categories, "REFUSED without categories violates EgressRecord._validate_shape"


# ── embeddings go through the same client seam ─────────────────────────────────


def test_embeddings_are_screened_through_the_same_client(screen: None) -> None:
    fake = _fake_client()
    client = client_mod.screened_client(fake)
    with pytest.raises(client_mod.Art9EgressRefused):
        client.embeddings.create(model="text-embedding-3-small", input=[EMBEDDING_REFUSAL])
    fake.embeddings.create.assert_not_called()


def test_clean_embeddings_are_passed_through(screen: None) -> None:
    fake = _fake_client()
    client = client_mod.screened_client(fake)
    client.embeddings.create(model="text-embedding-3-small", input=[EMBEDDING_CLEAN])
    assert fake.embeddings.create.call_args.kwargs["input"] == [EMBEDDING_CLEAN]


# ── non-interference ───────────────────────────────────────────────────────────


def test_client_behaves_like_the_object_it_wraps() -> None:
    """The proxy must not change a client beyond screening it."""
    fake = _fake_client()
    fake.base_url = "https://provider.example/v1"
    client = client_mod.screened_client(fake)
    # base_url is read by _egress_destination to place the call in the ledger.
    assert client.base_url == "https://provider.example/v1"
    assert client.chat.completions is not fake.chat.completions
    assert client.with_raw_response is fake.with_raw_response


def test_egress_destination_resolves_through_the_proxy() -> None:
    fake = _fake_client()
    fake.base_url = "https://user:secret@provider.example/v1"
    client = client_mod.screened_client(fake)
    destination = client_mod._egress_destination(client)
    assert destination == "https://provider.example/v1"
    assert "secret" not in destination


def test_local_minilm_never_reaches_this_leaf() -> None:
    """The default embedder is local and must stay unscreened.

    MiniLM runs an ONNX model in-process, so there is no outbound call, no
    provider and no destination. Screening it would be screening nothing while
    making the real production path -- the default embedder -- look covered.
    """
    import digisearch.embedding.providers.minilm as minilm_module

    source = Path(minilm_module.__file__).read_text()
    assert "openai" not in source
    assert "digillm" not in source
    assert "screened_client" not in source
    assert "art9" not in source


# ── the digest describes what left, not what was withheld ─────────────────────


def _allow_screen(payload: Any, *, exception_ref: str | None = None) -> Any:
    from digibase.art9 import ScreenResult

    return ScreenResult(
        categories=(), redacted=None, decision="allow", reason="art9:clear", exception_ref=None
    )


def _mask_screen(redacted: Any) -> Any:
    def screen(payload: Any, *, exception_ref: str | None = None) -> Any:
        from digibase.art9 import ScreenResult

        return ScreenResult(
            categories=("health",),
            redacted=redacted,
            decision="mask",
            reason="art9:health:nhs_number",
            exception_ref="exception-1",
        )

    return screen


def test_a_masked_egress_record_digests_the_masked_copy_not_the_original(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A masked record must describe the bytes the provider received.

    The retry loop binds ``outbound_payload = kwargs.get("messages")`` *before*
    the attempt, but the screen substitutes the redacted copy *inside*
    ``create`` on a fresh dict built by the ``**kwargs`` expansion. So the two
    are not the same object graph, and the pre-call binding keeps the copy that
    was withheld. An egress ledger that then reports a digest of the withheld
    text describes an egress that did not happen.
    """
    redacted = [{"role": "user", "content": "[REDACTED]"}]

    # With no pepper the ledger deliberately records ``payload_digest: null``,
    # and then ``masked == plain`` would hold because both are ``None`` -- the
    # whole comparison satisfied by absent data. Set a real key so a missing
    # digest cannot make this test pass for the wrong reason.
    monkeypatch.setenv(egress_record_mod.DIGEST_KEY_ENV, "k" * 32)

    def _call(screen: Any, messages: Any) -> Any:
        monkeypatch.setattr(client_mod, "get_egress_screen", lambda: screen)
        client_mod.set_egress_screen(screen)
        digillm.clear_caches()
        fake = _fake_client()
        # A real base_url, not a bare MagicMock attribute: the retry loop reads it
        # through ``_egress_destination`` before it attempts anything, and an
        # unresolvable one takes the attempt out of the loop entirely -- which
        # reads as "create was never called" rather than as the wiring fault.
        fake.base_url = "https://api.example.test/v1"
        with patch.object(client_mod, "OpenAI", side_effect=lambda **kw: fake):
            with patch.object(client_mod, "_client_cache", {}):
                digillm.completion("gpt-4o-mini", list(messages))
        return fake.chat.completions.create.call_args.kwargs["messages"]

    masked_sent = _call(_mask_screen(redacted), REFUSING_MESSAGES)
    plain_sent = _call(_allow_screen, redacted)
    original_sent = _call(_allow_screen, REFUSING_MESSAGES)

    # What actually went on the wire, per call.
    assert masked_sent == redacted
    assert plain_sent == redacted
    assert original_sent == list(REFUSING_MESSAGES)

    rows = _records(tmp_path)
    assert len(rows) == 3, f"expected one record per call, got {len(rows)}"
    assert [r["decision"] for r in rows] == ["masked", "pass", "pass"]
    masked_digest, plain_digest, original_digest = (r["payload_digest"] for r in rows)

    # Non-vacuity first: an absent digest is not a comparison.
    assert masked_digest and plain_digest and original_digest, (
        f"records carry no digest to compare: {masked_digest!r} "
        f"{plain_digest!r} {original_digest!r}"
    )

    # Same bytes on the wire, same digest -- the masked record describes the
    # egress rather than the intent.
    assert masked_digest == plain_digest
    # And it is NOT the digest of the copy the screen withheld. Without this the
    # assertion above could pass for the wrong reason.
    assert masked_digest != original_digest
