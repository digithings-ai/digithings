"""DigiVault CLI. Typer-based. Entry point: ``digivault``.

Operates on a vault directory passed via ``--root`` or the ``DIGIVAULT_ROOT``
environment variable.
"""

from __future__ import annotations

import os
from pathlib import Path

import typer

from digivault.vault import MANIFEST_NAME, Vault, VaultError

app = typer.Typer(help="DigiVault – Obsidian-style markdown vault management")


def _resolve_root(root: str | None) -> Path:
    chosen = (root or os.environ.get("DIGIVAULT_ROOT") or "").strip()
    if not chosen:
        typer.echo("No vault root: pass --root or set DIGIVAULT_ROOT", err=True)
        raise typer.Exit(code=2)
    return Path(chosen)


@app.command()
def init(
    root: str | None = typer.Option(None, "--root", help="Vault directory (or DIGIVAULT_ROOT)"),
) -> None:
    """Create the vault directory and a default ``.digivault.yml`` manifest."""
    path = _resolve_root(root)
    path.mkdir(parents=True, exist_ok=True)
    manifest = path / MANIFEST_NAME
    if not manifest.exists():
        manifest.write_text("required_frontmatter: []\nallow_orphans: true\n", encoding="utf-8")
        typer.echo(f"Initialized vault at {path} ({MANIFEST_NAME} written)")
    else:
        typer.echo(f"Vault already initialized at {path}")


@app.command()
def lint(
    root: str | None = typer.Option(None, "--root", help="Vault directory (or DIGIVAULT_ROOT)"),
) -> None:
    """Validate the vault; exit non-zero if any issues are found."""
    try:
        report = Vault(_resolve_root(root)).lint()
    except VaultError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    if report.ok:
        typer.echo(f"vault OK ({report.note_count} notes)")
        return
    for issue in report.issues:
        typer.echo(f"{issue.note}: {issue.kind}: {issue.message}", err=True)
    raise typer.Exit(code=1)


@app.command()
def reindex(
    root: str | None = typer.Option(None, "--root", help="Vault directory (or DIGIVAULT_ROOT)"),
) -> None:
    """Rebuild the index and report note and link counts."""
    vault = Vault(_resolve_root(root))
    notes = vault.list_notes()
    links = sum(len(n.outlinks) for n in notes)
    typer.echo(f"{len(notes)} notes, {links} wikilinks")


@app.command("new-note")
def new_note(
    name: str = typer.Argument(..., help="New note name (filename stem)"),
    title: str | None = typer.Option(None, "--title", help="Frontmatter title"),
    root: str | None = typer.Option(None, "--root", help="Vault directory (or DIGIVAULT_ROOT)"),
) -> None:
    """Create a new note in the vault."""
    try:
        fm = {"title": title} if title else {}
        note = Vault(_resolve_root(root)).create_note(name, frontmatter=fm)
    except VaultError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"created {note.rel_path}")


if __name__ == "__main__":  # pragma: no cover
    app()
