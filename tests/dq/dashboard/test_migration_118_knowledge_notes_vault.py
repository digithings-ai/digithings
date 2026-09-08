"""Migration 118 — knowledge_notes vault namespace (#1142 / #3603).

Structural parse checks always run. Executable Postgres checks apply the
file with ``psql -v ON_ERROR_STOP=1 --single-transaction`` against an
ephemeral Docker Postgres (the same wrapping ``db-migrate.yml`` uses).
They skip when Docker is missing locally; they fail in CI rather than skip.
``psql``/``pg_isready`` use TCP ``127.0.0.1`` inside the container so a unix
socket that lags ``pg_isready`` cannot flake the promote job (#3594).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "digiquant" / "supabase" / "migrations"
MIGRATION = MIGRATIONS_DIR / "118_knowledge_notes_vault_namespace.sql"
PG_IMAGE = os.environ.get("DIGITHINGS_TEST_PG_IMAGE", "postgres:16-alpine")
SELF_WRAP_REGEX = re.compile(r"(^|[\s])begin[\s]*;", re.IGNORECASE)

PRE_118_TABLE = """
CREATE TABLE public.knowledge_notes (
    id            bigint generated always as identity primary key,
    slug          text not null,
    vault_path    text not null,
    title         text not null,
    note_type     text not null default 'reference',
    status        text not null default 'stub',
    tags          text[] not null default '{}',
    relevance     text[] not null default '{}',
    summary       text not null default '',
    body_markdown text not null default '',
    frontmatter   jsonb  not null default '{}'::jsonb,
    sources       jsonb  not null default '[]'::jsonb,
    wikilinks     text[] not null default '{}',
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now(),
    constraint knowledge_notes_vault_path_key unique (vault_path)
);
CREATE OR REPLACE FUNCTION public.knowledge_notes_set_updated_at()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;
CREATE TRIGGER knowledge_notes_set_updated_at
  BEFORE UPDATE ON public.knowledge_notes
  FOR EACH ROW EXECUTE FUNCTION public.knowledge_notes_set_updated_at();
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.knowledge_notes
    TO PUBLIC, anon, authenticated;
"""

DUPLICATE_STEMS = """
INSERT INTO public.knowledge_notes (slug, vault_path, title)
VALUES
    ('risk', 'concepts/risk', 'Risk in concepts'),
    ('risk', 'notes/risk', 'Risk in notes');
"""

ACL_SHIM = """
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    CREATE ROLE anon NOLOGIN NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    CREATE ROLE authenticated NOLOGIN NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    CREATE ROLE service_role NOLOGIN BYPASSRLS;
  END IF;
