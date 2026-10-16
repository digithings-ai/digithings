"""Migrate a pre-spec ``config.yaml`` to a v1alpha1 ``digiproject.yaml``.

Applies the field renames and section-nesting changes documented in the migration
table of ``docs/spec/project-spec-v1alpha1.md``. Unknown top-level keys are surfaced
to stderr as ``UserWarning`` rather than silently dropped, so migration reports are
auditable. The resulting structure is re-validated via
:mod:`digigraph.project_validate` before the file is written — migrate + validate
stay in lockstep.

Used by the ``digi project migrate`` CLI; callable as a library for programmatic use.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from digigraph.project_validate import ValidationReport, validate_project_file

# Top-level keys that v1alpha1 recognises (in the schema). Anything else is either
# migrated below or flagged as unknown.
_KNOWN_V1ALPHA1_TOP_LEVEL: frozenset[str] = frozenset(
    {"project", "agents", "run_data_dir", "indexes_dir", "mcp", "services"}
)

# Legacy top-level keys that migrate into the v1alpha1 shape. Their handling is
# explicit (see :func:`migrate_mapping`), so we don't warn on them.
_LEGACY_HANDLED_TOP_LEVEL: frozenset[str] = frozenset({"run_storage", "graph", "indexes"})


@dataclass
class MigrationReport:
    """Outcome of a migration run. ``warnings`` captures unknown/dropped keys."""

    warnings: list[str] = field(default_factory=list)

    def render(self) -> str:
        if not self.warnings:
            return "migrated cleanly"
        lines = [f"migrated with {len(self.warnings)} warning(s):"]
        for w in self.warnings:
            lines.append(f"  - {w}")
        return "\n".join(lines)


def migrate_mapping(data: dict[str, Any]) -> tuple[dict[str, Any], MigrationReport]:
    """Apply legacy→v1alpha1 migrations in-memory.

    Returns the migrated mapping alongside a :class:`MigrationReport`. Emits a
    ``UserWarning`` for every unknown top-level key so the message surfaces on
    stderr when the caller does not capture warnings.
    """
    report = MigrationReport()
    out: dict[str, Any] = {}

    # Preserve passthrough sections/fields verbatim when present.
    for key in ("project", "agents", "mcp", "services"):
        if key in data and isinstance(data[key], dict):
            out[key] = dict(data[key])

    # run_data_dir: explicit field wins; else lift run_storage.dir.
    if "run_data_dir" in data:
        out["run_data_dir"] = data["run_data_dir"]
    elif isinstance(data.get("run_storage"), dict) and "dir" in data["run_storage"]:
        out["run_data_dir"] = data["run_storage"]["dir"]
        extra = {k: v for k, v in data["run_storage"].items() if k != "dir"}
        if extra:
            msg = (
                f"run_storage subkeys dropped (not in v1alpha1): {sorted(extra)}. "
                "Only 'dir' is migrated (→ run_data_dir)."
            )
            report.warnings.append(msg)
            warnings.warn(msg, UserWarning, stacklevel=2)

    if "indexes_dir" in data:
        out["indexes_dir"] = data["indexes_dir"]

    # graph.workflow_profile → agents.workflow_profile (agents wins if both set).
    graph_cfg = data.get("graph")
    if isinstance(graph_cfg, dict):
        wp = graph_cfg.get("workflow_profile")
        if wp is not None:
            agents_out = out.setdefault("agents", {})
            if "workflow_profile" not in agents_out:
                agents_out["workflow_profile"] = wp
        extra = {k: v for k, v in graph_cfg.items() if k != "workflow_profile"}
        if extra:
            msg = (
                f"graph subkeys dropped (not in v1alpha1): {sorted(extra)}. "
                "Only 'workflow_profile' is migrated (→ agents.workflow_profile)."
            )
            report.warnings.append(msg)
            warnings.warn(msg, UserWarning, stacklevel=2)

    # Legacy top-level `indexes:` list has no v1alpha1 equivalent — indexes are now
    # discovered from `indexes_dir`. Flag it so the user knows to migrate manually.
    if "indexes" in data:
        msg = (
            "Top-level 'indexes' list is not part of v1alpha1 — use 'indexes_dir' "
            "pointing at a directory of per-index YAML files instead. Original value "
            "dropped; migrate each entry into its own file under that directory."
        )
        report.warnings.append(msg)
        warnings.warn(msg, UserWarning, stacklevel=2)

    # Unknown top-level keys → warn and drop.
    for key in data:
        if key in _KNOWN_V1ALPHA1_TOP_LEVEL or key in _LEGACY_HANDLED_TOP_LEVEL:
            continue
        msg = f"unknown top-level key '{key}' has no v1alpha1 mapping; dropped."
        report.warnings.append(msg)
        warnings.warn(msg, UserWarning, stacklevel=2)

    return out, report


def migrate_project_file(
    src: str | Path,
    dest: str | Path | None = None,
    *,
    force: bool = False,
) -> tuple[Path, MigrationReport, ValidationReport]:
    """Migrate ``src`` to ``dest`` (default: ``digiproject.yaml`` next to src).

    Raises :class:`FileNotFoundError`, :class:`FileExistsError`, or
    :class:`ValueError` on failure. Returns the destination path, the migration
    report, and the final validation report (which will be ``ok`` — otherwise a
    :class:`ValueError` is raised before any write).
    """
    src_path = Path(src)
    if not src_path.exists():
        raise FileNotFoundError(f"source config not found: {src_path}")

    dest_path = Path(dest) if dest else src_path.parent / "digiproject.yaml"
    # Resolve for comparison (handle relative equivalence).
    if dest_path.resolve() == src_path.resolve() and not force:
        raise FileExistsError(f"refusing to overwrite source file {src_path} without --force")
    if dest_path.exists() and not force:
        raise FileExistsError(f"destination {dest_path} already exists; pass --force to overwrite")

    raw = src_path.read_text()
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"cannot parse YAML at {src_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(
            f"top-level YAML at {src_path} must be a mapping (got {type(data).__name__})"
        )

    migrated, mig_report = migrate_mapping(data)

    # Write to a temp file first, validate that, then move into place. Keeps the
    # destination untouched on validation failure.
    tmp_path = dest_path.with_suffix(dest_path.suffix + ".tmp")
    tmp_path.write_text(yaml.safe_dump(migrated, sort_keys=False, default_flow_style=False))
    try:
        val_report = validate_project_file(tmp_path)
        if not val_report.ok:
            raise ValueError(f"migrated output failed validation:\n{val_report.render()}")
        tmp_path.replace(dest_path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass

    return dest_path, mig_report, val_report
