"""Tests for document parsers."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest

from digisearch.ingestion.parsers.plaintext import PlainTextParser
from digisearch.ingestion.registry import ParserRegistry

# Server/runtime modules that the [server] extra owns plus the DigiSearch client.
# Importing an ingestion parser (the [ingestion] extra) must NOT pull any of
# these in — that is the whole point of the lazy package surface (#633).
_FORBIDDEN_ON_PARSER_IMPORT = (
    "fastapi",
    "uvicorn",
    "mcp",
    "typer",
    "digikey",
    "digisearch.client",
)


@pytest.mark.unit
def test_plaintext_parser() -> None:
    p = PlainTextParser()
    doc = p.parse("hello world")
    assert doc.content == "hello world"
    assert doc.doc_type == "plaintext"


@pytest.mark.unit
def test_registry_plaintext() -> None:
    r = ParserRegistry()
    doc = r.parse("simple text")
    assert "simple text" in doc.content


def _import_isolation_probe(target_import: str) -> subprocess.CompletedProcess[str]:
    """Import ``target_import`` in a FRESH interpreter and report forbidden modules.

    A subprocess is required: asserting on ``sys.modules`` inside the shared
    pytest process would be polluted by sibling tests that import the server
    stack (test_server_query, test_orchestrator_invoke, ...). A clean process
    measures exactly what importing the parser pulls in — independent of what
    the test venv happens to have installed.
    """
    forbidden = ", ".join(repr(m) for m in _FORBIDDEN_ON_PARSER_IMPORT)
    code = textwrap.dedent(f"""
        import sys
        {target_import}
        forbidden = {{{forbidden}}}
        leaked = sorted(forbidden & set(sys.modules))
        assert not leaked, "server/client modules leaked into parser import: " + repr(leaked)
    """)
    # Make the child import the SAME digisearch the parent resolved (e.g. a
    # worktree src on sys.path), not whatever happens to be editable-installed,
    # by forwarding the parent's import paths via PYTHONPATH.
    env = dict(os.environ)
    parent_paths = [p for p in sys.path if p]
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(parent_paths + ([existing] if existing else []))
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.mark.unit
def test_pdf_parser_imports_without_server_stack() -> None:
    """`digisearch.ingestion.parsers.pdf` must import without the [server] stack.

    Proves the PEP 562 lazy ``digisearch/__init__`` does not eagerly import the
    DigiSearch client, and that the parser's own import chain stays light.
    """
    result = _import_isolation_probe("import digisearch.ingestion.parsers.pdf")
    assert result.returncode == 0, result.stderr or result.stdout


@pytest.mark.unit
def test_parser_registry_imports_without_server_stack() -> None:
    """The ParserRegistry entrypoint is also import-light (no server/client)."""
    result = _import_isolation_probe("import digisearch.ingestion.registry")
    assert result.returncode == 0, result.stderr or result.stdout


@pytest.mark.unit
def test_top_level_import_stays_lazy() -> None:
    """`import digisearch` alone must not import the client or the server stack."""
    result = _import_isolation_probe("import digisearch")
    assert result.returncode == 0, result.stderr or result.stdout


@pytest.mark.unit
def test_lazy_client_attribute_still_resolves() -> None:
    """`from digisearch import DigiSearch` (and core models) still works via PEP 562."""
    import digisearch

    # Public names are exported and discoverable...
    for name in ("DigiSearch", "Chunk", "Document", "Query", "Result"):
        assert name in digisearch.__all__
        assert name in dir(digisearch)

    # ...and resolve to the real objects on access.
    from digisearch import Chunk, DigiSearch, Document, Query, Result
    from digisearch.client import DigiSearch as RealClient
    from digisearch.core.models import Document as RealDocument

    assert DigiSearch is RealClient
    assert Document is RealDocument
    assert {Chunk, Query, Result}  # imported without error

    with pytest.raises(AttributeError):
        digisearch.does_not_exist  # noqa: B018 - intentional attribute probe
