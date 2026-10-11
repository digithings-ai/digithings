"""Tests for ``scripts/snapshot.sh`` (DIG-2888, ticket 0).

Every test runs the real script with stubbed pg client tools and a stub
``boto3``, so the parts this repository owns are measured rather than asserted
about the source text: the directory layout, the SHA-256 sidecar, the
``pg_restore -l`` verification, the fail-closed exit codes, and the R2
read-back comparison.

The stubs record what they were handed. That is what makes the controls
non-vacuous: a test that only asserted "the dump file exists" would still pass
if ``pg_dump`` had never run at all.

What is NOT proven here: that PostgreSQL 17 can dump and restore these two
databases. That needs a live server and Chris holds the DSNs, so this suite
deliberately never opens a connection to anything.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "snapshot.sh"

# The password carries a "/" and an "@", which a DSN must percent-encode and the
# script must decode back. If it were passed through unparsed, or if the parsing
# silently dropped the decode, PGPASSWORD would not equal PASSWORD below and both
# the argv test and the leak test would be measuring the wrong thing.
PASSWORD = "S3cr3t/pw@x_9"
ENCODED_PASSWORD = "S3cr3t%2Fpw%40x_9"
DSN = (
    f"postgresql://snapuser:{ENCODED_PASSWORD}"
    "@db.example.invalid:6543/postgres?sslmode=require"
)
STUB_ARCHIVE = b"FAKE CUSTOM-FORMAT ARCHIVE\nrow one\nrow two\n"

STUB_LIST = """;
; Archive created at 2026-10-11 10:00:00 UTC
; dbname: postgres
;
;
; Selected TOC Entries:
;
3; 1259 16385 TABLE public checkpoint_blobs postgres
4; 1259 16386 TABLE public checkpoint_writes postgres
5; 1259 16401 SEQUENCE public checkpoint_blobs_id_seq postgres
"""

PG_DUMP_STUB = """#!/usr/bin/env bash
set -u
if [ "${1:-}" = "--version" ]; then
  echo "pg_dump (PostgreSQL) ${FAKE_PG_VERSION:-17.11}"
  exit 0
fi
out=""; prev=""
for a in "$@"; do
  if [ "$prev" = "-f" ]; then out="$a"; fi
  prev="$a"
done
[ -n "$out" ] || { echo "stub pg_dump: no -f argument" >&2; exit 64; }
: > "$STUB_DIR/argv"
for a in "$@"; do printf '%s\\n' "$a" >> "$STUB_DIR/argv"; done
for v in PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE PGSSLMODE; do
  eval "val=\\${$v:-}"
  printf '%s=%s\\n' "$v" "$val" >> "$STUB_DIR/env"
done
printf 'FAKE CALLLED %s\\n' "$(date -u +%Y%m%dT%H%M%SZ)" > "$STUB_DIR/dump_ran"
printf 'STUB ARCHIVE BYTES\\n' > "$out"
printf 'FAKE CUSTOM-FORMAT ARCHIVE\\nrow one\\nrow two\\n' >> "$out"
exit 0
"""

PG_RESTORE_STUB = """#!/usr/bin/env bash
set -u
if [ "${1:-}" = "--version" ]; then
  echo "pg_restore (PostgreSQL) ${FAKE_PG_VERSION:-17.11}"
  exit 0
fi
: > "$STUB_DIR/restore_argv"
for a in "$@"; do printf '%s\\n' "$a" >> "$STUB_DIR/restore_argv"; done
printf 'FAKE CALLLED %s\\n' "$(date -u +%Y%m%dT%H%M%SZ)" > "$STUB_DIR/restore_ran"
if [ "${FAKE_LIST_BODY:-}" = "empty" ]; then
  printf ';\\n; Archive created at 2026-10-11 10:00:00 UTC\\n;\\n;\\n; Selected TOC Entries:\\n;\\n'
  exit 0
