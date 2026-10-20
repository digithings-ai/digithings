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
one symlink per layered file, and whose ``config.toml``, ``seed.sql``,
``roles.sql`` and ``functions/`` point at the real ones. ``dt`` runs the CLI
with ``--workdir <generated root>``, so the CLI sees the same order the other
harnesses apply while the checked-in chain keeps its layering and the
migration guard keeps rejecting a stray top-level ``*.sql``.

The CLI sorts that directory by file name, and the two layers share one
numbering space (engine holds 001..131, prod holds 002..143), so a flat
directory of canonical names would interleave the layers: prod/002 would be
applied second instead of seventy-seventh. The generated links are therefore
numbered ``001..N`` in the order the harnesses apply — engine first, then prod,
each in filename order — and the canonical name is kept in the link stem, so
``077_002_schema_hardening.sql`` points at ``prod/002_schema_hardening.sql``.
The CLI records the generated version numbers in the local database; the
canonical numbers stay in the chain and in every link target.

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
    apply harnesses use (the names are ASCII ``NNN_name.sql``).
    """
    migrations = project_dir / "migrations"
    ordered: List[Path] = []
    for layer in LAYERS:
        ordered.extend(sorted((migrations / layer).glob("*.sql"), key=lambda p: p.name))
    return ordered


def flat_name(index: int, source: Path) -> str:
    """The generated link name for the ``index``-th migration of the chain.

    ``index`` is 1-based and follows the apply order (engine first, then prod),
    so the CLI's own sort of the flat directory reproduces that order. The
    canonical name is kept in the stem, so the link still says which file it is.
    """
    return f"{index:03d}_{source.stem}.sql"


def assert_chain_is_flat_safe(project: Path) -> None:
    """Refuse a chain the flat view cannot represent faithfully.

    A stray top-level ``migrations/*.sql`` is not in either layer, so the flat
    view would silently drop it — the chain's own guard rejects it too. A name
    present in both layers would collapse into one link, dropping a migration.
    """
    migrations = project / "migrations"
    strays = sorted(p.name for p in migrations.glob("*.sql"))
    if strays:
        raise ValueError(
            "stray top-level migration file(s) in the chain: "
            + ", ".join(strays)
            + " (the chain must hold only engine/ and prod/)"
        )
    seen: dict = {}
    for source in ordered_migrations(project):
        if source.name in seen:
            raise ValueError(
                f"duplicate migration name {source.name} in {seen[source.name].parent.name}/ "
                f"and {source.parent.name}/: the flat view would drop one"
            )
        seen[source.name] = source


def _relink(link: Path, target: Path) -> None:
    """Make ``link`` a relative symlink to ``target``, replacing anything there."""
    if link.is_symlink() or link.exists():
        if link.is_dir() and not link.is_symlink():
            shutil.rmtree(link)
        else:
            link.unlink()
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(os.path.relpath(target, link.parent))


def _unlink(entry: Path) -> None:
    """Remove a generated entry, whatever it is."""
    if entry.is_symlink() or entry.is_file():
        entry.unlink()
    elif entry.is_dir():
        shutil.rmtree(entry)


def materialize(root: Optional[Path] = None, dest: Optional[Path] = None) -> Path:
    """Build the flat view and return the project root to hand to ``--workdir``.

    Idempotent: it rebuilds the generated ``migrations/`` from the layered chain
    every call, so a file that moved between layers cannot leave a stale link.
    """
    root = (root or repo_root()).resolve()
    project = root / PROJECT_REL
    if dest is None:
        dest = root / DERIVED_REL
    elif not dest.is_absolute():
        dest = root / dest
    dest = dest.resolve()

    # This function deletes entries under <dest>/supabase/migrations, so refuse
    # any destination that could be the checked-in project — including an
    # ancestor of it (`--dest digiquant` would land on the real project).
    if dest == root or dest == project or project in dest.parents or dest in project.parents:
        raise ValueError(f"refusing to materialize into {dest}: not a generated directory")
    if not project.is_dir():
        raise FileNotFoundError(f"Supabase project dir not found: {project}")
    assert_chain_is_flat_safe(project)

    supabase = dest / "supabase"
    migrations = supabase / "migrations"
    migrations.mkdir(parents=True, exist_ok=True)

    for name in LINKED:
        source = project / name
        if source.exists() or source.is_symlink():
            _relink(supabase / name, source)
        else:
            # the source is gone: drop the link so the CLI cannot read a stale file
            stale = supabase / name
            if stale.is_symlink() or stale.exists():
                _unlink(stale)

    for entry in migrations.iterdir():
        _unlink(entry)
    for index, source in enumerate(ordered_migrations(project), start=1):
        _relink(migrations / flat_name(index, source), source)

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
