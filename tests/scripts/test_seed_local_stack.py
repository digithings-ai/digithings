"""Contract tests for the synthetic local-stack seed (DIG-2774, plan section 5).

The suite is written to be falsifiable. Two properties carry most of the
weight and both have an explicit non-vacuity control:

* **Deterministic** — the same ``--seed`` reproduces byte-identical objects.
* **The seed is load-bearing** — a different seed produces different bytes.
  Without this second test, a seeder that ignored ``--seed`` entirely would
  pass the first one, which is the whole point of pinning ``--seed 42``.

The R2 tests assert the contract the *reader* enforces
(``apps/digithings-stack-cloudflare/src/market-data.ts``): a manifest at
``market-data/manifest.json``, per-ticker ``object`` + ``sha256`` entries
under ``market-data/price/``, sha256 matching the object bytes, and parquet
that yields the ``date``/``ticker``/``close`` columns the reader projects.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.seed.deterministic import (  # noqa: E402
    DEFAULT_SEED,
    LOCAL_GUARDS,
    ProductionTargetError,
    digest,
    require_local,
    require_local_database,
    rng_for,
    stable_uuid,
    synthetic_ohlc,
)
from scripts.seed.portfolio import (  # noqa: E402
    BRIEF_DOC_TYPE,
    DEMO_USERS,
    DEMO_WORKSPACES,
    brief_documents,
    user_id,
    workspace_id,
)

pytestmark = pytest.mark.unit

SEED_SQL = REPO_ROOT / "digiquant" / "supabase" / "seed.sql"

#: Migration 096 already seeds these two under its own deterministic ids.
#: The seed must never insert them, or it would fight the migration.
MIGRATION_SEEDED_IDS = (
    "1105372f-4109-5815-be5a-21091ccfc8ad",  # system
    "6b753576-ced9-5319-9bfa-c5d0aacd9319",  # house
)


# --------------------------------------------------------------- determinism


def test_same_seed_reproduces_identical_briefs():
    first = brief_documents(seed=42)
    second = brief_documents(seed=42)
    assert first == second
    assert digest(json.dumps(first, sort_keys=True)) == digest(json.dumps(second, sort_keys=True))


def test_seed_value_is_load_bearing_not_decorative():
    """Non-vacuity control for the determinism test above.

    If ``--seed`` were ignored, the two briefs would be equal here too and
    the determinism test would pass while proving nothing.
    """
    assert brief_documents(seed=42) != brief_documents(seed=43)
    assert synthetic_ohlc("SPY", days=5, seed=42) != synthetic_ohlc("SPY", days=5, seed=43)


def test_ohlc_shape_is_what_the_parquet_encoder_expects():
    rows = synthetic_ohlc("SPY", days=25, seed=DEFAULT_SEED)
    assert len(rows) == 25
    for row in rows:
        assert set(row) == {"date", "ticker", "open", "high", "low", "close", "volume"}
        assert row["ticker"] == "SPY"
        assert row["high"] >= max(row["open"], row["close"])
        assert row["low"] <= min(row["open"], row["close"])
        assert row["volume"] > 0


def test_rng_streams_are_independent_per_topic():
    """Adding a ticker must not perturb an unrelated seeder's values."""
    assert rng_for(42, "ohlc", "SPY").random() == rng_for(42, "ohlc", "SPY").random()
    assert rng_for(42, "ohlc", "SPY").random() != rng_for(42, "ohlc", "QQQ").random()


def test_stable_uuid_is_uuid5_and_deterministic():
    assert stable_uuid("workspace", 42, "seed-demo") == stable_uuid("workspace", 42, "seed-demo")
    assert stable_uuid("workspace", 42, "seed-demo") != stable_uuid("workspace", 43, "seed-demo")


# ------------------------------------------------------- no production writes


def test_require_local_refuses_a_production_target():
    with pytest.raises(ProductionTargetError):
        require_local("https://db.supabase.co", what="tenant rows")


