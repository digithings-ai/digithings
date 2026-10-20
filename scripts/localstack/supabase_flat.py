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
import re
import shutil
import sys
from pathlib import Path
from typing import List, Mapping, Optional, Sequence

try:  # imported as part of the scripts package
    from .supabase_ports import PORT_KEYS, api_port as env_api_port, ports_for_api_port
except ImportError:  # run as a script
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from supabase_ports import PORT_KEYS, api_port as env_api_port, ports_for_api_port

#: The checked-in Supabase project dir, relative to the repository root.
PROJECT_REL = "digiquant/supabase"
#: The generated project root the CLI is pointed at with ``--workdir``.
DERIVED_REL = "digiquant/.supabase-local"
#: Apply order (D-Q6′, DIG-3694): ``engine/`` first, then ``prod/``.
LAYERS = ("engine", "prod")
#: Entries the CLI reads from ``<project>/supabase/``. ``migrations/`` is
#: handled separately. ``config.toml`` is a real, port-rewritten copy (it
#: carries the Supabase ports and the CLI has no port flags); the rest are
#: relative symlinks.
LINKED = ("config.toml", "seed.sql", "roles.sql", "functions")
#: Entries the CLI reads from the PROJECT ROOT rather than from
#: ``<project>/supabase/``. Supabase CLI 2.117.0 reads
#: ``docs/schemas/execution_policy.v1.json`` from the project root, so the
#: generated root has to carry it: the CLI resolves the workdir as the project
#: root and fails with "failed to read file" when the schema is missing.
PROJECT_ROOT_LINKED = ("docs",)

#: A ``port = <n>`` / ``shadow_port = <n>`` line in a config.toml.
_PORT_LINE = re.compile(r"^(\s*)(port|shadow_port)(\s*=\s*)(\d+)(\s*(#.*)?)?$")
#: A ``[table]`` header in a config.toml.
_TABLE_LINE = re.compile(r"^\s*\[([^\]]+)\]\s*$")


def rewrite_ports(text: str, port_map: Mapping[str, int]) -> str:
    """Rewrite the Supabase ports in a config.toml.

    Only the ``port``/``shadow_port`` keys of the tables named in ``PORT_KEYS``
    are touched, and only inside the table they belong to. Every other byte
    (comments, order, spacing) is preserved, so the generated file stays
    reviewable against the checked-in one.
    """
    by_table: dict[str, dict[str, int]] = {}
    for name, (table, key) in PORT_KEYS.items():
        if name in port_map:
            by_table.setdefault(table, {})[key] = port_map[name]

    out: list[str] = []
    table = ""
    for line in text.splitlines(keepends=True):
        stripped = line.rstrip("\n")
        header = _TABLE_LINE.match(stripped)
        if header:
            table = header.group(1).strip()
        else:
            match = _PORT_LINE.match(stripped)
            if match:
                key = match.group(2)
                port = by_table.get(table, {}).get(key)
                if port is not None:
                    ending = "\n" if line.endswith("\n") else ""
                    comment = match.group(5) or ""
                    line = f"{match.group(1)}{key}{match.group(3)}{port}{comment}{ending}"
        out.append(line)
    return "".join(out)


def write_config(target: Path, source: Path, port_map: Mapping[str, int]) -> None:
    """Write a real, port-rewritten copy of ``source`` to ``target``.

    The link that used to be here is removed BEFORE the write: a symlink would
    send the write straight into the checked-in config.toml.
    """
    _unlink(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rewrite_ports(source.read_text(), port_map))


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


def materialize(root: Optional[Path] = None, dest: Optional[Path] = None,
                api_port: Optional[int] = None) -> Path:
    """Build the flat view and return the project root to hand to ``--workdir``.

    Idempotent: it rebuilds the generated ``migrations/`` from the layered chain
    every call, so a file that moved between layers cannot leave a stale link.
    """
    root = (root or repo_root()).resolve()
    port_map = ports_for_api_port(api_port if api_port is not None else env_api_port())
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
        if name == "config.toml":
            # The config.toml carries the Supabase ports, and the CLI has no
            # port flags to override them. A symlink cannot carry an override
            # (writing through it would edit the checked-in file), so the
            # generated tree holds a real, rewritten copy.
            write_config(supabase / name, source, port_map)
            continue
        if source.exists() or source.is_symlink():
            _relink(supabase / name, source)
        else:
            # the source is gone: drop the link so the CLI cannot read a stale file
            stale = supabase / name
            if stale.is_symlink() or stale.exists():
                _unlink(stale)

    for name in PROJECT_ROOT_LINKED:
        # The CLI resolves the workdir as the project root, so a file it reads
        # from the root of the real project has to be reachable there too.
        source = project.parent / name
        if source.exists() or source.is_symlink():
            _relink(dest / name, source)
        else:
            stale = dest / name
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
    parser.add_argument(
        "--api-port", type=int, default=None,
        help="Supabase API port for the generated config.toml (default: DT_SUPABASE_PORT)",
    )
    args = parser.parse_args(argv)
    try:
        dest = materialize(args.root, args.dest, args.api_port)
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
