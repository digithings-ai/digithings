"""Art. 9 screening on the remote embedding path (DIG-1085, Leaf 11).

DIG-1141 (Leaf C) owns the *record* on this path: that a remote embedding call
emits exactly one record, that the record never carries the texts, that the
deployed image excludes the extra entirely. That is all still true and is pinned
in ``test_egress_embedding_record.py``. This file owns the other half, which did
not exist until this leaf: that the call is **screened** before it goes out.

Three questions, each independently falsifiable:

* **Uniformity.** The remote embedding path constructs its own client, outside
  ``digillm.client``, so the screen attached there cannot see it. If that
  construction is not wrapped, embeddings leave the process with nothing checked.
* **Honesty of the ledger.** A refusal is a *block*, not a provider outage, and a
  screened batch is not an unscreened one. Both distinctions are what a data
  subject request turns on.
* **Non-interference.** The local MiniLM embedder is the default backend and must
  be completely untouched -- pinned by a screen that refuses *everything* and by
  the local embedder still succeeding inside the same test run, so the control
  that the screen is live cannot be vacuous.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from digisearch.embedding.providers import openai as provider_mod

from digillm import client as client_mod
from digillm import egress_record as egress_record_mod

# Measured against digibase's patterns at develop, not from memory:
# "nhs number 485 777 3456" -> refuse ("health",) art9:health:nhs_number.
# ("my nhs number is 485 777 3456" is ALLOWED -- intervening words defeat the
# pattern. That recall gap belongs to the DIG-1071 leaf, whose file this leaf may
# not edit; it is not this leaf's to compensate for by loosening an assertion.)
# CI runs this lane as ``pytest tests/ds/ -m unit`` / ``pytest digillm/tests
# -m unit``. Without a module-level marker pytest DESELECTS every test in
# this file and prints a green line having run nothing, so the whole
# suite would be invisible to CI while looking perfect locally.
pytestmark = pytest.mark.unit

REFUSING_TEXTS = ["nhs number 485 777 3456"]
CLEAN_TEXTS = ["the weather in Rome is mild", "summarise this changelog"]


def _records(tmp_path: Path) -> list[dict[str, Any]]:
    path = tmp_path / "records.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


@pytest.fixture(autouse=True)
def _records_sink(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the egress sink at ``tmp_path``.

    Autouse on purpose. The sink otherwise defaults *inside the checkout*
    (``digiquant/results/egress/records.jsonl``), so without this a test that
    drives a completion writes production-shaped rows into the repository, and a
    test that reads ``tmp_path`` without redirecting reads a file nobody wrote.
    Both are the same mistake, and the second one reads as "nothing was
    recorded" -- which is a wrong answer rather than a missing one.
    """
    monkeypatch.setenv(egress_record_mod.EGRESS_LOG_PATH_ENV, str(tmp_path / "records.jsonl"))


