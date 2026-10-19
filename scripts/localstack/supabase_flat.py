#!/usr/bin/env python3
"""Materialize the layered migration chain as the flat view the Supabase CLI reads.

D-Q6′ (DIG-3694) split ``digiquant/supabase/migrations/`` into ``engine/`` (the
tables the open pipeline uses, the R0 self-host schema) and ``prod/`` (the
house-only remainder). The apply order is engine first, then prod, each in
filename order; ``scripts/self_host_migrations_check.sh`` and
``scripts/rls_proof/run.sh`` implement exactly that order.

The Supabase CLI does not. ``supabase start`` and ``supabase db reset`` read only
the top level of ``<project>/supabase/migrations`` — the CLI lists that directory
without recursing — so once the files moved into ``engine/`` and ``prod/`` a
clean bring-up applied nothing and the seed then failed on the missing
``public.workspaces`` (DIG-4449).

This module builds a generated project root whose ``supabase/migrations/`` holds
one symlink per layered file — engine first, prod second, each in filename order
— and whose ``config.toml``, ``seed.sql``, ``roles.sql`` and ``functions/`` point
at the real ones. ``dt`` runs the CLI with ``--workdir <generated root>``, so the
CLI sees the same order the other harnesses apply while the checked-in chain
keeps its layering and the migration guard keeps rejecting a stray top-level
``*.sql``.

Nothing here writes to ``digiquant/supabase/``. The generated tree is
git-ignored and safe to delete at any time.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import List, Optional, Sequence

#: The checked-in Supabase project dir, relative to the repository root.
PROJECT_REL = "digiquant/supabase"
#: The generated project root the CLI is pointed at with ``--workdir``.
DERIVED_REL = "digiquant/.supabase-local"
#: Apply order (D-Q6′, DIG-3694): ``engine/`` first, then ``prod/``.
LAYERS = ("engine", "prod")
#: Entries the CLI reads from ``<project>/supabase/`` that the generated tree
#: points at with a relative symlink. ``migrations/`` is handled separately.
LINKED = ("config.toml", "seed.sql", "roles.sql", "functions")


def repo_root() -> Path:
    """The repository root: two levels above ``scripts/localstack/``."""
    return Path(__file__).resolve().parents[2]


def ordered_migrations(project_dir: Path) -> List[Path]:
    """Every layered migration, engine first then prod, each in filename order.

    A plain filename sort within a layer is the ``LC_ALL=C`` sort the other
    apply harnesses use (the names are ASCII ``NNN_name.sql``). The numeric
    prefixes are globally unique, so the flattened view has no collisions.
    """
    migrations = project_dir / "migrations"
    ordered: List[Path] = []
    for layer in LAYERS:
        ordered.extend(sorted((migrations / layer).glob("*.sql"), key=lambda p: p.name))
    return ordered


def _relink(link: Path, target: Path) -> None:
    """Make ``link`` a relative symlink to ``target``, replacing anything there."""
    if link.is_symlink() or link.exists():
        if link.is_dir() and not link.is_symlink():
            shutil.rmtree(link)
        else:
            link.unlink()
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(os.path.relpath(target, link.parent))


def materialize(root: Optional[Path] = None, dest: Optional[Path] = None) -> Path:
    """Build the flat view and return the project root to hand to ``--workdir``.

    Idempotent: it rebuilds the generated ``migrations/`` from the layered chain
    every call, so a file that moved between layers cannot leave a stale link.
    """
    root = (root or repo_root()).resolve()
    project = root / PROJECT_REL
    dest = (dest or (root / DERIVED_REL)).resolve()

    # This function deletes entries under <dest>/supabase/migrations, so refuse
    # any destination that could be the checked-in project.
    if dest == root or dest == project or project in dest.parents:
        raise ValueError(f"refusing to materialize into {dest}: not a generated directory")
    if not project.is_dir():
        raise FileNotFoundError(f"Supabase project dir not found: {project}")

    supabase = dest / "supabase"
    migrations = supabase / "migrations"
    migrations.mkdir(parents=True, exist_ok=True)

    for name in LINKED:
        source = project / name
        if source.exists() or source.is_symlink():
            _relink(supabase / name, source)

    for entry in migrations.iterdir():
        if entry.is_symlink() or entry.is_file():
            entry.unlink()
        else:
            shutil.rmtree(entry)
    for source in ordered_migrations(project):
        _relink(migrations / source.name, source)

    return dest


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="supabase_flat", description=__doc__.splitlines()[0]
    )
    parser.add_argument(
        "--root", type=Path, default=None,
        help="repository root (default: the repo this file lives in)",
    )
    parser.add_argument(
        "--dest", type=Path, default=None,
        help=f"generated project root (default: {DERIVED_REL})",
    )
    args = parser.parse_args(argv)
    try:
        dest = materialize(args.root, args.dest)
    except (FileNotFoundError, ValueError) as exc:
        print(f"supabase-flat: {exc}", file=sys.stderr)
        return 1
    project = (args.root or repo_root()) / PROJECT_REL
    engine = len(list((project / "migrations" / "engine").glob("*.sql")))
    prod = len(list((project / "migrations" / "prod").glob("*.sql")))
    print(f"{engine + prod} migrations ({engine} engine + {prod} prod) -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
