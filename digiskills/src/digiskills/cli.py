"""DigiSkills CLI. Typer-based. Entry point: ``digiskills``."""

from __future__ import annotations

from pathlib import Path

import typer

from digiskills.compiler import compile_skill
from digiskills.ingest import LocalPathCorpusBuilder
from digiskills.models import SkillSource, SourceKind
from digiskills.package import write_skill_package, write_skill_zip

app = typer.Typer(
    help="DigiSkills – compile a codebase/docs source into an installable Agent Skill"
)


@app.callback()
def _main() -> None:
    """DigiSkills – compile a codebase/docs source into an installable Agent Skill.

    Empty callback: keeps ``digiskills compile ...`` requiring the explicit
    subcommand name even while it's the only command (Typer otherwise
    collapses a single-command app so the subcommand name isn't needed) —
    stable CLI shape as more subcommands (``validate``, ``list``, ...) land.
    """


@app.command("compile")
def compile_cmd(
    source: str = typer.Argument(..., help="Local directory/file path to compile from"),
    name: str = typer.Option(..., "--name", help="Skill name (lowercase-hyphenated slug)"),
    out: Path = typer.Option(Path("."), "--out", help="Output directory for the compiled package"),
    description: str | None = typer.Option(
        None, "--description", help="Author-provided description hint"
    ),
    llm: bool = typer.Option(
        False, "--llm", help="Use DigiLLMSynthesizer for real prose (requires digiskills[llm])"
    ),
    model: str | None = typer.Option(
        None,
        "--model",
        help="Model string for --llm synthesis (default: DIGISKILLS_SYNTHESIS_MODEL env or openrouter/auto)",
    ),
    zip_output: bool = typer.Option(False, "--zip", help="Also write a <out>/<name>.zip archive"),
    max_files: int | None = typer.Option(
        None, "--max-files", help="Max files to ingest (default 500)"
    ),
    max_file_chars: int | None = typer.Option(
        None,
        "--max-file-chars",
        help="Max chars per file before truncation (default 200000). Raise for large OpenAPI specs.",
    ),
    max_total_chars: int | None = typer.Option(
        None, "--max-total-chars", help="Max chars across the whole corpus (default 2000000)"
    ),
) -> None:
    """Compile a local path into an installable Agent Skill package."""
    skill_source = SkillSource(
        kind=SourceKind.LOCAL_PATH,
        name=name,
        description_hint=description,
        local_path=Path(source),
    )

    synthesizer = None
    if llm:
        from digiskills.synthesize import DigiLLMSynthesizer

        synthesizer = DigiLLMSynthesizer(model=model)

    # Only build an explicit corpus builder when a cap is overridden — otherwise
    # let compile_skill pick the default LocalPathCorpusBuilder. Each unset cap
    # falls back to the builder's own default.
    corpus_builder = None
    if max_files is not None or max_file_chars is not None or max_total_chars is not None:
        overrides = {
            "max_files": max_files,
            "max_file_chars": max_file_chars,
            "max_total_chars": max_total_chars,
        }
        corpus_builder = LocalPathCorpusBuilder(
            **{k: v for k, v in overrides.items() if v is not None}
        )

    result = compile_skill(skill_source, corpus_builder=corpus_builder, synthesizer=synthesizer)
    for warning in result.warnings:
        typer.echo(f"warning: {warning}", err=True)

    package_dir = write_skill_package(result.package, out)
    typer.echo(f"wrote {package_dir} ({result.document_count} document(s) ingested)")

    if zip_output:
        zip_path = Path(out) / f"{name}.zip"
        write_skill_zip(result.package, zip_path)
        typer.echo(f"wrote {zip_path}")


if __name__ == "__main__":  # pragma: no cover
    app()
