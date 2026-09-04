"""digisearch CLI. Typer-based. Entry point: digisearch."""

from __future__ import annotations

from pathlib import Path

import typer

app = typer.Typer(help="digisearch – RAG, document search for Digi ecosystem")


def _ingest_paths(paths: list[Path], index: str, chunker_name: str | None) -> int:
    from digisearch.pipeline.ingest import IngestError, ingest_paths

    try:
        total, results = ingest_paths(
            paths,
            index_name=index,
            chunker_name=chunker_name,
            skip_errors=True,
        )
    except IngestError as exc:
        typer.echo(f"Ingest failed: {exc.message}", err=True)
        return 0
    for result in results:
        name = Path(result.source).name if result.source else result.doc_id
        typer.echo(f"Ingested {name}: {result.chunks_created} chunks")
    return total


@app.command()
def ingest(
    index: str = typer.Option("default", "--index", "-i", help="Index name"),
    source: Path = typer.Argument(..., help="File or directory to ingest"),
    chunker: str | None = typer.Option(
        None,
        "--chunker",
        "-c",
        help="semantic | token | recursive | fixed (default: DIGISEARCH_CHUNKER or semantic)",
    ),
) -> None:
    """Ingest documents into an index (stub in-process). Loads ``{stem}.yaml`` / ``.yml`` sidecars."""
    sources = list(source.rglob("*")) if source.is_dir() else [source]
    paths = [p for p in sources if p.is_file()]
    total = _ingest_paths(paths, index, chunker)
    typer.echo(f"Total chunks: {total}")


@app.command("ingest-batch")
def ingest_batch(
    index: str = typer.Option("default", "--index", "-i", help="Index name"),
    directory: Path = typer.Argument(
        ..., help="Directory of PDFs/Markdown and optional YAML sidecars"
    ),
    chunker: str | None = typer.Option(
        None,
        "--chunker",
        "-c",
        help="semantic | token | recursive | fixed (default: DIGISEARCH_CHUNKER or semantic)",
    ),
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