END $$;
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;
"""


@pytest.fixture(scope="module")
def raw() -> str:
    assert MIGRATION.is_file(), f"migration missing: {MIGRATION}"
    return MIGRATION.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sql(raw: str) -> str:
    return "\n".join(line for line in raw.splitlines() if not line.lstrip().startswith("--"))


def test_migration_is_the_only_118() -> None:
    assert sorted(MIGRATIONS_DIR.glob("118_*.sql")) == [MIGRATION]


def test_migration_is_not_self_wrapping(raw: str) -> None:
    assert not SELF_WRAP_REGEX.search(raw), (
        "db-migrate.yml would drop --single-transaction wrapping if this file "
        "matches a begin-statement (comments included)"
    )


def test_comment_on_vault_column_follows_add_column(sql: str) -> None:
    add_at = sql.lower().index("add column if not exists vault")
    comment_at = sql.lower().index("comment on column public.knowledge_notes.vault")
    assert comment_at > add_at


def test_uniqueness_is_vault_path_not_slug(sql: str) -> None:
    assert "unique (vault, vault_path)" in sql
    assert "knowledge_notes_vault_vault_path_key" in sql
    assert "drop constraint if exists knowledge_notes_vault_slug_key" in sql
    assert "unique (vault, slug)" not in sql
    assert "add constraint knowledge_notes_vault_slug_key" not in sql


def test_revokes_client_grants_and_grants_service_role(sql: str) -> None:
    assert "revoke all on table public.knowledge_notes from public, anon, authenticated" in sql
    assert (
        "grant select, insert, update, delete on table public.knowledge_notes "
        "to service_role" in sql
    )


def test_psql_and_pg_isready_use_tcp_loopback() -> None:
    argv = _psql_argv("docker", "dt-m118-x", "postgres", single_transaction=True)
    assert argv[argv.index("psql") + 1 : argv.index("psql") + 3] == ["-h", "127.0.0.1"]
    ready = _pg_isready_argv("docker", "dt-m118-x")
    assert ready[ready.index("pg_isready") + 1 : ready.index("pg_isready") + 3] == [
        "-h",
        "127.0.0.1",
    ]


def test_fresh_and_upgrade_share_updated_at_trigger(sql: str) -> None:
    assert "create or replace function public.knowledge_notes_set_updated_at()" in sql
    assert "set search_path = ''" in sql
    assert "create trigger knowledge_notes_set_updated_at" in sql
    assert "enable row level security" in sql


def _docker_available() -> str | None:
    docker = shutil.which("docker")
    if docker is None:
        return None
    probe = subprocess.run(
        [docker, "info"],
        capture_output=True,
        check=False,
        timeout=20,
    )
    return docker if probe.returncode == 0 else None


def _require_docker() -> str:
    docker = _docker_available()
    if docker is not None:
        return docker
    message = "Docker is required to execute migration 118 against Postgres"
    if os.environ.get("CI") == "true":
        pytest.fail(message)
    pytest.skip(message)


def _psql_argv(
    docker: str,
    container: str,
    database: str,
    *,
    single_transaction: bool,
) -> list[str]:
    # TCP loopback: unix sockets in postgres:alpine can lag pg_isready (#3594 flake).
    cmd = [
        docker,
        "exec",
        "-i",
        container,
        "psql",
        "-h",
        "127.0.0.1",
        "-U",
        "postgres",
        "-d",
        database,
        "-v",
        "ON_ERROR_STOP=1",
        "-q",
        "-t",
        "-A",
    ]
    if single_transaction:
        cmd.append("--single-transaction")
    return cmd


def _pg_isready_argv(docker: str, container: str) -> list[str]:
    return [docker, "exec", container, "pg_isready", "-h", "127.0.0.1", "-U", "postgres"]


def _psql(
    docker: str,
    container: str,
    database: str,
    sql_text: str,
    *,
    single_transaction: bool,
) -> str:
    cmd = _psql_argv(docker, container, database, single_transaction=single_transaction)
    last_err = ""
    for attempt in range(8):
        result = subprocess.run(
            cmd,
            input=sql_text,
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        last_err = result.stderr or result.stdout
        if "No such file or directory" in last_err or "Connection refused" in last_err:
            time.sleep(0.4)
            continue
        break
    raise AssertionError(
        f"psql failed (db={database}, single_tx={single_transaction}):\n{last_err}"
    )


@pytest.fixture(scope="module")
def pg_container() -> Iterator[tuple[str, str]]:
    docker = _require_docker()
    name = f"dt-m118-{uuid.uuid4().hex[:10]}"
    run = subprocess.run(
        [
            docker,
            "run",
            "-d",
            "--rm",
            "--name",
            name,
            "-e",
            "POSTGRES_HOST_AUTH_METHOD=trust",
            PG_IMAGE,
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if run.returncode != 0:
        detail = run.stderr.strip() or run.stdout.strip()
        message = f"could not start {PG_IMAGE}: {detail}"
        if os.environ.get("CI") == "true":
            pytest.fail(message)
        pytest.skip(message)
    try:
        deadline = time.time() + 40
        while time.time() < deadline:
            ready = subprocess.run(
                _pg_isready_argv(docker, name),
                capture_output=True,
                check=False,
                timeout=10,
            )
            if ready.returncode == 0:
                break
            time.sleep(0.4)
        else:
            pytest.fail(f"{PG_IMAGE} did not become ready")
        _psql(docker, name, "postgres", ACL_SHIM, single_transaction=True)
        yield docker, name
    finally:
        subprocess.run(
            [docker, "rm", "-f", name],
            capture_output=True,
            check=False,
            timeout=30,
        )


def _new_db(pg: tuple[str, str], suffix: str) -> str:
    docker, container = pg
    db = f"m118_{suffix}_{uuid.uuid4().hex[:8]}"
    _psql(
        docker,
        container,
        "postgres",
        f"CREATE DATABASE {db};",
        single_transaction=False,
    )
    _psql(docker, container, db, ACL_SHIM, single_transaction=True)
    return db


def _apply_118(pg: tuple[str, str], database: str) -> None:
    docker, container = pg
    _psql(
        docker,
        container,
        database,
        MIGRATION.read_text(encoding="utf-8"),
        single_transaction=True,
    )


def _scalar(pg: tuple[str, str], database: str, sql_text: str) -> str:
    docker, container = pg
    return _psql(docker, container, database, sql_text, single_transaction=False)


def test_fresh_database_applies_118(pg_container: tuple[str, str]) -> None:
    db = _new_db(pg_container, "fresh")
    _apply_118(pg_container, db)
    assert (
        _scalar(
            pg_container,
            db,
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='knowledge_notes' "
            "AND column_name='vault';",
        )
        == "1"
    )
    uniques = _scalar(
        pg_container,
        db,
        "SELECT string_agg(conname, ',' ORDER BY conname) FROM pg_constraint "
        "WHERE conrelid='public.knowledge_notes'::regclass AND contype='u';",
    )
    assert uniques == "knowledge_notes_vault_vault_path_key"
    trigger = _scalar(
        pg_container,
        db,
        "SELECT COUNT(*) FROM pg_trigger WHERE tgrelid='public.knowledge_notes'::regclass "
        "AND NOT tgisinternal AND tgname='knowledge_notes_set_updated_at';",
    )
    assert trigger == "1"


def test_pre118_duplicate_stems_apply_without_data_loss(
    pg_container: tuple[str, str],
) -> None:
    db = _new_db(pg_container, "legacy")
    docker, container = pg_container
    _psql(docker, container, db, PRE_118_TABLE + DUPLICATE_STEMS, single_transaction=True)
    _apply_118(pg_container, db)
    rows = _scalar(
        pg_container,
        db,
        "SELECT string_agg(vault_path, ',' ORDER BY vault_path) "
        "FROM public.knowledge_notes WHERE slug='risk';",
    )
    assert rows == "concepts/risk,notes/risk"
    vaults = _scalar(
        pg_container,
        db,
        "SELECT COUNT(DISTINCT vault) FROM public.knowledge_notes;",
    )
    assert vaults == "1"


def test_118_is_idempotent_on_fresh_and_legacy(pg_container: tuple[str, str]) -> None:
    for suffix, prelude in (("idemp_fresh", ""), ("idemp_legacy", PRE_118_TABLE + DUPLICATE_STEMS)):
        db = _new_db(pg_container, suffix)
        docker, container = pg_container
        if prelude:
            _psql(docker, container, db, prelude, single_transaction=True)
        _apply_118(pg_container, db)
        _apply_118(pg_container, db)
        assert _scalar(pg_container, db, "SELECT COUNT(*) FROM public.knowledge_notes;") in {
            "0",
            "2",
        }


def test_anon_cannot_read_or_mutate_even_if_rls_disabled(
    pg_container: tuple[str, str],
) -> None:
    db = _new_db(pg_container, "acl")
    docker, container = pg_container
    _psql(docker, container, db, PRE_118_TABLE + DUPLICATE_STEMS, single_transaction=True)
    _apply_118(pg_container, db)
    _psql(
        docker,
        container,
        db,
        "ALTER TABLE public.knowledge_notes DISABLE ROW LEVEL SECURITY;",
        single_transaction=False,
    )
    for role in ("anon", "authenticated"):
        for priv in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            allowed = _scalar(
                pg_container,
                db,
                f"SELECT has_table_privilege('{role}', 'public.knowledge_notes', '{priv}');",
            )
            assert allowed == "f", f"{role} still has {priv}"
    for priv in ("SELECT", "INSERT", "UPDATE", "DELETE"):
        allowed = _scalar(
            pg_container,
            db,
            f"SELECT has_table_privilege('service_role', 'public.knowledge_notes', '{priv}');",
        )
        assert allowed == "t", f"service_role missing {priv}"
    with pytest.raises(AssertionError, match="permission denied"):
        _psql(
            docker,
            container,
            db,
            "SET ROLE anon; SELECT COUNT(*) FROM public.knowledge_notes;",
            single_transaction=False,
        )


def test_updated_at_trigger_fires_after_upgrade(pg_container: tuple[str, str]) -> None:
    db = _new_db(pg_container, "trig")
    docker, container = pg_container
    _psql(docker, container, db, PRE_118_TABLE + DUPLICATE_STEMS, single_transaction=True)
    _apply_118(pg_container, db)
    _psql(
        docker,
        container,
        db,
        "SET ROLE service_role; "
        "UPDATE public.knowledge_notes "
        "SET updated_at = '2000-01-01'::timestamptz "
        "WHERE vault_path='concepts/risk';",
        single_transaction=False,
    )
    after = _scalar(
        pg_container,
        db,
        "SELECT updated_at < now() AND updated_at > '2020-01-01'::timestamptz "
        "FROM public.knowledge_notes WHERE vault_path='concepts/risk';",
    )
    assert after == "t"