@pytest.fixture
def screen(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Install digibase's screener for the duration of one test.

    Restored through monkeypatch rather than by setting it back to ``None``.
    Those are different states: ``None`` means "a screen is deliberately not
    installed", so every test that ran afterwards would see UNSCREENED where
    production sees the auto-resolved screener -- a suite whose answer depends on
    what ran first. monkeypatch puts the module's original sentinel back, so the
    next test resolves the seam exactly as if this fixture had never run.
    """
    from digibase.art9 import screen_request

    monkeypatch.setattr(client_mod, "_egress_screen", screen_request)
    # A fixture that silently installed nothing would make every assertion below
    # vacuous, so the seam is proved live before the test body runs.
    assert client_mod.get_egress_screen() is screen_request
    yield


class _FakeOpenAI:
    """Stands in for ``openai.OpenAI``; counts constructions and wire calls."""

    instances: list[_FakeOpenAI] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.embed_calls: list[dict[str, Any]] = []
        _FakeOpenAI.instances.append(self)
        self.embeddings = self
        # The screen wraps both surfaces at construction, so the double must
        # carry both attributes or the wrapper -- not the code under test -- is
        # what fails.
        self.chat = self

    def create(self, **kwargs: Any) -> Any:
        self.embed_calls.append(kwargs)
        rows = [_Row([0.1, 0.2]) for _ in kwargs["input"]]
        return _Result(rows)


class _Row:
    def __init__(self, embedding: list[float]) -> None:
        self.embedding = embedding


class _Result:
    def __init__(self, data: list[_Row]) -> None:
        self.data = data


@pytest.fixture
def fake_openai(monkeypatch: pytest.MonkeyPatch) -> type[_FakeOpenAI]:
    """Patch the construction the provider performs lazily inside ``_get_client``."""
    import openai

    _FakeOpenAI.instances = []
    monkeypatch.setattr(openai, "OpenAI", _FakeOpenAI)
    return _FakeOpenAI


def _embedder(**kwargs: Any) -> provider_mod.OpenAIEmbedder:
    kwargs.setdefault("api_key", "sk-test-house")
    return provider_mod.OpenAIEmbedder(**kwargs)


# --- uniformity -------------------------------------------------------------


def test_remote_embedding_client_is_screened_at_construction(
    screen: None, fake_openai: type[_FakeOpenAI]
) -> None:
    """The one construction site in this module must come back wrapped.

    Nothing else screens it: this module drives ``openai.OpenAI`` directly, and
    ``digillm.client`` never sees the client object. An unwrapped construction
    here is the exact gap the leaf exists to close.
    """
    client = _embedder()._get_client()
    assert hasattr(client, "last_screen"), "construction was not wrapped by the screen"
    assert len(fake_openai.instances) == 1, "expected exactly one construction"


def test_the_screen_runs_before_the_wire(fake_openai: type[_FakeOpenAI]) -> None:
    """No screen installed -> nothing screened, and the call still goes out.

    This is the deliberate degradation the leaf keeps (the deployed image
    installs neither digillm nor openai). Pinned so the degradation cannot
    quietly become a crash.
    """
    embedder = _embedder()
    embedder._screened = lambda inner: inner  # type: ignore[method-assign]
    vectors = embedder.embed(list(CLEAN_TEXTS))
    assert len(vectors) == len(CLEAN_TEXTS)
    assert fake_openai.instances[0].embed_calls, "the wire was never reached"


# --- honesty of the ledger -------------------------------------------------


def test_clean_embeddings_are_recorded_as_screened_not_unscreened(
    screen: None, tmp_path: Path, fake_openai: type[_FakeOpenAI]
) -> None:
    """Screened-and-clean is not the same claim as never-screened."""
    _embedder().embed(list(CLEAN_TEXTS))
    rows = _records(tmp_path)
    assert rows, "no egress record was written"
    assert {r["decision"] for r in rows} == {"pass"}
    assert all(r["category_ids"] == [] for r in rows)


def test_refused_embedding_is_recorded_as_refused_not_failed(
    screen: None, tmp_path: Path, fake_openai: type[_FakeOpenAI]
) -> None:
    """A block is not a provider outage.

    Recording it as ``failed`` would tell every reader counting outcomes that
    the provider was unavailable, when nothing was sent at all.
    """
    with pytest.raises(Exception):
        _embedder().embed(list(REFUSING_TEXTS))
    rows = _records(tmp_path)
    assert rows, "a refusal left no record at all"
    row = rows[0]
    assert row["outcome"] == "refused"
    assert row["decision"] == "refused"
    assert row["category_ids"] == ["health"]
    # Validator rule: "none" is reserved for a cache hit.
    assert row["destination"] != "none"
    assert fake_openai.instances[0].embed_calls == [], "the wire was called after a refusal"


def test_the_verdict_is_read_without_importing_digillm_types() -> None:
    """This module must not import digillm at module scope.

    Module scope would raise ``ModuleNotFoundError`` in the deployed image, which
    installs neither digillm nor openai. Compared as plain strings instead,
    because ``EgressDecision`` is a ``StrEnum``.
    """
    source = Path(provider_mod.__file__).read_text()
    body = source.split("class OpenAIEmbedder", 1)[0]
    assert "import digillm" not in body
    assert "from digillm" not in body


def test_missing_digillm_degrades_to_unscreened_rather_than_failing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A digillm that will not import leaves the client exactly as it was.

    Guarded on purpose: this must not become a new import-time failure in a
    module that imports cleanly today. ``sys.modules[...] = None`` is what makes
    ``from digillm.client import ...`` raise ``ImportError`` -- the same shape
    as digillm being absent from the installed image.
    """
    import sys

    monkeypatch.setitem(sys.modules, "digillm.client", None)
    inner = object()
    assert provider_mod.OpenAIEmbedder._screened(inner) is inner


# --- non-interference ------------------------------------------------------


def test_local_minilm_is_unaffected_by_a_screen_that_refuses_everything(
    screen: None, tmp_path: Path, fake_openai: type[_FakeOpenAI]
) -> None:
    """Acceptance test 9, clause 2 -- local MiniLM must be untouched.

    The refusal at the end is the control, and it is deliberately *inside this
    test*: it proves the installed screen is live and refusing right now, so the
    local embedder's success cannot be explained by a screen that was never
    reached, or reached and silently allowed. Without it the first half would
    also pass against a screen that did nothing at all.
    """
    from digisearch.embedding.providers.minilm import MiniLMEmbedder

    local = MiniLMEmbedder(embed_fn=lambda texts: [[0.5, 0.25] for _ in texts])
    vectors = local.embed(["nhs number 485 777 3456", "date of birth 1974-03-02"])
    assert vectors, "the local embedder stopped working when a screen was installed"
    assert _records(tmp_path) == [], "the local path emitted an egress record"

    # Control: the very same screen refuses the remote path in this same run.
    with pytest.raises(Exception):
        _embedder().embed(list(REFUSING_TEXTS))
    refused = [r for r in _records(tmp_path) if r["decision"] == "refused"]
    assert refused, "the installed screen never fired, so the local pass proves nothing"


def test_local_minilm_never_imports_the_remote_provider_or_the_screen() -> None:
    """Structurally, not just behaviourally: MiniLM has no path to this screen."""
    source = Path(provider_mod.__file__).with_name("minilm.py").read_text()
    for token in ("openai", "digillm", "screened_client", "art9"):
        assert token not in source, f"minilm.py must not reference {token}"


def test_both_surfaces_are_reachable_in_one_run(
    screen: None, tmp_path: Path, fake_openai: type[_FakeOpenAI]
) -> None:
    """Uniformity: completions and embeddings are screened by the same leaf.

    A screen that worked on one surface and not the other would still satisfy
    every other test in this file, so the two are driven together here.
    """
    with pytest.raises(Exception):
        _embedder().embed(list(REFUSING_TEXTS))
    assert _records(tmp_path), "the remote path produced no record to compare"
