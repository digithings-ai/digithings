"""DigiProject v1alpha1 validator.

Loads a project YAML, resolves ``${VAR}`` / ``${VAR:-default}`` environment-variable
references, and validates the result against the packaged JSON Schema
(``digigraph/schemas/digiproject.v1alpha1.json``).

Used by the ``digi project validate`` CLI; callable as a library for programmatic use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

from digigraph.env_utils import resolve_env_refs
from digigraph.schemas import DIGIPROJECT_V1ALPHA1, load_schema


@dataclass
class ValidationReport:
    """Aggregate validation outcome. ``ok`` is False when any error was collected."""

    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def render(self) -> str:
        if self.ok:
            return "OK"
        lines = [f"Found {len(self.errors)} error(s):"]
        for err in self.errors:
            lines.append(f"  - {err}")
        return "\n".join(lines)


def _resolve_env_refs(
    value: Any,
    *,
    env: dict[str, str] | None = None,
    path: str = "$",
    errors: list[str] | None = None,
) -> Any:
    """Walk ``value`` resolving ``${VAR}`` / ``${VAR:-default}`` in strings.

    Appends a human-readable error to ``errors`` for each unresolved ``${VAR}``
    (no default and env unset). Returns the substituted structure.

    Delegates to :func:`digigraph.env_utils.resolve_env_refs` in tracked mode
    (``errors`` list provided).
    """
    if errors is None:
        errors = []
    return resolve_env_refs(value, env=env, errors=errors, path=path)


def _format_schema_error_path(abs_path: Any) -> str:
    parts: list[str] = ["$"]
    for seg in abs_path:
        if isinstance(seg, int):
            parts.append(f"[{seg}]")
        else:
            parts.append(f".{seg}")
    return "".join(parts)


def validate_project_file(
    path: str | Path,
    *,
    env: dict[str, str] | None = None,
) -> ValidationReport:
    """Validate a project YAML file and return a :class:`ValidationReport`."""
    report = ValidationReport()
    p = Path(path)

    if not p.exists():
        report.errors.append(f"{p}: file not found")
        return report

    try:
        raw = p.read_text()
    except OSError as exc:
        report.errors.append(f"{p}: cannot read file: {exc}")
        return report

    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        report.errors.append(f"{p}: YAML parse error: {exc}")
        return report

    if data is None:
        data = {}
    if not isinstance(data, dict):
        report.errors.append(
            f"{p}: top-level YAML document must be a mapping (got {type(data).__name__})"
        )
        return report

    env_errors: list[str] = []
    resolved = _resolve_env_refs(data, env=env, errors=env_errors)
    report.errors.extend(env_errors)

    schema = load_schema(DIGIPROJECT_V1ALPHA1)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for err in sorted(validator.iter_errors(resolved), key=lambda e: list(e.absolute_path)):
        loc = _format_schema_error_path(err.absolute_path)
        report.errors.append(f"{loc}: {err.message}")

    return report
