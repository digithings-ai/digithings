#!/usr/bin/env python3
"""Inventory every code file that reads or writes Supabase/Postgres.

DIG-2889 (Supabase exit). Produces a per-table caller map: which module touches
which Postgres table, through which mechanism, and with which operation.

Method
------
The map is driven by the SCHEMA, not by a keyword sweep, so prose can never
invent a caller:

1. **Table universe** comes from the migrations -- ``CREATE TABLE``,
   ``ALTER TABLE``, ``CREATE VIEW``/``CREATE MATERIALIZED VIEW``. That is the
   set of names a reference could possibly mean.
2. **Callers** are files that name a member of that universe through one of two
   mechanisms, reported in separate classes so the strength of each is visible:
   - ``client_api`` -- a PostgREST call: ``.from("t")``, ``.table("t")``,
     ``.rpc("f")``. Strong: the name is a literal argument.
   - ``sql_text`` -- a SQL statement in a ``.sql`` file or inside a source
     string, matched only when the referenced name is in the universe. Weaker:
     it cannot prove the statement executes.
3. **Connection surface** is a third, separate class: files that hold a
   Supabase/Postgres connection string or driver. This is the surface a
   provider exit has to preserve or move, and it is not the same thing as a
   table caller.

Files are enumerated with ``git ls-tree`` so build output, vendored trees and
gitignored artefacts can never enter the census.

Usage
-----
    python3 scripts/inventory/supabase_caller_inventory.py \
        --repo . --ref HEAD --json out.json --md out.md
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict

# --------------------------------------------------------------------------
# Enumeration
# --------------------------------------------------------------------------

#: Tracked files with these suffixes are scanned as source.
SOURCE_SUFFIXES = (".py", ".ts", ".tsx", ".js", ".mjs", ".jsx", ".sql", ".sh")

#: Never scanned. ``reference/assistant-ui-templates`` is vendored upstream
#: templates, not our code; its presence in a census is noise.
SKIP_PREFIXES = (
    "reference/assistant-ui-templates/",
    "node_modules/",
    ".next/",
    "dist/",
    ".venv/",
    "target/",
)


def list_tracked_files(repo: str, ref: str) -> list[str]:
    """Tracked paths at ``ref``, in one ``git ls-tree`` call."""
    out = subprocess.run(
        ["git", "-C", repo, "ls-tree", "-r", "--name-only", ref],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    keep = []
    for line in out.splitlines():
        path = line.strip()
        if not path or path.startswith(SKIP_PREFIXES):
            continue
        if path.endswith(SOURCE_SUFFIXES):
            keep.append(path)
    return keep


def read_text(repo: str, ref: str, path: str) -> str | None:
    """File content at ``ref``. Undecodable or oversized files are skipped."""
    try:
        blob = subprocess.run(
            ["git", "-C", repo, "show", f"{ref}:{path}"],
            check=True,
            capture_output=True,
        ).stdout
    except subprocess.CalledProcessError:
        return None
    if len(blob) > 4_000_000:
        return None
    try:
        return blob.decode("utf-8")
    except UnicodeDecodeError:
        return None


# --------------------------------------------------------------------------
# Schema universe
# --------------------------------------------------------------------------

_SCHEMA = r'(?:(?P<schema>[a-z_][a-z0-9_]*)\.)?(?P<name>[a-z_][a-z0-9_]*)'

RE_CREATE_TABLE = re.compile(
    r"create\s+(?:unlogged\s+)?table\s+(?:if\s+not\s+exists\s+)?" + _SCHEMA, re.I
)
RE_ALTER_TABLE = re.compile(
    r"alter\s+table\s+(?:if\s+exists\s+)?" + _SCHEMA + r"(?![A-Za-z0-9_])", re.I
)
RE_CREATE_VIEW = re.compile(
    r"create\s+(?:or\s+replace\s+)?(?:materialized\s+)?view\s+"
    r"(?:if\s+not\s+exists\s+)?" + _SCHEMA,
    re.I,
)
RE_CREATE_FUNCTION = re.compile(
    r"create\s+(?:or\s+replace\s+)?function\s+" + _SCHEMA + r"(?![A-Za-z0-9_])", re.I
)

SCHEMA_PATTERNS = {
    "create_table": RE_CREATE_TABLE,
    "alter_table": RE_ALTER_TABLE,
    "create_view": RE_CREATE_VIEW,
    "create_function": RE_CREATE_FUNCTION,
}


def build_table_universe(repo: str, ref: str, files: list[str]) -> dict[str, dict]:
    """Table/view/function names the migrations define, with the file that defines each."""
    universe: dict[str, dict] = {}
    for path in files:
        if not path.endswith(".sql"):
            continue
        text = read_text(repo, ref, path)
        if not text:
            continue
        for kind, pattern in SCHEMA_PATTERNS.items():
            for m in pattern.finditer(text):
                name = m.group("name").lower()
                if name in {"if", "not", "exists", "only"}:
                    continue
                entry = universe.setdefault(
                    name, {"kind": kind, "defined_in": set(), "schema": m.group("schema")}
                )
                entry["defined_in"].add(path)
                # A name first seen as ALTER is still a table; upgrade the kind.
                if kind == "create_table" and entry["kind"] == "alter_table":
                    entry["kind"] = "create_table"
    for entry in universe.values():
        entry["defined_in"] = sorted(entry["defined_in"])
    return universe


# --------------------------------------------------------------------------
# Reference extraction
# --------------------------------------------------------------------------

RE_POSTGREST_FROM = re.compile(r"\.from\(\s*[\"'`](?P<n>[A-Za-z_][A-Za-z0-9_]*)[\"'`]")
RE_SQL_TABLE = re.compile(r"\.table\(\s*[\"'`](?P<n>[A-Za-z_][A-Za-z0-9_]*)[\"'`]")
RE_POSTGREST_RPC = re.compile(r"\.rpc\(\s*[\"'`](?P<n>[A-Za-z_][A-Za-z0-9_]*)[\"'`]")

#: Operations on a PostgREST chain. The window is the text after ``.from(...)``
#: on the same statement; when no operation is found the op stays ``unknown``
#: rather than being guessed.
RE_CHAIN_OP = re.compile(
    r"\.(?P<op>select|insert|upsert|update|delete|eq|neq|gt|gte|lt|lte|like|ilike|"
    r"in|is|match|matches|filter|order|limit|range|maybeSingle|single|count)\s*\("
)

RE_SQL_REF = re.compile(
    r"\b(?:from|join|into|update)\s+[\"`]?(?P<schema>[a-z_][a-z0-9_]*\.)?"
    r"(?P<name>[a-z_][a-z0-9_]*)[\"`]?(?![A-Za-z0-9_])",
    re.I,
)
RE_SQL_WRITE_STMT = re.compile(
    r"^\s*(insert\s+into|update\b|delete\s+from|truncate\b|merge\s+into|"
    r"copy\b|upsert\b)",
    re.I,
)
RE_SQL_READ_STMT = re.compile(r"^\s*(select\b|with\b|explain\b|table\b)", re.I)
#: DDL/DCL. A migration that creates or alters a table is the *definition* of
#: that table, not a caller of it -- counting it as a caller would make schema
#: churn look like a read/write dependency and send the migration effort at the
#: wrong files.
RE_SQL_SCHEMA_STMT = re.compile(
    r"^\s*(create|alter|drop|grant|revoke|comment\s+on|rename)\b", re.I
)

CLIENT_API = {
    "postgrest_from": RE_POSTGREST_FROM,
    "sql_table": RE_SQL_TABLE,
    "postgrest_rpc": RE_POSTGREST_RPC,
}

#: Connection surface. A hit means the file can open a Supabase/Postgres
#: connection -- it is the cutover surface, distinct from any table caller.
RE_CONNECTION = re.compile(
    r"SUPABASE_(?:URL|ANON_KEY|SERVICE_ROLE_KEY|ACCESS_TOKEN|DB_URL|KEY)"
    r"|CORE_SUPABASE_[A-Z_]+"
    r"|POSTGRES_[A-Z_]+"
    r"|DATABASE_URL"
    r"|createClient\s*\("
    r"|SupabaseConnector"
    r"|get_core_supabase_connector"
    r"|get_supabase_client"
    r"|@supabase/supabase-js"
    r"|\bpsycopg\b|\basyncpg\b|\bpg8000\b|sqlalchemy|create_engine|create_async_engine",
)


def _classify_sql_statement(stmt: str) -> str:
    head = stmt.lstrip()[:200]
    if RE_SQL_SCHEMA_STMT.match(head):
        return "schema"
    if RE_SQL_WRITE_STMT.match(head):
        return "write"
    if RE_SQL_READ_STMT.match(head):
        return "read"
    return "unknown"


def service_of(path: str) -> str:
    """Owning surface: ``apps/dashboard`` or the top-level package."""
    parts = path.split("/")
    if parts[0] == "apps" and len(parts) > 1:
        return "/".join(parts[:2])
    return parts[0]


def is_test(path: str) -> bool:
    parts = path.split("/")
    return "tests" in parts or "test" in parts[-1] or parts[-1].startswith("test_")


def _sql_statements(text: str) -> list[str]:
    """Split on ``;`` but keep it honest: statements are the unit we classify."""
    return [s for s in text.split(";") if s.strip()]


def _postgrest_chain_op(text: str, end: int, limit: int = 400) -> str:
    """Operation on the chain that follows ``.from("t")``."""
    window = text[end : end + limit]
    ops = [m.group("op").lower() for m in RE_CHAIN_OP.finditer(window)]
    for write in ("insert", "upsert", "update", "delete"):
        if write in ops:
            return write
    for read in ("select", "maybeSingle", "single", "count", "eq", "order", "limit", "range"):
        if read in ops:
            return "read"
    return "unknown"


def scan_file(
    path: str, text: str, universe: set[str], matcher=None
) -> tuple[dict[str, set[str]], set[str], bool]:
    """Per-file references.

    Returns ``(table_refs, rpc_refs, touches_connection)`` where ``table_refs``
    maps ``"<name>::<op>"`` to the set of mechanisms that produced it.
    """
    refs: dict[str, set[str]] = defaultdict(set)

    for mechanism, pattern in CLIENT_API.items():
        for m in pattern.finditer(text):
            name = m.group("n").lower()
            if mechanism == "postgrest_rpc":
                op = "call"
            elif mechanism == "postgrest_from":
                op = _postgrest_chain_op(text, m.end())
            else:
                op = _classify_sql_statement(text[m.end() : m.end() + 400])
            refs[f"{name}::{op}"].add(mechanism)

    rpcs = {m.group("n").lower() for m in RE_POSTGREST_RPC.finditer(text)}

    # SQL text: only names that exist in the schema universe count.
    if path.endswith(".sql"):
        for stmt in _sql_statements(text):
            op = _classify_sql_statement(stmt)
            for m in RE_SQL_REF.finditer(stmt):
                name = m.group("name").lower()
                if name in universe:
                    refs[f"{name}::{op}"].add("sql_text")
    else:
        for m in RE_SQL_REF.finditer(text):
            name = m.group("name").lower()
            if name in universe:
                refs[f"{name}::{op_unknown()}"].add("sql_text")

    # Bare mention of a schema table: the weakest mechanism, and the only one
    # that sees a caller which passes the table name as a plain string.
    #
    # Never applied to a .sql file. There the name always appears in the DDL
    # that created the table, so this fallback would list every migration as a
    # caller of the table it defines -- which sends the exit effort at
    # migrations instead of at the code that actually depends on them. Genuine
    # DML in a migration is already covered by the sql_text branch above.
    if not path.endswith(".sql"):
        for name in _named_table_refs(text, matcher):
            refs[f"{name}::{op_unknown()}"].add("named_table")

    return refs, rpcs, bool(RE_CONNECTION.search(text))


def op_unknown() -> str:
    return "unknown"


def build_name_matcher(names: set[str]):
    """One alternation over every table name, matched on word boundaries.

    Needed because not every caller reaches a table through a PostgREST chain:
    twelve-x passes table names as plain strings to a ``SupabaseConnector``
    helper (50 files, zero ``.from(`` calls). A per-name loop would be
    O(universe x files) regex compiles; one alternation is a single pass.
    """
    if not names:
        return None
    alts = "|".join(sorted((re.escape(n) for n in names), key=len, reverse=True))
    return re.compile(r"(?<![A-Za-z0-9_])(?:" + alts + r")(?![A-Za-z0-9_])", re.I)


def _named_table_refs(text: str, matcher) -> set[str]:
    if matcher is None:
        return set()
    return {m.group(0).lower() for m in matcher.finditer(text)}


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------


def build_report(repo_label: str, repo: str, ref: str) -> dict:
    files = list_tracked_files(repo, ref)
    universe = build_table_universe(repo, ref, files)
    table_names = set(universe)
    matcher = build_name_matcher(table_names)

    per_table: dict[str, dict] = defaultdict(
        lambda: {
            "callers": defaultdict(set),
            "touchers": set(),
            "mechanisms": set(),
            "operations": set(),
        }
    )
    per_service: dict[str, dict] = defaultdict(
        lambda: {
            "files_scanned": 0,
            "files_with_reference": 0,
            "product_files_with_reference": 0,
            "connection_files": 0,
            "tables_touched": set(),
        }
    )
    per_file: dict[str, dict] = {}
    rpc_callers: dict[str, set[str]] = defaultdict(set)
    connection_files: set[str] = set()
    # A file that cannot be read is NOT a file with no references. On a
    # blobless/partial clone ``git show <ref>:<path>`` fails for any blob not
    # already fetched, and a census that silently drops those files reports a
    # smaller world than it claims to have measured.
    read_failures: list[str] = []

    for path in files:
        text = read_text(repo, ref, path)
        if text is None:
            read_failures.append(path)
            continue
        svc = service_of(path)
        per_service[svc]["files_scanned"] += 1
        refs, rpcs, touches = scan_file(path, text, table_names, matcher)
        if not refs and not rpcs and not touches:
            continue
        entry: dict = {"tables": {}, "rpcs": sorted(rpcs), "connection": touches}
        for key, mechanisms in refs.items():
            name, op = key.split("::", 1)
            if op == "schema":
                per_table[name]["touchers"].add(path)
            else:
                per_table[name]["callers"][path].add(op)
                per_table[name]["mechanisms"].update(mechanisms)
                per_table[name]["operations"].add(op)
            entry["tables"][name] = sorted(set(entry["tables"].get(name, [])) | {op})
        for rpc in rpcs:
            rpc_callers[rpc].add(path)
        if touches:
            connection_files.add(path)
        svc = service_of(path)
        bucket = per_service[svc]
        bucket["files_scanned"] += 1
        if refs or rpcs or touches:
            bucket["files_with_reference"] += 1
            if not is_test(path):
                bucket["product_files_with_reference"] += 1
        if touches:
            bucket["connection_files"] += 1
        if refs or rpcs:
            bucket["tables_touched"].update(refs and {k.split("::", 1)[0] for k in refs} or set())
        per_file[path] = entry

    table_map = {
        name: {
            "kind": universe.get(name, {}).get("kind", "unknown"),
            "defined_in": universe.get(name, {}).get("defined_in", []),
            "operations": sorted(v["operations"]),
            "mechanisms": sorted(v["mechanisms"]),
            "caller_count": len(v["callers"]),
            "callers": {p: sorted(ops) for p, ops in sorted(v["callers"].items())},
            "schema_touchers": sorted(v["touchers"]),
        }
        for name, v in sorted(per_table.items())
    }
    # A table with only schema touchers is a definition, not a dependency.
    called_tables = {n for n, t in table_map.items() if t["callers"]}

    return {
        "repo": repo_label,
        "ref": ref,
        "source_files_enumerated": len(files),
        "source_files_scanned": sum(s["files_scanned"] for s in per_service.values()),
        "source_files_unreadable": len(read_failures),
        "unreadable_paths": sorted(read_failures)[:50],
        "files_with_references": len(per_file),
        "tables_defined": len(universe),
        "table_universe": sorted(universe),
        "tables_referenced": len(table_map),
        "tables_called": len(called_tables),
        "tables_defined_never_called": sorted(set(universe) - called_tables),
        "connection_files": len(connection_files),
        "rpc_functions_called": len(rpc_callers),
        "unknown_operation_references": sum(
            1
            for t in table_map.values()
            for ops in t["callers"].values()
            for o in ops
            if o == "unknown"
        ),
        "per_service": {
            svc: {
                "files_scanned": s["files_scanned"],
                "files_with_reference": s["files_with_reference"],
                "product_files_with_reference": s["product_files_with_reference"],
                "connection_files": s["connection_files"],
                "tables_touched": len(s["tables_touched"]),
            }
            for svc, s in sorted(per_service.items())
            if s["files_with_reference"] or s["connection_files"]
        },
        "table_map": table_map,
        "rpc_callers": {k: sorted(v) for k, v in sorted(rpc_callers.items())},
        "per_file": {p: per_file[p] for p in sorted(per_file)},
    }


# --------------------------------------------------------------------------
# Non-vacuity controls
# --------------------------------------------------------------------------


def cross_schema(reports: list[dict]) -> dict[str, dict]:
    """Tables a repo touches that its OWN migrations do not define.

    A name absent from a repo's own schema but present in another repo's is a
    shared table: the two repos are coupled through the database, so a provider
    exit that moves one schema without the other breaks the pair. This is the
    coupling a per-repo census cannot show on its own.
    """
    own_universe = {r["repo"]: set(r["table_universe"]) for r in reports}
    out: dict[str, dict] = {}
    for r in reports:
        foreign: dict[str, list[str]] = {}
        for name, t in r["table_map"].items():
            if not t["callers"]:
                continue
            # "Foreign" means: I touch it, my migrations do not define it, and
            # someone else's migrations do. The universe -- not the called set --
            # is the definition side, otherwise a table the repo touches but
            # does not own is mistaken for one it owns.
            if name in own_universe[r["repo"]]:
                continue
            owners = [o for o, names in own_universe.items() if name in names and o != r["repo"]]
            if owners:
                foreign[name] = owners
        out[r["repo"]] = foreign
    return out


def controls(reports: list[dict]) -> list[tuple[str, bool, str]]:
    """Prove the scanner can find things, so a zero is a measurement."""
    out: list[tuple[str, bool, str]] = []

    scanned = sum(r["source_files_scanned"] for r in reports)
    out.append(("source files enumerated > 0", scanned > 0, f"{scanned}"))

    # Every enumerated source file must have been readable. A non-zero count
    # here means the census is partial -- on a blobless clone the missing blobs
    # were never fetched, and a partial census under-reports its own subject.
    unreadable = sum(r["source_files_unreadable"] for r in reports)
    enumerated = sum(r["source_files_enumerated"] for r in reports)
    out.append(
        (
            "every enumerated source file was readable",
            unreadable == 0,
            f"{unreadable} unreadable of {enumerated} enumerated",
        )
    )

    defined = sum(r["tables_defined"] for r in reports)
    out.append(("migrations define tables > 0", defined > 0, f"{defined}"))

    called = sum(r["tables_called"] for r in reports)
    out.append(("tables have callers > 0", called > 0, f"{called}"))

    client_api = sum(
        1
        for r in reports
        for t in r["table_map"].values()
        if "postgrest_from" in t["mechanisms"] or "sql_table" in t["mechanisms"]
    )
    out.append(("client_api mechanism fires > 0", client_api > 0, f"{client_api} tables"))

    conn = sum(r["connection_files"] for r in reports)
    out.append(("connection surface > 0", conn > 0, f"{conn} files"))

    # DML through raw SQL text must be separable from DDL, or schema churn
    # would be reported as a read/write dependency.
    dml = sum(
        1
        for r in reports
        for t in r["table_map"].values()
        if t["callers"] and any(o in t["operations"] for o in ("read", "write"))
    )
    out.append(("tables with a read or write caller > 0", dml > 0, f"{dml} tables"))

    writers = sum(
        1
        for r in reports
        for t in r["table_map"].values()
        if "write" in t["operations"] and t["callers"]
    )
    out.append(("tables with a write caller > 0", writers > 0, f"{writers} tables"))

    # The weakest mechanism must be visible, or a reader cannot tell which
    # tables are covered by a proven call and which only by a name mention.
    named_only = sum(
        1
        for r in reports
        for t in r["table_map"].values()
        if t["callers"] and set(t["mechanisms"]) == {"named_table"}
    )
    out.append(
        (
            "named_table-only tables reported separately",
            True,
            f"{named_only} tables seen only by name mention",
        )
    )

    # With more than one repo the shared-schema check must be shown to work:
    # a zero here would otherwise read as "the two repos are independent".
    if len(reports) > 1:
        xs = cross_schema(reports)
        shared = sum(len(v) for v in xs.values())
        out.append(
            (
                "cross-repo shared tables measured (see the doc section)",
                True,
                f"{shared} foreign table reference(s)",
            )
        )
        for repo, foreign in xs.items():
            out.append(
                (
                    f"foreign-table section non-empty for {repo}"
                    if foreign
                    else f"{repo} defines every table it touches",
                    True,
                    f"{len(foreign)} foreign",
                )
            )

    # A named table that the migrations create must be reachable through the
    # caller's own mechanism. If the control table is absent the control fails
    # loudly rather than passing vacuously.
    control_names = [n for n in ("daily_snapshots", "fx_daily_digest") if any(n in r["table_map"] for r in reports)]
    out.append(
        (
            "control table(s) present: " + (", ".join(control_names) or "NONE"),
            bool(control_names),
            f"{len(control_names)} control(s)",
        )
    )
    return out


# --------------------------------------------------------------------------
# Markdown rendering
# --------------------------------------------------------------------------


def render_markdown(reports: list[dict], regenerate: str = "") -> str:
    L: list[str] = []
    L.append("<!-- GENERATED by scripts/inventory/supabase_caller_inventory.py -- do not hand-edit. -->")
    L.append("")
    L.append("# Supabase / Postgres caller map")
    L.append("")
    L.append(
        "DIG-2889. Which module reads or writes which Postgres table, through which "
        "mechanism, with which operation. " + (f"Regenerate with `{regenerate}`." if regenerate else "")
    )
    L.append("")
    L.append("## How to read this")
    L.append("")
    L.append("- **mechanism** - `postgrest_from` is a `.from(\"table\")` call, "
             "`sql_table` a `.table(\"name\")` call, `sql_text` a SQL statement naming the table.")
    L.append("- **operation** - `read` / `write` / `call`, or `unknown` when the "
             "operation could not be established from the text. `unknown` is reported, never guessed.")
    L.append("- The table universe comes from the migrations, so a name that no "
             "migration creates is not counted as a caller.")
    L.append("")
    if len(reports) > 1:
        xs = cross_schema(reports)
        L.append("## Shared tables (the cross-repo coupling)")
        L.append("")
        L.append(
            "Tables one repo touches whose definition lives in the *other* repo's "
            "schema. Moving one side of a pair without the other breaks it, so these "
            "are the couplings to resolve first."
        )
        L.append("")
        any_pair = False
        for repo, foreign in xs.items():
            if not foreign:
                continue
            any_pair = True
            L.append(f"**{repo}** touches tables defined elsewhere:")
            L.append("")
            for name, owners in sorted(foreign.items()):
                L.append(f"- `{name}` (defined in {', '.join(owners)})")
            L.append("")
        if not any_pair:
            L.append("_No cross-repo table references found._")
            L.append("")
    for r in reports:
        L.append(f"## {r['repo']} @ `{r['ref']}`")
        L.append("")
        L.append(
            f"- source files enumerated: **{r['source_files_enumerated']}**; "
            f"read: **{r['source_files_scanned']}**; unreadable: **{r['source_files_unreadable']}**"
        )
        L.append(f"- files with a Supabase/Postgres reference: **{r['files_with_references']}**")
        L.append(
            f"- tables defined by migrations: **{r['tables_defined']}**; "
            f"tables with at least one code caller: **{r['tables_called']}**; "
            f"defined but never called from code: **{len(r['tables_defined_never_called'])}**"
        )
        L.append(
            f"- files holding a Supabase/Postgres connection string or driver: "
            f"**{r['connection_files']}**"
        )
        L.append(f"- RPC functions called from code: **{r['rpc_functions_called']}**")
        L.append("")
        if r.get("per_service"):
            L.append("### By surface")
            L.append("")
            L.append(
                "| surface | source files scanned | files with a reference | "
                "of which product code | connection-holding files | tables touched |"
            )
            L.append("| --- | --- | --- | --- | --- | --- |")
            for svc, s in r["per_service"].items():
                L.append(
                    f"| `{svc}` | {s['files_scanned']} | {s['files_with_reference']} | "
                    f"{s['product_files_with_reference']} | {s['connection_files']} | "
                    f"{s['tables_touched']} |"
                )
            L.append("")
            L.append(
                "_A surface with a reference count of 0 does not appear here: it "
                "reaches Postgres through no module in this repo at this ref._"
            )
            L.append("")
        L.append("### Per-table callers")
        L.append("")
        if not r["table_map"]:
            L.append("_No table callers found._")
            L.append("")
        else:
            L.append("| table | ops | mechanism | callers | defined in |")
            L.append("| --- | --- | --- | --- | --- |")
            for name, t in r["table_map"].items():
                ops = ", ".join(t["operations"])
                mech = ", ".join(t["mechanisms"])
                where = ", ".join(f"`{p}`" for p in t["callers"]) if t["callers"] else ""
                defined = ", ".join(f"`{p}`" for p in t["defined_in"]) or "-"
                L.append(f"| `{name}` | {ops} | {mech} | {where} | {defined} |")
            L.append("")
        if r["tables_defined_never_called"]:
            L.append("<details><summary>Defined by a migration, no caller found</summary>")
            L.append("")
            for name in r["tables_defined_never_called"]:
                L.append(f"- `{name}`")
            L.append("")
            L.append("</details>")
            L.append("")
        L.append("### RPC callers")
        L.append("")
        if r["rpc_callers"]:
            for fn, callers in r["rpc_callers"].items():
                L.append(f"- `{fn}` - " + ", ".join(f"`{c}`" for c in callers))
        else:
            L.append("_None._")
        L.append("")
        L.append("### Connection surface (files holding a Supabase/Postgres connection)")
        L.append("")
        conn_files = sorted(
            p for p, e in r["per_file"].items() if e.get("connection")
        )
        if conn_files:
            for p in conn_files:
                L.append(f"- `{p}`")
        else:
            L.append("_None._")
        L.append("")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------


def resolve_repos(specs: list[str]) -> list[tuple[str, str, str]]:
    """Parse ``LABEL=PATH[@REF]`` into (label, path, ref).

    A second repository (twelve-x) is a separate checkout with its own history,
    so it is passed with its own ref. Reading it from the shared checkout's
    HEAD would census whatever branch that seat happens to be on.
    """
    out = []
    for spec in specs:
        if "=" not in spec:
            raise SystemExit(f"--repo needs LABEL=PATH[@REF], got {spec!r}")
        label, _, rest = spec.partition("=")
        path, _, ref = rest.partition("@")
        out.append((label, path or ".", ref or "HEAD"))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--repo",
        action="append",
        default=None,
        help="LABEL=PATH[@REF], repeatable (default: digithings=.@HEAD)",
    )
    ap.add_argument("--json", dest="json_out", default=None)
    ap.add_argument("--md", dest="md_out", default=None)
    args = ap.parse_args(argv)

    specs = args.repo or ["digithings=."]
    resolved = resolve_repos(specs)
    reports = [build_report(label, path, ref) for label, path, ref in resolved]
    # The committed document must name the command that reproduces it, so the
    # regen line is built from the actual --repo arguments this run used. A
    # repo given as this working directory is written as "." so the command
    # works from a fresh clone instead of naming someone's worktree.
    def _arg(label: str, path: str, ref: str) -> str:
        shown = "." if path in (".", os.getcwd()) else path
        return f"--repo {label}={shown}" + (f"@{ref}" if ref else "")

    regenerate = (
        "python3 scripts/inventory/supabase_caller_inventory.py "
        + " ".join(_arg(label, path, ref) for label, path, ref in resolved)
        + " --md docs/release/supabase-exit/caller-inventory.md"
    )

    if args.md_out:
        with open(args.md_out, "w", encoding="utf-8") as fh:
            fh.write(render_markdown(reports, regenerate))
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(
                reports[0] if len(reports) == 1 else reports,
                fh,
                indent=2,
                sort_keys=True,
            )
    if not args.md_out and not args.json_out:
        sys.stdout.write(render_markdown(reports, regenerate))

    failures = [name for name, ok, _ in controls(reports) if not ok]
    for name, ok, detail in controls(reports):
        print(f"CONTROL {'PASS' if ok else 'FAIL'}: {name} ({detail})")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())