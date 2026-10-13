"""Coverage and classification tests for the D1 authz policy table.

The predicate table in ``d1_authz_policies.py`` is generated from the Postgres
migrations. These tests re-derive the expectations from the migrations with a
deliberately independent parser and assert the generated table matches, so a
parsing regression in the generator cannot silently agree with itself.
"""
from __future__ import annotations

import importlib.util
import pathlib
import re

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
POLICY_MODULE = REPO_ROOT / "digiquant" / "src" / "digiquant" / "d1_authz_policies.py"
GENERATOR = REPO_ROOT / "scripts" / "gen_d1_authz_policies.py"

CLASSES = {
    "PUBLIC",
    "MEMBER_SELF",
    "OWN_WORKSPACE",
    "OWN_OR_SYSTEM",
    "SYSTEM_ONLY",
    "WORKSPACES_ROW",
}


def _load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _strip(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", " ", sql)


POLICY_HEAD_RE = re.compile(
    r"CREATE\s+POLICY\s+\"?([A-Za-z0-9_]+)\"?\s+ON\s+(?:public\.)?([a-z0-9_]+)"
    r"(?P<head>[^;]*?)\bUSING\s*\(",
    re.IGNORECASE | re.DOTALL,
)
ROLE_RE = re.compile(r"\bTO\s+([a-z_]+(?:\s*,\s*[a-z_]+)*)", re.IGNORECASE)


def _select_policies() -> list[tuple[str, str, list[str]]]:
    """Every SELECT policy as ``(policy_name, table, roles)``, parsed independently.

    Keyed per POLICY, not per table: ``daily_snapshots`` carries both an
    ``anon_read`` (anon only) and an ``authenticated_read_house_teaser``
    (authenticated), so asking "is this table anon" would condemn a table whose
    authenticated policy is correctly ported.
    """
    out = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        sql = _strip(path.read_text(encoding="utf-8"))
        for m in POLICY_HEAD_RE.finditer(sql):
            head = m.group("head")
            if not re.search(r"\bFOR\s+SELECT\b", head, re.I):
                continue
            role = ROLE_RE.search(head)
            roles = (
                [r.strip() for r in role.group(1).split(",")] if role else []
            )
            out.append((m.group(1), m.group(2).lower(), roles))
    return out


def _independent_pg_policies() -> dict[str, set[str]]:
    """table -> set of normalised USING bodies, parsed independently.

    Deliberately *not* reusing the generator's classifier: this only asserts the
    set of tenant-scoped tables and the presence of each predicate style, not
    the class assignment.
    """
    found: dict[str, set[str]] = {}
    policy_re = re.compile(
        r"CREATE\s+POLICY\s+\"?([A-Za-z0-9_]+)\"?\s+ON\s+(?:public\.)?([a-z0-9_]+)"
        r"(?P<head>[^;]*?)\bUSING\s*\(",
        re.IGNORECASE | re.DOTALL,
    )
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        sql = _strip(path.read_text(encoding="utf-8"))
        for m in policy_re.finditer(sql):
            pol, tbl, head = m.group(1), m.group(2).lower(), m.group("head")
            if "anon" in head.lower():
                continue
            if not re.search(r"\bFOR\s+SELECT\b", head, re.I):
                continue
            depth, i = 1, m.end()
            while i < len(sql) and depth:
                if sql[i] == "(":
                    depth += 1
                elif sql[i] == ")":
                    depth -= 1
                i += 1
            body = re.sub(r"\s+", " ", sql[m.end() : i - 1]).strip()
            body = re.sub(r"\(\s*SELECT\s+auth\.uid\(\)\s*\)", "auth.uid()", body, flags=re.I)
            body = body.replace("::uuid", "").replace("::text", "")
            found.setdefault(tbl, set()).add(body)
    return found


def test_policy_module_exists_and_is_non_empty():
    assert POLICY_MODULE.exists()
    mod = _load_module("d1_authz_policies", POLICY_MODULE)
    assert mod.POLICY_TABLE, "policy table parsed to zero tables"


def test_every_class_is_one_the_authz_layer_implements():
    mod = _load_module("d1_authz_policies", POLICY_MODULE)
    for table, cls in mod.POLICY_TABLE.items():
        assert cls in CLASSES, f"{table} classified as unknown class {cls!r}"


def test_tenant_scoped_tables_are_all_covered():
    """Every table carrying a non-anon SELECT policy must appear in the table."""
    mod = _load_module("d1_authz_policies", POLICY_MODULE)
    pg = _independent_pg_policies()
    missing = sorted(set(pg) - set(mod.POLICY_TABLE))
    assert not missing, f"tables with an RLS SELECT policy but no Worker predicate: {missing}"


def test_workspace_scoping_predicate_is_present():
    """The core tenant predicate must be represented by a membership-scoped class."""
    mod = _load_policy_module_safe()
    scoped = {
        t for t, c in mod.POLICY_TABLE.items() if c in {"OWN_WORKSPACE", "OWN_OR_SYSTEM"}
    }
    assert scoped, "no table classified as workspace-scoped; parser may have broken"


def test_system_workspace_branch_is_only_on_tables_that_had_it():
    """A table may only be OWN_OR_SYSTEM if some PG policy granted the system branch."""
    mod = _load_policy_module_safe()
    pg = _independent_pg_policies()
    for table, cls in mod.POLICY_TABLE.items():
        if cls != "OWN_OR_SYSTEM":
            continue
        bodies = " ".join(pg.get(table, ()))
        assert "type = 'system'" in bodies or re.search(
            r"workspace_id = '[0-9a-f-]{36}'", bodies, re.I
        ), f"{table} classified OWN_OR_SYSTEM but no system-workspace branch in its policies"


def test_generated_module_is_in_sync_with_migrations():
    gen = _load_module("gen_d1_authz", GENERATOR)
    mod = _load_module("d1_authz_policies_sync", POLICY_MODULE)
    policies, unsupported = gen.parse_migrations()
    assert policies == mod.POLICY_TABLE, "generated policy table is stale; run the generator"
    # Every unported policy must be excluded because it names the anon role in its
    # TO clause -- not merely because its name happens to contain "anon".
    # `prices_live_public_read` is TO anon, authenticated: excluded correctly,
    # excluded for a role reason. Assert the reason is a role, by re-parsing.
    anon_excluded = 0
    for label, tbl, _cmd, _mig in unsupported:
        if "could not read" in label:
            continue
        assert _policy_is_anon(tbl), f"non-anon policy not ported: {label} ({tbl})"
        anon_excluded += 1
    assert anon_excluded, "expected at least one anon-excluded policy"


def _policy_is_anon(table: str) -> bool:
    """True if every SELECT policy on ``table`` includes the anon role."""
    roles_seen = 0
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        sql = _strip(path.read_text(encoding="utf-8"))
        for m in re.finditer(
            r"CREATE\s+POLICY\s+\"?[A-Za-z0-9_]+\"?\s+ON\s+(?:public\.)?"
            + re.escape(table)
            + r"(?P<head>[^;]*?)\bUSING\s*\(",
            sql,
            re.I | re.S,
        ):
            role = re.search(r"\bTO\s+([a-z_]+(?:\s*,\s*[a-z_]+)*)", m.group("head"), re.I)
            if not role:
                continue
            if not re.search(r"\bFOR\s+SELECT\b", m.group("head"), re.I):
                continue
            roles_seen += 1
            if "anon" not in [r.strip() for r in role.group(1).split(",")]:
                return False
    return roles_seen > 0


def test_anon_policies_are_excluded_from_the_worker_table():
    """The anon read surface is deliberately untouched by this exit."""
    gen = _load_module("gen_d1_authz_anon", GENERATOR)
    _policies, unsupported = gen.parse_migrations()
    anon = [u for u in unsupported if "anon" in u[0].lower()]
    assert anon, "expected anon policies to be present and excluded"
    mod = _load_policy_module_safe()
    # prices_live_public_read is TO anon, authenticated -- it must not appear.
    assert "prices_live" not in mod.POLICY_TABLE


def _load_policy_module_safe():
    return _load_module("d1_authz_policies_safe", POLICY_MODULE)
