"""DigiSkills CLI. Typer-based. Entry point: ``digiskills``."""

from __future__ import annotations

from pathlib import Path

import typer

from digiskills.compiler import compile_skill
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

    result = compile_skill(skill_source, synthesizer=synthesizer)
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
