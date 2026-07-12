"""Synthesizer tests: TemplateSynthesizer (deterministic) + DigiLLMSynthesizer (mocked).

DigiLLMSynthesizer tests never call a live model — ``digillm.completion`` is
monkeypatched, matching the repo convention of mocking HTTP/LLM calls in unit
tests. Skipped (via ``importorskip``) unless the ``digiskills[llm]`` extra
(``digillm``) is installed.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from digiskills.models import Corpus, SkillSource, SourceDocument, SourceKind
from digiskills.synthesize import TemplateSynthesizer

pytestmark = pytest.mark.unit


def _source(**kwargs: object) -> SkillSource:
    kwargs.setdefault("kind", SourceKind.URLS)
    kwargs.setdefault("name", "acme-sdk")
    kwargs.setdefault("urls", ["https://example.com"])
    return SkillSource(**kwargs)  # type: ignore[arg-type]


def _corpus() -> Corpus:
    return Corpus(
        documents=[
            SourceDocument(origin="README.md", title="README.md", content="# Acme\n\nDo X."),
            SourceDocument(
                origin="src/client.py",
                title="src/client.py",
                content="def get_widget(): ...",
                content_type="text/x-python",
            ),
        ]
    )


class TestTemplateSynthesizer:
    def test_uses_description_hint(self) -> None:
        source = _source(description_hint="How to use the Acme SDK")
        package = TemplateSynthesizer().synthesize(_corpus(), source)
        assert package.manifest.description == "How to use the Acme SDK"
        assert package.manifest.name == "acme-sdk"

    def test_generates_placeholder_description_without_hint(self) -> None:
        package = TemplateSynthesizer().synthesize(_corpus(), _source())
        assert "2 document" in package.manifest.description

    def test_builds_one_reference_per_document(self) -> None:
        package = TemplateSynthesizer().synthesize(_corpus(), _source())
        assert len(package.references) == 2
        paths = {r.relative_path for r in package.references}
        assert paths == {"references/README.md", "references/src__client.py.md"}

    def test_code_reference_wrapped_in_fenced_block(self) -> None:
        package = TemplateSynthesizer().synthesize(_corpus(), _source())
        code_ref = next(r for r in package.references if "client" in r.relative_path)
        assert "```python" in code_ref.content

    def test_empty_corpus_produces_placeholder_body(self) -> None:
        package = TemplateSynthesizer().synthesize(Corpus(), _source())
        assert package.references == []
        assert "No documents" in package.body

    def test_untrusted_document_gets_banner_in_reference(self) -> None:
        corpus = Corpus(
            documents=[
                SourceDocument(
                    origin="https://example.com/docs",
                    title="https://example.com/docs",
                    content="Do X.",
                    trusted=False,
                )
            ]
        )
        package = TemplateSynthesizer().synthesize(corpus, _source())
        assert "Untrusted external content" in package.references[0].content
        assert "Do X." in package.references[0].content

    def test_trusted_document_has_no_banner(self) -> None:
        package = TemplateSynthesizer().synthesize(_corpus(), _source())
        assert "Untrusted external content" not in package.references[0].content

    def test_untrusted_document_gets_banner_in_body(self) -> None:
        corpus = Corpus(
            documents=[
                SourceDocument(origin="u", title="u", content="x", trusted=False),
            ]
        )
        package = TemplateSynthesizer().synthesize(corpus, _source())
        assert "Untrusted external content" in package.body

    def test_all_trusted_corpus_has_no_banner_in_body(self) -> None:
        package = TemplateSynthesizer().synthesize(_corpus(), _source())
        assert "Untrusted external content" not in package.body

    def test_reference_filenames_collision_safe(self) -> None:
        corpus = Corpus(
            documents=[
                SourceDocument(origin="a/b.md", title="t1", content="one"),
                SourceDocument(origin="a__b.md", title="t2", content="two"),
            ]
        )
        package = TemplateSynthesizer().synthesize(corpus, _source())
        paths = [r.relative_path for r in package.references]
        assert len(paths) == len(set(paths))


class TestDigiLLMSynthesizer:
    def test_synthesize_calls_digillm_completion(self, monkeypatch: pytest.MonkeyPatch) -> None:
        digillm = pytest.importorskip("digillm")
        captured: dict[str, object] = {}

        def fake_completion(model, messages, *, temperature=0.2, response_format=None, **kwargs):
            captured["model"] = model
            captured["messages"] = messages
            payload = json.dumps(
                {
                    "description": "Use the Acme SDK to fetch widgets.",
                    "body": "# acme-sdk\n\nStep 1.",
                }
            )
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=payload))]
            )

        monkeypatch.setattr(digillm, "completion", fake_completion)

        from digiskills.synthesize import DigiLLMSynthesizer

        synthesizer = DigiLLMSynthesizer(model="openrouter/auto")
        package = synthesizer.synthesize(_corpus(), _source())

        assert package.manifest.description == "Use the Acme SDK to fetch widgets."
        assert package.body == "# acme-sdk\n\nStep 1."
        assert len(package.references) == 2
        assert captured["model"] == "openrouter/auto"
        system_message = captured["messages"][0]["content"]
        assert "untrusted third-party data" in system_message

    def test_untrusted_corpus_gets_banner_in_body(self, monkeypatch: pytest.MonkeyPatch) -> None:
        digillm = pytest.importorskip("digillm")

        def fake_completion(model, messages, *, temperature=0.2, response_format=None, **kwargs):
            payload = json.dumps({"description": "d", "body": "# acme-sdk\n\nStep 1."})
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=payload))]
            )

        monkeypatch.setattr(digillm, "completion", fake_completion)

        from digiskills.synthesize import DigiLLMSynthesizer

        corpus = Corpus(
            documents=[SourceDocument(origin="u", title="u", content="x", trusted=False)]
        )
        package = DigiLLMSynthesizer(model="openrouter/auto").synthesize(corpus, _source())

        assert "Untrusted external content" in package.body
        assert "Step 1." in package.body

    def test_default_model_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        pytest.importorskip("digillm")
        monkeypatch.setenv("DIGISKILLS_SYNTHESIS_MODEL", "xai/grok-test")

        from digiskills.synthesize import DigiLLMSynthesizer

        assert DigiLLMSynthesizer().model == "xai/grok-test"

    def test_non_json_response_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        digillm = pytest.importorskip("digillm")

        def fake_completion(*args: object, **kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="not json"))]
            )

        monkeypatch.setattr(digillm, "completion", fake_completion)

        from digiskills.synthesize import DigiLLMSynthesizer

        with pytest.raises(ValueError, match="non-JSON"):
            DigiLLMSynthesizer().synthesize(_corpus(), _source())