def test_require_local_allows_loopback():
    """Positive control: the guard above is not simply always raising."""
    assert require_local("http://127.0.0.1:54321", what="x") == "http://127.0.0.1:54321"
    assert require_local("http://localhost:8002", what="x")


def test_the_r2_writer_hard_codes_local():
    """`r2_market.put_local` hard-codes --local in its wrangler argv."""
    src = (REPO_ROOT / "scripts" / "seed" / "r2_market.py").read_text()
    # The wrangler argv is a list literal, so the subcommand is three separate
    # tokens rather than one string.
    assert '"--local"' in src, "the R2 writer must pass --local unconditionally"
    for token in ('"r2"', '"object"', '"put"'):
        assert token in src, f"wrangler subcommand token {token} is gone"


# ------------------------------------------------------------------ R2 slice


@pytest.fixture(scope="module")
def market_objects():
    pytest.importorskip("polars", reason="parquet encoder needs polars (digiquant extra)")
    pytest.importorskip("digiquant.data.prices.r2_history", reason="digiquant src on path")
    from scripts.seed import r2_market

    return r2_market.build_market_slice(seed=DEFAULT_SEED, tickers=("SPY", "QQQ"), days=30)


def test_r2_manifest_satisfies_the_reader_contract(market_objects):
    manifest_key = "market-data/manifest.json"
    manifest_obj = next(o for o in market_objects if o.key == manifest_key)
    manifest = json.loads(manifest_obj.payload)

    assert manifest["version"] == 1
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", manifest["as_of"])
    assert manifest["datasets"], "manifest advertised no datasets"

    by_key = {o.key: o.payload for o in market_objects}
    for ticker, entry in manifest["datasets"].items():
        assert entry["object"].startswith("market-data/price/"), ticker
        assert re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]), ticker
        assert entry["object"] in by_key, (
            f"{ticker} manifest points at an object that was not written"
        )
        # The reader returns 502 on a digest mismatch; prove we would not.
        assert hashlib.sha256(by_key[entry["object"]]).hexdigest() == entry["sha256"]


def test_r2_writes_a_latest_pointer_per_ticker(market_objects):
    keys = {o.key for o in market_objects}
    for ticker in ("SPY", "QQQ"):
        assert f"market-data/price/{ticker}/latest" in keys


def test_r2_objects_are_byte_identical_across_runs():
    pytest.importorskip("polars")
    from scripts.seed import r2_market

    a = r2_market.build_market_slice(seed=DEFAULT_SEED, tickers=("SPY",), days=10)
    b = r2_market.build_market_slice(seed=DEFAULT_SEED, tickers=("SPY",), days=10)
    assert [o.key for o in a] == [o.key for o in b]
    assert [o.sha256 for o in a] == [o.sha256 for o in b]


def test_r2_parquet_yields_the_columns_the_reader_projects(market_objects):
    import io

    polars = pytest.importorskip("polars")
    manifest = json.loads(
        next(o for o in market_objects if o.key.endswith("manifest.json")).payload
    )
    by_key = {o.key: o.payload for o in market_objects}
    entry = next(iter(manifest["datasets"].values()))
    frame = polars.read_parquet(io.BytesIO(by_key[entry["object"]]))
    assert {"date", "ticker", "close"} <= set(frame.columns)
    assert frame.height == entry["rows"]


# ------------------------------------------------------------- digikey keys


def test_digikey_seed_keys_are_unique_by_label_and_carry_real_scopes():
    from scripts.seed import digikey_keys

    labels = [label for label, _ in digikey_keys.SEED_KEYS]
    assert len(labels) == len(set(labels)), "a repeated label would make idempotency ambiguous"
    assert "digisearch:ingest" in dict(digikey_keys.SEED_KEYS)["seed-ingest"]


