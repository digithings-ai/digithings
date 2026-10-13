#!/usr/bin/env python3
"""Derive the D1 (SQLite) authz policy table from the Postgres RLS migrations.

Every ``CREATE POLICY ... USING (...)`` in ``digiquant/supabase/migrations`` is
classified into one of a small number of *predicate classes*, and the resulting
``table -> class`` table is emitted as a generated Python module. The Worker
authz module (``d1_authz.py``) implements each class; this generator guarantees
no policy is silently unported, because a policy whose class cannot be decided
is a hard error rather than a silent omission.

The raw ``USING`` bodies differ only by cosmetic spelling -- ``auth.uid()`` vs
``(SELECT auth.uid())``, repeated ``OR`` terms, ``::uuid`` casts. Those are
normalised away before classification, so the same rule written twice in two
migrations lands in the same class.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
OUTPUT_PATH = REPO_ROOT / "digiquant" / "src" / "digiquant" / "d1_authz_policies.py"

# The predicate classes d1_authz.py knows how to evaluate. A policy that
# classifies as anything else aborts the generator.
CLASSES = (
    "PUBLIC",  # USING (true) -- readable by any authenticated caller
    "MEMBER_SELF",  # USING (user_id = auth.uid())
    "OWN_WORKSPACE",  # workspace_id IN (<my workspace memberships>)
    "OWN_OR_SYSTEM",  # own memberships OR the house/system workspace
    "SYSTEM_ONLY",  # the house/system workspace and nothing else
    "WORKSPACES_ROW",  # workspaces.id IN (<my memberships>) OR type = 'system'
)

# Postgres permissive policies are OR-ed together, so a table carrying several
# policies has the UNION of their predicates as its effective predicate. The
# Worker must therefore take the MOST PERMISSIVE class a table was ever given:
# a later migration that loosens a policy widens access, and keeping the first
# (or narrowest) class seen would silently under-grant.
# `position_events` is the concrete case: it has both SYSTEM_ONLY and
# OWN_OR_SYSTEM policies, and OWN_OR_SYSTEM is the union of the two.
_PRIVILEGE = {
    "MEMBER_SELF": 0,
    "SYSTEM_ONLY": 1,
    "OWN_WORKSPACE": 2,
    "WORKSPACES_ROW": 3,
    "OWN_OR_SYSTEM": 4,
    "PUBLIC": 5,
}

CREATE_POLICY_RE = re.compile(
    r"CREATE\s+POLICY\s+\"?([A-Za-z0-9_]+)\"?\s+ON\s+(?:public\.)?([a-z0-9_]+)"
    # [^;] is load-bearing: a backward window of N characters can contain the
    # PREVIOUS policy's `FOR ... TO anon` clause, which silently mis-classified
    # three authenticated `USING (true)` policies as anon. Bounded to the
    # statement instead.
    r"(?P<head>[^;]*?)\bUSING\s*\(",
    re.IGNORECASE | re.DOTALL,
)
# Commands this generator understands. `FOR SELECT TO authenticated` is the shape
# the tenant scoping depends on; anything else is reported rather than guessed.
COMMAND_RE = re.compile(r"\bFOR\s+(SELECT|INSERT|UPDATE|DELETE)\b", re.IGNORECASE)
# Capture the role list directly rather than trying to terminate it on
# WITH/USING/CHECK: `head` no longer contains the USING keyword, so a delimiter
# based on it silently stopped matching -- and an unmatched role means the anon
# filter below never fires, which would silently drop every anon policy into the
# Worker table instead of excluding it.
ROLE_RE = re.compile(r"\bTO\s+([a-z_]+(?:\s*,\s*[a-z_]+)*)", re.IGNORECASE)


def strip_comments(sql: str) -> str:
    """Remove ``--`` line comments and ``/* */`` blocks.

    Required: an unstripped comment mentioning ``RAISE EXCEPTION`` or a function
    name otherwise becomes a phantom policy, and a comment holding ``auth.uid()``
    makes a public policy look tenant-scoped.
    """
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", " ", sql)


def split_top_level(body: str) -> list[str]:
    """Split on top-level ``OR``, ignoring anything inside parentheses."""
    parts, depth, buf = [], 0, []
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if depth == 0 and body[i : i + 4].upper() == " OR ":
            parts.append("".join(buf))
            buf = []
            i += 4
            continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


def normalise(expr: str) -> str:
    """Canonicalise cosmetic spelling so one rule written twice is one term."""
    e = expr
    e = re.sub(r"\(\s*SELECT\s+auth\.uid\(\)\s*\)", "auth.uid()", e, flags=re.I)
    e = e.replace("::uuid", "").replace("::text", "")
    e = re.sub(r"\s+", " ", e).strip().rstrip(";").strip()
    return e


def classify(using_body: str) -> str:
    """Map a Postgres ``USING`` expression to one of :data:`CLASSES`."""
    body = normalise(using_body)
    if body.lower() == "true":
        return "PUBLIC"

    terms = [normalise(t) for t in split_top_level(body)]
    # A repeated term is still one term: `documents` carries
    # `workspace_id = SYSTEM OR workspace_id = SYSTEM OR <memberships>`.
    unique = []
    for t in terms:
        if t not in unique:
            unique.append(t)

    is_member = any(re.fullmatch(r"user_id = auth\.uid\(\)", t, re.I) for t in unique)
    is_memberships = any(
        re.fullmatch(
            r"workspace_id IN \(\s*SELECT workspace_id FROM (?:public\.)?"
            r"workspace_members WHERE user_id = auth\.uid\(\)\s*\)",
            t,
            re.I,
        )
        for t in unique
    )
    is_system_ws = any(
        re.fullmatch(r"workspace_id = '[0-9a-f-]{36}'", t, re.I) for t in unique
    )
    is_workspaces_row = any(
        re.fullmatch(r"id IN \(\s*SELECT workspace_id FROM (?:public\.)?"
        r"workspace_members WHERE user_id = auth\.uid\(\)\s*\)", t, re.I)
        for t in unique
    )
    is_system_type = any(re.fullmatch(r"type = 'system'", t, re.I) for t in unique)

    if is_member and len(unique) == 1:
        return "MEMBER_SELF"
    if is_workspaces_row and is_system_type:
        return "WORKSPACES_ROW"
    if is_memberships and is_system_ws:
        return "OWN_OR_SYSTEM"
    if is_memberships and not is_system_ws:
        return "OWN_WORKSPACE"
    if is_system_ws and not is_memberships:
        return "SYSTEM_ONLY"
    raise ValueError(f"unclassified USING expression: {body}")


def parse_migrations(migrations_dir: pathlib.Path = MIGRATIONS_DIR):
    """Return ``(policies, unsupported)`` read off the migrations.

    ``policies`` maps table -> predicate class. A table keeps the most
    permissive class it was ever given, so a later migration that *loosens* a
    policy is reflected rather than hidden by the stricter one it replaced.
    """
    policies: dict[str, str] = {}
    unsupported: list[tuple[str, str, str, str]] = []

    for path in sorted(migrations_dir.glob("*.sql")):
        sql = strip_comments(path.read_text(encoding="utf-8"))

        for m in CREATE_POLICY_RE.finditer(sql):
            pol, tbl = m.group(1), m.group(2).lower()
            # Balanced scan for the end of the USING (...).
            depth, i = 1, m.end()
            while i < len(sql) and depth:
                if sql[i] == "(":
                    depth += 1
                elif sql[i] == ")":
                    depth -= 1
                i += 1
            using = sql[m.end() : i - 1]
            head = m.group("head")

            cmd = COMMAND_RE.search(head)
            roles = ROLE_RE.search(head)
            command = (cmd.group(1).upper() if cmd else "UNSPECIFIED")
            # A policy with no readable role/command is not safe to silently
            # treat as `public`: that would let an anon-scoped policy through as
            # PUBLIC. Record it as unsupported instead.
            if not cmd or not roles:
                unsupported.append(
                    (f"{pol}: could not read command/role from head {head.strip()!r}",
                     tbl, command, path.name)
                )
                continue
            role = roles.group(1).strip().lower()

            if command != "SELECT" or "anon" in [r.strip() for r in role.split(",")]:
                unsupported.append((pol, tbl, command, path.name))
                continue

            try:
                cls = classify(using)
            except ValueError as exc:
                unsupported.append((f"{pol}: {exc}", tbl, command, path.name))
                continue

            current = policies.get(tbl)
            if current is None or _PRIVILEGE[cls] > _PRIVILEGE[current]:
                policies[tbl] = cls

    return policies, unsupported


def render_module(policies: dict[str, str], unsupported, source_count: int) -> str:
    out = [
        '"""GENERATED FILE -- do not edit.',
        "",
        "Produced by ``scripts/gen_d1_authz_policies.py`` from",
        "``digiquant/supabase/migrations/*.sql``. Regenerate with the script,",
        "or run it with ``--check`` in CI to fail on drift.",
        "",
        "Maps each RLS-protected table to the predicate class that the Worker",
        "authz layer (``d1_authz.py``) evaluates for it.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "# table -> predicate class (see d1_authz.PolicyClass)",
        "POLICY_TABLE: dict[str, str] = {",
    ]
    for tbl in sorted(policies):
        out.append(f'    "{tbl}": "{policies[tbl]}",')
    out.append("}")
    out.append("")
    out.append(f"# {len(policies)} RLS-protected tables derived from {source_count} policies.")
    out.append("NON_SELECT_OR_ANON_POLICIES: tuple[str, ...] = (")
    for pol, tbl, command, migration in sorted(unsupported):
        out.append(f'    "{pol} [{command} on {tbl}, {migration}]",')
    out.append(")")
    out.append("")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="exit non-zero if the generated module is stale")
    args = ap.parse_args(argv)

    policies, unsupported = parse_migrations()
    if not policies:
        print("ERROR: no policies parsed", file=sys.stderr)
        return 2

    source_count = sum(
        len(CREATE_POLICY_RE.findall(strip_comments(p.read_text(encoding="utf-8"))))
        for p in sorted(MIGRATIONS_DIR.glob("*.sql"))
    )
    text = render_module(policies, unsupported, source_count)

    if args.check:
        if not OUTPUT_PATH.exists() or OUTPUT_PATH.read_text(encoding="utf-8") != text:
            print(f"STALE: {OUTPUT_PATH} differs from the migrations", file=sys.stderr)
            return 1
        print(f"OK: policy table is in sync ({len(policies)} tables)")
        return 0

    OUTPUT_PATH.write_text(text, encoding="utf-8")
    print(
        f"wrote {OUTPUT_PATH.name}: {len(policies)} RLS-protected tables, "
        f"{source_count} policies, {len(unsupported)} not mapped to a Worker predicate"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
