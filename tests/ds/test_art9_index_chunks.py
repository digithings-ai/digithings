"""Acceptance test 1 for the Art. 9 screen at the entry of ``index_chunks``.

Spec §5.3 (L1) on DIG-912, leaf L6 of the plan on DIG-959.

The screen must refuse **before** anything is persisted and **before** anything
is embedded. Asserting that a call raised is not acceptance test 1: it passes
just as well when the backend write already happened. So every refusal case here
asserts two independent facts:

1. the backend write path was never reached, and
2. no vector appears in any backend afterwards.

Both assertions are vacuous unless the write path *can* fire, so the module
opens with positive controls that a benign chunk set does reach the backend.
"""

from __future__ import annotations

import pytest
from digibase.art9 import ScreenResult
from digisearch.core.models import Chunk
from digisearch.pipeline import ingest as ingest_module
from digisearch.pipeline.ingest import IngestError, index_chunks
from digisearch.search import _stub

REFUSED_CODE = "art9_special_category"
REFUSED_STATUS = 422

# Trips the screen by value pattern (`nhs_number`) in the chunk content.
NHS_CONTENT = "Patient NHS number: 943 476 5919 was seen in clinic."
# Trips the screen by field name (`diagnosis`) in chunk metadata.
DIAGNOSIS_METADATA = {"diagnosis": "acute sinusitis"}
# Keys that are not in the §5.5 table. Must not trip anything.
SAFE_METADATA = {"page": 3, "title": "Q3 results", "department": "finance"}
BENIGN_CONTENT = "Quarterly revenue rose 4 percent."


def _chunks(content: str = BENIGN_CONTENT, **metadata) -> list[Chunk]:
    return [Chunk(id="c1", content=content, doc_id="doc-1", metadata=dict(metadata))]


class _SpyProvider:
    """Minimal EmbeddingProvider stand-in that records every embed call."""

    def __init__(self) -> None:
        self.embedded: list[list[str]] = []

    def embed(self, texts):
        self.embedded.append(list(texts))
        return [[0.0, 0.0] for _ in texts]


@pytest.fixture
def backend_spy(monkeypatch):
    """Record every backend write instead of performing it.

    Patches the router itself *and* both backend classes' ``add()``, so the
    assertion holds whichever branch ``route_add_chunks`` would have taken.
    """
    calls: list[tuple[str, object]] = []

    def _record(where):
        def _add(*args, **kwargs):
            calls.append((where, args[1] if len(args) > 1 else args))

        return _add

    monkeypatch.setattr(_stub, "route_add_chunks", _record("route_add_chunks"))
    monkeypatch.setattr(_stub, "_stub_add_chunks", _record("_stub_add_chunks"))
    for mod, cls in (
        ("digisearch.indexes.backends.vectorize", "VectorizeBackend"),
        ("digisearch.indexes.backends.chroma", "ChromaBackend"),
    ):
        monkeypatch.setattr(f"{mod}.{cls}.add", _record(f"{cls}.add"), raising=False)

    _stub.get_stub_index().clear()
    yield calls
    _stub.get_stub_index().clear()


# --------------------------------------------------------------------------
# Positive controls. Without these, every "never called" below passes vacuously.
# --------------------------------------------------------------------------


def test_positive_control_benign_chunks_reach_the_backend(backend_spy):
    """A benign chunk set DOES reach the backend, so the spy can fire.

    The spy sits on ``route_add_chunks`` itself, which is the module attribute
    ``index_chunks`` looks up at call time, so this is the first thing reached.
    """
    index_chunks("pos-control", _chunks(**SAFE_METADATA), auto_embed=False)

    assert backend_spy, "spy never fired: every 'never called' assertion is vacuous"
    assert [where for where, _ in backend_spy] == ["route_add_chunks"]


def test_positive_control_benign_chunks_land_in_the_stub_index(monkeypatch):
    """And the real router really does store them (requirement 2 has teeth)."""
    monkeypatch.setenv("DIGISEARCH_ALLOW_STUB", "1")
    _stub.get_stub_index().clear()
    try:
        index_chunks("pos-control-2", _chunks(**SAFE_METADATA), auto_embed=False)
        assert [c.content for c in _stub.get_stub_index()["pos-control-2"]] == [BENIGN_CONTENT]
    finally:
        _stub.get_stub_index().clear()


def test_positive_control_the_screen_actually_runs(monkeypatch, backend_spy):
    """``screen_request`` is called on every non-empty batch at this seam."""
    seen: list[object] = []
    real = ingest_module.screen_request

    def _spy(payload, **kwargs):
        seen.append(payload)
        return real(payload, **kwargs)

    monkeypatch.setattr(ingest_module, "screen_request", _spy)
    index_chunks("screen-runs", _chunks(**SAFE_METADATA), auto_embed=False)

    assert len(seen) == 1, "the screen was skipped"
    assert seen[0][0]["content"] == BENIGN_CONTENT
    assert seen[0][0]["metadata"] == SAFE_METADATA


# --------------------------------------------------------------------------
# Acceptance test 1
# --------------------------------------------------------------------------


@pytest.mark.parametrize("auto_embed", [True, False])
def test_refusal_never_reaches_the_backend(backend_spy, auto_embed):
    """1. the backend's ``add()`` is never called, on either auto_embed setting."""
    provider = _SpyProvider()

    with pytest.raises(IngestError) as excinfo:
        index_chunks(
            "refused", _chunks(NHS_CONTENT), embedding_provider=provider, auto_embed=auto_embed
        )

    assert excinfo.value.code == REFUSED_CODE
    assert excinfo.value.http_status == REFUSED_STATUS
    assert backend_spy == [], f"backend write happened despite the refusal: {backend_spy}"
    assert provider.embedded == [], "the refused chunk was embedded"