def test_digikey_seed_skips_without_a_local_database():
    """No DIGIKEY_DATABASE_URL must mean `skipped`, never a fabricated mint."""
    from scripts.seed import digikey_keys

    results = digikey_keys.ensure_keys(
        tenant_slug="seed-demo", database_url=None, out_path=Path("/nonexistent/keys.env")
    )
    assert [r.action for r in results] == ["skipped"] * len(results)
    assert all(r.raw is None for r in results)


def test_secret_file_is_owner_readable_only(tmp_path):
    from scripts.seed import digikey_keys

    target = tmp_path / "keys.env"
    digikey_keys._write_secret_file(target, "seed-demo", {"seed-ingest": "dgk_live_example"})
    assert oct(target.stat().st_mode)[-3:] == "600"
    env = digikey_keys.secret_file_env(target)
    assert env == {"seed-ingest": "dgk_live_example"}


# ---------------------------------------------------------------- SQL seed


def test_seed_sql_exists_and_is_the_configured_seed_file():
    assert SEED_SQL.exists(), "digiquant/supabase/seed.sql is the [db.seed] sql_paths entry"
    config = (REPO_ROOT / "digiquant" / "supabase" / "config.toml").read_text()
    assert 'sql_paths = ["./seed.sql"]' in config
    seed_block = config.split("[db.seed]")[1].split("[db.")[0]
    assert "enabled = true" in seed_block, (
        "[db.seed] is still disabled, so db reset would skip the seed"
    )


def _sql_statements(text: str) -> list[str]:
    """Comment-stripped statements, split on ``;``, transaction verbs dropped.

    Splitting and then filtering for ``INSERT`` is the trap this exists to
    avoid: drop an ``ON CONFLICT`` clause and the orphaned tail becomes a
    separate fragment that no longer starts with INSERT, so a
    "every INSERT has an upsert" filter silently stops seeing it. Every
    fragment is therefore returned and classified.
    """
    stripped = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("--"))
    out = []
    for fragment in stripped.split(";"):
        body = fragment.strip()
        if not body or body.upper() in ("BEGIN", "COMMIT", "ROLLBACK"):
            continue
        out.append(body)
    return out


def test_every_seed_sql_statement_is_an_idempotent_upsert():
    statements = _sql_statements(SEED_SQL.read_text())
    assert statements, "seed.sql contains no statements"
    expected = (
        len(DEMO_WORKSPACES) + len(DEMO_WORKSPACES) * len(DEMO_USERS) + len(brief_documents())
    )
    assert len(statements) == expected, f"expected {expected} statements, found {len(statements)}"
    for statement in statements:
        assert statement.upper().startswith("INSERT INTO"), (
            f"non-INSERT statement: {statement[:90]}"
        )
        assert statement.upper().count("ON CONFLICT") == 1, f"not an upsert: {statement[:90]}"


def test_seed_sql_statement_count_matches_the_fixtures():
    """Non-vacuity control: the previous assertion is only real if it sees rows."""
    statements = _sql_statements(SEED_SQL.read_text())
    inserts = SEED_SQL.read_text().upper().count("INSERT INTO")
    assert inserts == len(statements) == 12, (inserts, len(statements))


def test_seed_sql_never_touches_the_migration_seeded_workspaces():
    body = SEED_SQL.read_text()
    for reserved in MIGRATION_SEEDED_IDS:
        assert reserved not in body, (
            f"seed.sql collides with the migration-seeded workspace {reserved}"
        )


def test_seed_sql_ids_match_the_python_derivation():
    """The SQL file and the client path must write the same rows."""
    body = SEED_SQL.read_text()
    for ws in DEMO_WORKSPACES:
        assert workspace_id(ws["slug"], seed=DEFAULT_SEED) in body, ws["slug"]
        for user in DEMO_USERS:
            assert user_id(user["local"], seed=DEFAULT_SEED) in body, user["local"]