fi
cat "$STUB_DIR/list"
exit 0
"""

FAKE_BOTO = '''"""Minimal stand-in for boto3's S3 client, logging every call."""
import json
import os


def client(service, **kwargs):
    log = os.environ["FAKE_BOTO_LOG"]
    corrupt = os.environ.get("FAKE_BOTO_CORRUPT") == "1"
    store = {}

    class Client:
        def upload_fileobj(self, fileobj, bucket, key):
            data = fileobj.read()
            store[key] = data
            with open(log, "a") as fh:
                fh.write(json.dumps({
                    "op": "put", "service": service, "bucket": bucket,
                    "key": key, "bytes": len(data),
                    "endpoint_url": kwargs.get("endpoint_url"),
                    "access_key_len": len(kwargs.get("aws_access_key_id") or ""),
                    "secret_key_len": len(kwargs.get("aws_secret_access_key") or ""),
                }) + "\\n")

        def download_fileobj(self, bucket, key, buf):
            if key not in store:
                raise KeyError("no such object: " + key)
            data = store[key]
            if corrupt:
                data = data + b"CORRUPTED-IN-TRANSIT"
            buf.write(data)
            with open(log, "a") as fh:
                fh.write(json.dumps({
                    "op": "get", "bucket": bucket, "key": key, "bytes": len(data),
                }) + "\\n")

    return Client()
