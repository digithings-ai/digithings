"""DigiSearch CLI. Typer-based. Entry point: digisearch."""

from __future__ import annotations

from pathlib import Path

import typer

app = typer.Typer(help="DigiSearch – RAG, document search for Digi ecosystem")


@app.command()
def ingest(
    index: str = typer.Option("default", "--index", "-i", help="Index name"),
    source: Path = typer.Argument(..., help="File or directory to ingest"),
    chunker: str = typer.Option("recursive", "--chunker", "-c", help="recursive | fixed | sentence"),
) -> None:
    """Ingest documents into an index."""
    from digisearch.ingestion.chunkers.fixed import FixedSizeChunker
    from digisearch.ingestion.chunkers.recursive import RecursiveChunker
    from digisearch.ingestion.registry import ParserRegistry
    from digisearch.search._stub import add_chunks

    registry = ParserRegistry()
    if chunker == "recursive":
        ch = RecursiveChunker(chunk_size=512, chunk_overlap=64)
    elif chunker == "fixed":
        ch = FixedSizeChunker(chunk_size=512)
    else:
        ch = RecursiveChunker(chunk_size=512)
    sources = list(source.rglob("*")) if source.is_dir() else [source]
    total = 0
    for p in sources:
        if p.is_file() and registry.get_parser(str(p)):
            try:
                doc = registry.parse(p)
                chunks = ch.chunk(doc)
                add_chunks(index, chunks)
                total += len(chunks)
                typer.echo(f"Ingested {p.name}: {len(chunks)} chunks")
            except Exception as e:
                typer.echo(f"Skip {p}: {e}", err=True)
    typer.echo(f"Total chunks: {total}")


@app.command()
def query(
    index: str = typer.Option("default", "--index", "-i"),
    text: str = typer.Option(..., "--text", "-t"),
    mode: str = typer.Option("hybrid", "--mode", "-m"),
    top_k: int = typer.Option(10, "--top-k", "-k"),
) -> None:
    """Run a search query."""
    from digisearch.core.models import DigiQuery
    from digisearch.search._stub import query_index

    q = DigiQuery(text=text, top_k=top_k, mode=mode)
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