def test_brief_doc_type_is_inside_the_schema_allow_list():
    """`chk_documents_doc_type` (migration 023) rejects anything else at INSERT."""
    migration = (
        REPO_ROOT / "digiquant" / "supabase" / "migrations" / "023_pipeline_review_doc_type.sql"
    ).read_text()
    allowed = set(re.findall(r"'([^']+)'", migration.split("doc_type IN (")[1].split(")")[0]))
    assert allowed, "failed to parse the doc_type allow-list from migration 023"
    assert BRIEF_DOC_TYPE in allowed


def test_tenant_rows_are_upsertable_on_their_natural_keys():
    from scripts.seed import tenants

    workspaces, members = tenants.rows(seed=DEFAULT_SEED)
    assert len(workspaces) == len(DEMO_WORKSPACES)
    assert len(members) == len(DEMO_WORKSPACES) * len(DEMO_USERS)
    assert len({w["id"] for w in workspaces}) == len(workspaces)
    assert all(w["slug"] not in ("system", "house") for w in workspaces)


# ------------------------------------------------------- synthetic-only rule


def test_seed_artifacts_carry_no_deliverable_email_and_no_client_data():
    corpus_dir = REPO_ROOT / "scripts" / "seed" / "data"
    text = SEED_SQL.read_text()
    for path in corpus_dir.rglob("*"):
        if path.is_file():
            text += path.read_text()
    emails = set(re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text))
    assert emails <= {"seed.digithings.local"} or all(
        e.endswith("@seed.digithings.local") for e in emails
    ), emails
    assert "synthetic" in text.lower()


def test_seed_all_reports_a_verdict_and_exits_zero_in_dry_run(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.seed.seed_all",
            "--seed",
            "42",
            "--dry-run",
            "--out-dir",
            str(tmp_path),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-800:]
    manifest = json.loads((tmp_path / "seed-manifest.json").read_text())
    assert manifest["seed"] == 42 and manifest["dry_run"] is True
    assert {s["name"] for s in manifest["steps"]} == {
        "tenants",
        "portfolio",
        "digikey",
        "r2",
        "digisearch",
        "digigraph",
    }


def test_every_seed_module_parses():
    for path in sorted((REPO_ROOT / "scripts" / "seed").glob("*.py")):
        ast.parse(path.read_text(), filename=str(path))


def _unguarded_url_params(path):
    """Return (function_name, params) for every `*_url` param used unguarded.

    A parameter counts as guarded when it is passed straight to one of
    `LOCAL_GUARDS` in the same function. Anything else that reads it is a
    write path that never asked whether the target is this machine.
    """
    tree = ast.parse(path.read_text())
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args = node.args
        params = [
            a.arg
            for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)
            if a.arg.endswith("_url")
        ]
        if not params:
            continue
        guarded = set()
        for call in ast.walk(node):
            if not isinstance(call, ast.Call):
                continue
            fn = call.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            if name in LOCAL_GUARDS and call.args and isinstance(call.args[0], ast.Name):
                guarded.add(call.args[0].id)
        used = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
        found.append((node.name, [p for p in params if p in used and p not in guarded]))
    return found


def test_every_url_taking_seeder_guards_with_require_local():
    """No function in the package may use a `*_url` without guarding it.

    This walks the whole package on purpose. An earlier version of this rule
    read one file, so a sibling module could forward a URL to a real
    deployment while the suite stayed green.
    """
    seed_dir = REPO_ROOT / "scripts" / "seed"
    modules = sorted(seed_dir.glob("*.py"))
    assert len(modules) >= 8, f"control: expected the whole package, found {len(modules)}"

    unguarded, seen = [], 0
    for path in modules:
        for func_name, offenders in _unguarded_url_params(path):
            seen += 1
            for param in offenders:
                unguarded.append(f"{path.name}::{func_name}({param})")

    # Control: the walk must actually have found something to police, or a
    # rename of every parameter would make this pass for the wrong reason.
    assert seen >= 2, f"control: only {seen} function(s) take a *_url"
    assert unguarded == [], "unguarded URL parameters: " + ", ".join(unguarded)


