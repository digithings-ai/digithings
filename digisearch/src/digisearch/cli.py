"""DigiSearch CLI. Typer-based. Entry point: digisearch."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer

app = typer.Typer(help="DigiSearch – RAG, document search for Digi ecosystem")


def _pick_chunker(name: str) -> Any:
    from digisearch.ingestion.chunkers.fixed import FixedSizeChunker
    from digisearch.ingestion.chunkers.recursive import RecursiveChunker

    if name == "recursive":
        return RecursiveChunker(chunk_size=512, chunk_overlap=64)
    if name == "fixed":
        return FixedSizeChunker(chunk_size=512)
    return RecursiveChunker(chunk_size=512, chunk_overlap=64)


def _sidecar_path_for(file_path: Path) -> Path:
    y = file_path.parent / f"{file_path.stem}.yaml"
    if y.is_file():
        return y
    return file_path.parent / f"{file_path.stem}.yml"


def _ingest_paths(paths: list[Path], index: str, chunker_name: str) -> int:
    from digisearch.core.evidence_metadata import (
        load_sidecar_yaml,
        merge_document_metadata_into_chunks,
        metadata_from_sidecar_dict,
    )
    from digisearch.ingestion.registry import ParserRegistry
    from digisearch.search._stub import add_chunks

    registry = ParserRegistry()
    ch = _pick_chunker(chunker_name)
    total = 0
    for p in paths:
        if not p.is_file() or not registry.get_parser(str(p)):
            continue
        try:
            doc = registry.parse(p)
            side = _sidecar_path_for(p)
            side_meta = metadata_from_sidecar_dict(load_sidecar_yaml(side))
            doc.metadata = {**(doc.metadata or {}), **side_meta}
            chunks = ch.chunk(doc)
            merge_document_metadata_into_chunks(doc, chunks)
            doc.chunks = chunks
            add_chunks(index, chunks)
            total += len(chunks)
            typer.echo(f"Ingested {p.name}: {len(chunks)} chunks")
        except Exception as e:
            typer.echo(f"Skip {p}: {e}", err=True)
    return total


@app.command()
def ingest(
    index: str = typer.Option("default", "--index", "-i", help="Index name"),
    source: Path = typer.Argument(..., help="File or directory to ingest"),
    chunker: str = typer.Option("recursive", "--chunker", "-c", help="recursive | fixed | sentence"),
) -> None:
    """Ingest documents into an index (stub in-process). Loads ``{stem}.yaml`` / ``.yml`` sidecars."""
    sources = list(source.rglob("*")) if source.is_dir() else [source]
    paths = [p for p in sources if p.is_file()]
    total = _ingest_paths(paths, index, chunker)
    typer.echo(f"Total chunks: {total}")


@app.command("ingest-batch")
def ingest_batch(
    index: str = typer.Option("default", "--index", "-i", help="Index name"),
    directory: Path = typer.Argument(..., help="Directory of PDFs/Markdown and optional YAML sidecars"),
    chunker: str = typer.Option("recursive", "--chunker", "-c", help="recursive | fixed | sentence"),
) -> None:
    """Batch-ingest every supported file under a directory (PDF + YAML sidecar pattern)."""
    paths = sorted(directory.rglob("*"))
    total = _ingest_paths([p for p in paths if p.is_file()], index, chunker)
    typer.echo(f"Total chunks: {total}")


@app.command("discover-crossref")
def discover_crossref(
    doi: str = typer.Argument(..., help="DOI or https://doi.org/... URL"),
) -> None:
    """Fetch Crossref metadata and print a YAML snippet for a sidecar ``metadata:`` block."""
    import yaml

    from digisearch.discovery.crossref import fetch_crossref_work, work_to_evidence_metadata

    msg = fetch_crossref_work(doi)
    meta = work_to_evidence_metadata(msg)
    typer.echo(yaml.safe_dump({"metadata": meta}, default_flow_style=False, allow_unicode=True))


@app.command()
def query(
    index: str = typer.Option("default", "--index", "-i"),
    text: str = typer.Option(..., "--text", "-t"),
    mode: str = typer.Option("hybrid", "--mode", "-m"),
    top_k: int = typer.Option(10, "--top-k", "-k"),
) -> None:
    """Run a search query."""
    from digisearch.core.models import Query
    from digisearch.search._stub import query_index

    q = Query(text=text, top_k=top_k, mode=mode)
    response = query_index(q, index_name=index)
    for i, r in enumerate(response.results, 1):
        typer.echo(f"[{i}] score={r.score:.2f} {r.chunk.content[:200]}...")


@app.command()
def serve(
    config: Path | None = typer.Option(None, "--config", "-c"),
    port: int = typer.Option(8002, "--port", "-p"),
) -> None:
    """Start HTTP API server."""
    import uvicorn

    uvicorn.run("digisearch.server:app", host="0.0.0.0", port=port)


@app.command()
def mcp(
    config: Path | None = typer.Option(None, "--config", "-c"),
    port: int = typer.Option(8765, "--port", "-p"),
) -> None:
    """Start MCP server."""
    from digisearch.mcp_server import run_mcp

    run_mcp(port=port)


index_app = typer.Typer(help="Index operations")


@index_app.command("build")
def index_build(
    config: Path = typer.Option(..., "--config", "-c"),
) -> None:
    """Build or re-index from config."""
    typer.echo("Index build: use ingest to add documents to indexes")


@index_app.command("inspect")
def index_inspect(
    index: str = typer.Option("default", "--index", "-i"),
) -> None:
    """Inspect an index."""
    from digisearch.search._stub import get_stub_index

    idx = get_stub_index()
    typer.echo(f"Indexes: {list(idx.keys())}")
    if index in idx:
        typer.echo(f"  {index}: {len(idx[index])} chunks")


app.add_typer(index_app, name="index")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