@pytest.mark.parametrize("auto_embed", [True, False])
def test_refusal_leaves_no_vector_in_any_backend(monkeypatch, auto_embed):
    """2. no vector appears in any backend afterwards, via the *real* router."""
    monkeypatch.setenv("DIGISEARCH_ALLOW_STUB", "1")
    _stub.get_stub_index().clear()
    try:
        with pytest.raises(IngestError) as excinfo:
            index_chunks("refused-real", _chunks(NHS_CONTENT), auto_embed=auto_embed)

        assert excinfo.value.code == REFUSED_CODE
        assert _stub.get_stub_index() == {}, "a vector reached the backend"
    finally:
        _stub.get_stub_index().clear()


def test_field_name_hit_refuses_before_embed(backend_spy):
    """A §5.5 field name in chunk metadata refuses even with clean content."""
    provider = _SpyProvider()

    with pytest.raises(IngestError) as excinfo:
        index_chunks("field-name", _chunks(**DIAGNOSIS_METADATA), embedding_provider=provider)

    assert excinfo.value.code == REFUSED_CODE
    assert backend_spy == []
    assert provider.embedded == []


def test_metadata_string_values_are_screened_too(backend_spy):
    """A sensitive value under a neutral key still refuses."""
    with pytest.raises(IngestError) as excinfo:
        index_chunks("meta-value", _chunks(NHS_CONTENT, note="NHS number: 943 476 5919"))

    assert excinfo.value.code == REFUSED_CODE
    assert backend_spy == []


# --------------------------------------------------------------------------
# Ordering: the screen precedes provider resolution, embed and the write.
# --------------------------------------------------------------------------


def test_screen_runs_before_apply_embeddings(backend_spy):
    """Refusal happens before ``apply_embeddings``, not after it."""
    seen: list[str] = []
    real = ingest_module.apply_embeddings

    def _spy(chunks, provider):
        seen.append("apply_embeddings")
        return real(chunks, provider)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(ingest_module, "apply_embeddings", _spy)
    try:
        with pytest.raises(IngestError):
            index_chunks("order", _chunks(NHS_CONTENT), embedding_provider=_SpyProvider())
    finally:
        monkeypatch.undo()

    assert seen == [], "apply_embeddings ran before the screen refused"
    assert backend_spy == []


def test_auto_embed_false_refuses_without_resolving_a_provider(monkeypatch):
    """``auto_embed=False`` needs no provider and still refuses.

    This is the path where the backend embeds the chunk itself
    (``vectorize.py``), so a screen placed at the ``apply_embeddings`` call site
    would sit downstream of the embed it was meant to precede. With
    ``auto_embed=True`` and no provider, resolving one would raise
    ``EmbeddingConfigError`` first — so this refusal also proves the screen runs
    before provider resolution.
    """
    import digisearch.embedding.factory as factory

    monkeypatch.setattr(
        factory,
        "resolve_embedding_pipeline",
        lambda: pytest.fail("provider resolution ran despite the refusal"),
    )

    with pytest.raises(IngestError) as excinfo:
        index_chunks("no-provider", _chunks(NHS_CONTENT), auto_embed=False)

    assert excinfo.value.code == REFUSED_CODE


# --------------------------------------------------------------------------
# The screen's own contract at this seam
# --------------------------------------------------------------------------


def test_reason_never_carries_the_matched_value(backend_spy):
    """The refusal reason is a category/signal label, never the data."""
    with pytest.raises(IngestError) as excinfo:
        index_chunks("leak", _chunks(NHS_CONTENT), auto_embed=False)

    message = str(excinfo.value)
    assert "943" not in message
    assert "5919" not in message
    assert "art9:" in message


def test_empty_chunk_list_is_allowed_through(backend_spy):
    """An empty batch is not a refusal, and still no-ops in the router as before.

    ``index_chunks`` reaches ``route_add_chunks`` with an empty list today and
    that returns ``None``; this pins the screen as the only thing that changed.
    """
    assert index_chunks("empty", [], auto_embed=False) is None
    assert [where for where, _ in backend_spy] == ["route_add_chunks"]


def test_screen_fails_closed_on_any_decision_but_allow(monkeypatch, backend_spy):
    """Only ``allow`` passes. A future decision must not open the gate."""
    real = ingest_module.screen_request
    monkeypatch.setattr(
        ingest_module,
        "screen_request",
        lambda payload, **kw: ScreenResult(
            categories=("health",),
            redacted=None,
            decision="mask",
            reason="art9:health:nhs_number",
            exception_ref="OPS-1",
        ),
    )
    assert real is not ingest_module.screen_request

    with pytest.raises(IngestError) as excinfo:
        index_chunks("fails-closed", _chunks(**SAFE_METADATA), auto_embed=False)

    assert excinfo.value.code == REFUSED_CODE
    assert backend_spy == []


def test_no_bypass_switch_exists_at_this_seam():
    """No env var, flag or per-caller opt-out may reopen this gate.

    Scans the AST, not the text. A text scan for "bypass" or "exception_ref"
    fires on the docstring that documents their absence, which is the same trap
    as a guard that greps for a secret name inside the prose retracting it.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(ingest_module))

    env_reads = [
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr in {"environ", "getenv", "env"}
        and isinstance(node.value, ast.Name)
        and node.value.id == "os"
    ]
    assert env_reads == [], f"an env-var escape hatch may not live here: {env_reads}"

    banned = {"exception_ref", "bypass", "skip_screen", "override", "allow_art9"}
    passed = [
        kw.arg
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for kw in node.keywords
        if kw.arg in banned
    ]
    assert passed == [], f"an opt-out argument may not exist here: {passed}"