def test_digisearch_ingest_refuses_a_remote_search_host():
    """The concrete path a package-wide rule exists for.

    Only the search host is remote here, and the message must name it: with
    both URLs remote, dropping either one of the two guards would still raise
    and this test would stay green.
    """
    from scripts.seed import digisearch

    with pytest.raises(ProductionTargetError, match="digisearch ingest"):
        digisearch.run_ingest(
            api_key="dgk_live_example",
            digisearch_url="https://search.digithings.ai",
            digikey_url="http://127.0.0.1:8005",
            runner=lambda *a, **k: pytest.fail("must not reach the child process"),
        )


def test_digisearch_ingest_refuses_a_remote_digikey_host():
    """The token exchange is a second write path, guarded separately."""
    from scripts.seed import digisearch

    with pytest.raises(ProductionTargetError, match="digikey token exchange"):
        digisearch.run_ingest(
            api_key="dgk_live_example",
            digisearch_url="http://127.0.0.1:8002",
            digikey_url="https://key.digithings.ai",
            runner=lambda *a, **k: pytest.fail("must not reach the child process"),
        )


def test_digisearch_ingest_accepts_the_loopback_defaults():
    from scripts.seed import digisearch

    calls = []

    def fake_run(cmd, env=None, cwd=None, check=None):
        calls.append((cmd, env))
        return subprocess.CompletedProcess(cmd, 0)

    rc = digisearch.run_ingest(
        api_key="dgk_live_example",
        digisearch_url="http://127.0.0.1:8002",
        digikey_url="http://127.0.0.1:8005",
        runner=fake_run,
    )
    assert rc == 0
    assert len(calls) == 1, "the child must run exactly once for loopback URLs"
    assert calls[0][1]["DIGISEARCH_URL"] == "http://127.0.0.1:8002"


def test_require_local_database_refuses_a_remote_host():
    """A key store off this machine must fail the run, not accept the write."""
    remote = "postgresql://dk:pw@db.example:5432/digikey"

    # Control first: the guard must accept the local case, or the refusal
    # below would prove nothing about the remote one.
    assert require_local_database("postgresql://dk:pw@127.0.0.1:5432/digikey", what="k") == (
        "postgresql://dk:pw@127.0.0.1:5432/digikey"
    )
    with pytest.raises(ProductionTargetError):
        require_local_database(remote, what="digikey key rows")


def test_require_local_database_accepts_the_documented_local_file_dsn():
    """The local SQLite deployment must keep working.

    `infra/digichat-release/compose.profile-a.yml` defaults
    `DIGIKEY_DATABASE_URL` to `sqlite:////data/digikey.db`, which carries no
    host. `require_local` cannot judge that shape, which is why this guard
    exists instead of reusing the HTTP one.
    """
    dsn = "sqlite:////data/digikey.db"

    assert require_local_database(dsn, what="k") == dsn
    # Control: the HTTP guard really would refuse it, so the two guards are
    # not interchangeable and the new one is not a duplicate.
    with pytest.raises(ProductionTargetError):
        require_local(dsn, what="k")


def test_require_local_database_refuses_a_schemeless_value():
    """A bare path has no scheme, so it is refused rather than guessed at."""
    with pytest.raises(ProductionTargetError):
        require_local_database("/data/digikey.db", what="digikey key rows")


def test_ensure_keys_refuses_a_remote_database_before_writing(monkeypatch, tmp_path):
    """The guard must fire BEFORE the DSN is exported to digikey.

    Exporting first would leave `DIGIKEY_DATABASE_URL` pointing at production
    in this process even though the mint raised, so the assertion is on the
    environment and not only on the exception.
    """
    from scripts.seed import digikey_keys

    monkeypatch.delenv("DIGIKEY_DATABASE_URL", raising=False)

    with pytest.raises(ProductionTargetError):
        digikey_keys.ensure_keys(
            tenant_slug="seed",
            database_url="postgresql://dk:pw@db.example:5432/digikey",
            out_path=tmp_path / "keys.json",
        )

    assert "DIGIKEY_DATABASE_URL" not in os.environ