'''

R2_CREDS = {
    "R2_ACCOUNT_ID": "acc0123456789",
    "R2_BUCKET": "digithings-archive",
    "R2_ACCESS_KEY_ID": "AKIAEXAMPLEEXAMPLE00",
    "R2_SECRET_ACCESS_KEY": "s3cr3taccesskeyvalue0123456789",
}


def _write_exec(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(0o755)


@pytest.fixture
def stub_bin(tmp_path: Path) -> Path:
    d = tmp_path / "pgbin"
    d.mkdir()
    _write_exec(d / "pg_dump", PG_DUMP_STUB)
    _write_exec(d / "pg_restore", PG_RESTORE_STUB)
    return d


@pytest.fixture
def stub_home(tmp_path: Path) -> Path:
    """Out dir + the directory the stubs write their recordings into."""
    home = tmp_path / "home"
    home.mkdir()
    (home / "stub").mkdir()
    (home / "stub" / "list").write_text(STUB_LIST)
    return home


@pytest.fixture
def fake_boto_dir(tmp_path: Path) -> Path:
    d = tmp_path / "fakelibs"
    d.mkdir()
    (d / "boto3.py").write_text(FAKE_BOTO)
    return d


def run_snapshot(
    tmp_path: Path,
    stub_bin: Path,
    stub_home: Path,
    fake_boto_dir: Path,
    *args: str,
    r2: bool = True,
    corrupt_r2: bool = False,
    pg_version: str = "17.11",
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    for stale in list(env):
        if stale.startswith(("R2_", "CORE_POSTGRES", "SUPABASE_DB_URL")):
            del env[stale]
    env.update(
        {
            "PATH": f"{stub_bin}:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            "SNAPSHOT_PG_BIN": str(stub_bin),
            "SNAPSHOT_OUT_DIR": str(stub_home / "Backups" / "supabase-exit"),
            "STUB_DIR": str(stub_home / "stub"),
            "FAKE_PG_VERSION": pg_version,
            "FAKE_BOTO_LOG": str(stub_home / "stub" / "r2.jsonl"),
            "PYTHONPATH": str(fake_boto_dir),
            "CORE_POSTGRES_URI": DSN,
            "SUPABASE_DB_URL": DSN,
        }
    )
    if r2:
        env.update(R2_CREDS)
    if corrupt_r2:
        env["FAKE_BOTO_CORRUPT"] = "1"
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def run_dirs(stub_home: Path) -> list[Path]:
    root = stub_home / "Backups" / "supabase-exit"
    return sorted(p for p in root.iterdir() if p.is_dir()) if root.exists() else []


def stub_argv(stub_home: Path) -> str:
    return (stub_home / "stub" / "argv").read_text()


def stub_env(stub_home: Path) -> str:
    return (stub_home / "stub" / "env").read_text()


def r2_calls(stub_home: Path) -> list[dict]:
    log = stub_home / "stub" / "r2.jsonl"
    assert log.exists(), "the R2 stage never called boto3 at all"
    return [json.loads(line) for line in log.read_text().splitlines() if line.strip()]


# --------------------------------------------------------------------------- #


def test_writes_dump_list_sha256sums_and_manifest(
    tmp_path, stub_bin, stub_home, fake_boto_dir
):
    """The happy path produces the four documented artefacts in one run dir."""
    proc = run_snapshot(tmp_path, stub_bin, stub_home, fake_boto_dir, "core")
    assert proc.returncode == 0, proc.stdout + proc.stderr

    dirs = run_dirs(stub_home)
    assert len(dirs) == 1, dirs
    run = dirs[0]
    assert sorted(p.name for p in run.iterdir()) == [
        "SHA256SUMS",
        "core.dump",
        "core.dump.list",
        "manifest.json",
    ]
    assert (run / "core.dump").read_bytes() == STUB_ARCHIVE

    # The stubs really ran — without this the whole assertion above is vacuous.
    assert (stub_home / "stub" / "dump_ran").exists()
    assert (stub_home / "stub" / "restore_ran").exists()

    sums = (run / "SHA256SUMS").read_text()
    recorded = dict(
        (name, digest)
        for digest, name in (line.split("  ", 1) for line in sums.strip().splitlines())
    )
    assert set(recorded) == {"core.dump", "core.dump.list"}
    assert recorded["core.dump"] == hashlib.sha256(STUB_ARCHIVE).hexdigest()
    assert recorded["core.dump.list"] == hashlib.sha256(STUB_LIST.encode()).hexdigest()

    manifest = json.loads((run / "manifest.json").read_text())
    assert manifest["stamp"] == run.name
    assert manifest["pg_dump_major"] == 17
    assert manifest["created_at"].endswith("Z")
    assert [d["target"] for d in manifest["databases"]] == ["core"]
    entry = manifest["databases"][0]
    assert entry["archive"]["file"] == "core.dump"
    assert entry["archive"]["format"] == "custom"
    assert entry["archive"]["bytes"] == len(STUB_ARCHIVE)
    assert entry["archive"]["sha256"] == recorded["core.dump"]
    assert entry["table_of_contents"]["file"] == "core.dump.list"
    assert entry["table_of_contents"]["sha256"] == recorded["core.dump.list"]
    assert entry["table_of_contents"]["entries"] == len(
        [ln for ln in STUB_LIST.splitlines() if not ln.startswith(";")]
    )


def test_the_dsn_and_its_password_never_reach_the_artefacts(
    tmp_path, stub_bin, stub_home, fake_boto_dir
):
    """The URL is consumed, not archived. The password is the load-bearing half."""
    proc = run_snapshot(tmp_path, stub_bin, stub_home, fake_boto_dir, "core")
    assert proc.returncode == 0, proc.stdout + proc.stderr

    run = run_dirs(stub_home)[0]
    leaked = [
        p.name
        for p in run.iterdir()
        if PASSWORD.encode() in p.read_bytes() or DSN.encode() in p.read_bytes()
    ]
    assert leaked == [], f"credentials reached {leaked}"

    # Non-vacuity: the script really did receive the password, so the zero above
    # is a decision and not an accident of the prompt never running.
    assert f"PGPASSWORD={PASSWORD}" in stub_env(stub_home)
    assert "db.example.invalid" in stub_env(stub_home)
    assert proc.stdout.count(PASSWORD) == 0
    assert proc.stderr.count(PASSWORD) == 0
    assert PASSWORD not in (stub_home / "stub" / "r2.jsonl").read_text()


def test_password_is_passed_out_of_band_never_in_argv(
    tmp_path, stub_bin, stub_home, fake_boto_dir
):
    """`ps` shows any user's full command line on macOS, so argv must stay clean."""
    proc = run_snapshot(tmp_path, stub_bin, stub_home, fake_boto_dir, "core")
    assert proc.returncode == 0, proc.stdout + proc.stderr

    argv = stub_argv(stub_home)
    assert PASSWORD not in argv
    assert DSN not in argv
    assert not re.search(r"(?i)postgres(ql)?://", argv), argv

    # The dump still names its database, so this is hiding nothing.
    assert "postgres" in argv.split()
    # ... and the connection variables did reach the client.
    assert "PGHOST=db.example.invalid" in stub_env(stub_home)
    assert "PGPORT=6543" in stub_env(stub_home)
    assert "PGUSER=snapuser" in stub_env(stub_home)
    assert "PGDATABASE=postgres" in stub_env(stub_home)
    assert "PGSSLMODE=require" in stub_env(stub_home)
    # The percent-encoded form must not be what reaches libpq either.
    assert ENCODED_PASSWORD not in stub_env(stub_home)


def test_pg_restore_list_is_verified_and_an_empty_one_fails(
    tmp_path, stub_bin, stub_home, fake_boto_dir
):
    """An archive pg_restore cannot enumerate is not a backup."""
    ok = run_snapshot(tmp_path, stub_bin, stub_home, fake_boto_dir, "core")
    assert ok.returncode == 0, ok.stdout + ok.stderr
    listing = (run_dirs(stub_home)[0] / "core.dump.list").read_text()
    assert "TABLE public checkpoint_blobs" in listing

    empty = run_snapshot(
        tmp_path,
        stub_bin,
        stub_home,
        fake_boto_dir,
        "core",
        extra_env={"FAKE_LIST_BODY": "empty", "SNAPSHOT_OUT_DIR": str(stub_home / "empty")},
    )
    assert empty.returncode == 1, empty.stdout + empty.stderr
    assert "no entries" in empty.stderr, empty.stderr
    # Nothing was trusted, so the run dir holds no checksum sidecar.
    empty_run = stub_home / "empty"
    assert not (empty_run / "SHA256SUMS").exists()


def test_a_pg_client_older_than_17_is_refused_before_any_dump(
    tmp_path, stub_bin, stub_home, fake_boto_dir
):
    """The host's default PATH resolves to pg_dump 16; that must not be used."""
    proc = run_snapshot(
        tmp_path,
        stub_bin,
        stub_home,
        fake_boto_dir,
        "core",
        pg_version="16.15",
        extra_env={"SNAPSHOT_OUT_DIR": str(stub_home / "old")},
    )
    assert proc.returncode == 3, proc.stdout + proc.stderr
    assert "requires 17 or newer" in proc.stderr, proc.stderr
    assert not (stub_home / "stub" / "dump_ran").exists()
    assert run_dirs(stub_home) == []
    assert not (stub_home / "old").exists() or list((stub_home / "old").iterdir()) == []


def test_missing_r2_credentials_exit_2_and_keep_the_local_snapshot(
    tmp_path, stub_bin, stub_home, fake_boto_dir
):
    """Exit 2 means "local snapshot kept, copy not made" — never "snapshot lost"."""
    proc = run_snapshot(
        tmp_path, stub_bin, stub_home, fake_boto_dir, "core", r2=False
    )
    assert proc.returncode == 2, proc.stdout + proc.stderr
    for name in ("R2_ACCOUNT_ID", "R2_BUCKET", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"):
        assert name in proc.stderr, proc.stderr
    assert "LOCAL snapshot" in proc.stderr, proc.stderr

    run = run_dirs(stub_home)[0]
    assert (run / "core.dump").read_bytes() == STUB_ARCHIVE
    assert (run / "SHA256SUMS").exists()
    assert not (stub_home / "stub" / "r2.jsonl").exists(), "boto3 ran with no creds"


def test_r2_objects_land_under_the_documented_prefix_and_are_read_back(
    tmp_path, stub_bin, stub_home, fake_boto_dir
):
    """Parity with checkpoint_archive.py: upload, then compare SHA-256 on read-back."""
    proc = run_snapshot(tmp_path, stub_bin, stub_home, fake_boto_dir, "core")
    assert proc.returncode == 0, proc.stdout + proc.stderr

    calls = r2_calls(stub_home)
    puts = [c for c in calls if c["op"] == "put"]
    gets = [c for c in calls if c["op"] == "get"]
    run = run_dirs(stub_home)[0]
    stem = f"backups/supabase-exit/{run.name}"

    assert sorted(c["key"] for c in puts) == [
        f"{stem}/SHA256SUMS",
        f"{stem}/core.dump",
        f"{stem}/core.dump.list",
        f"{stem}/manifest.json",
    ]
    assert sorted(c["key"] for c in gets) == sorted(c["key"] for c in puts)
    assert {c["bucket"] for c in puts} == {"digithings-archive"}
    assert {c["service"] for c in puts} == {"s3"}
    assert {c["endpoint_url"] for c in puts} == {
        "https://acc0123456789.r2.cloudflarestorage.com"
    }
    # Credentials are used by reference only: lengths, never the values.
    assert all(c["access_key_len"] > 0 and c["secret_key_len"] > 0 for c in puts)
    assert R2_CREDS["R2_SECRET_ACCESS_KEY"] not in proc.stdout + proc.stderr

    sizes = {c["key"]: c["bytes"] for c in gets}
    assert sizes[f"{stem}/core.dump"] == len(STUB_ARCHIVE)


def test_a_corrupted_transit_is_caught_by_the_read_back(
    tmp_path, stub_bin, stub_home, fake_boto_dir
):
    """A copy that arrives altered must fail the run, not be reported as done."""
    proc = run_snapshot(
        tmp_path,
        stub_bin,
        stub_home,
        fake_boto_dir,
        "core",
        corrupt_r2=True,
        extra_env={"SNAPSHOT_OUT_DIR": str(stub_home / "corrupt")},
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "read-back mismatch" in proc.stderr, proc.stderr
    assert (stub_home / "stub" / "dump_ran").exists(), "the local dump should still exist"


def test_all_targets_are_dumped_into_one_timestamped_directory(
    tmp_path, stub_bin, stub_home, fake_boto_dir
):
    """`all` is the default the brief describes: core and twelve-x, one run dir."""
    proc = run_snapshot(tmp_path, stub_bin, stub_home, fake_boto_dir)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    dirs = run_dirs(stub_home)
    assert len(dirs) == 1, dirs
    run = dirs[0]
    assert (run / "core.dump").exists()
    assert (run / "twelve-x.dump").exists()
    assert (run / "twelve-x.dump.list").exists()

    # One manifest for the whole run, listing both databases — not a per-target
    # file overwritten by whichever target happened to run last.
    manifest = json.loads((run / "manifest.json").read_text())
    assert [d["target"] for d in manifest["databases"]] == ["core", "twelve-x"]
    for entry in manifest["databases"]:
        assert entry["archive"]["file"] == f"{entry['target']}.dump"
        assert entry["archive"]["bytes"] == len(STUB_ARCHIVE)
    assert (run / "core.dump.list").exists()
    assert (run / "twelve-x.dump.list").exists()


def test_the_script_refuses_to_run_without_a_usable_dsn(
    tmp_path, stub_bin, stub_home, fake_boto_dir
):
    """A half-configured env must stop, not dump an empty database."""
    env = {"CORE_POSTGRES_URI": "", "SUPABASE_DB_URL": "", "PATH": "/usr/bin:/bin"}
    proc = subprocess.run(
        ["bash", str(SCRIPT), "core"],
        env={**os.environ, "PATH": env["PATH"], **env},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert not re.search(r"pg_dump ->", proc.stdout + proc.stderr)
