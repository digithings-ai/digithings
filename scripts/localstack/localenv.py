"""The local stack's environment defaults.

Three things have to line up for the stack to come up beside core-local: the
Supabase ports, the keychain namespace the local material actually lives in,
and a ``.env`` docker compose can read. The compose services declare
``env_file: .env`` and compose itself needs that file present to interpolate
``${VAR}``, while the render step only ever writes ``.dev.vars``.

The root ``.env`` is the operator's file. The values they put in it - the ones
``docs/SELF_HOST.md`` 7.1 documents - survive a ``dt up``; before DIG-4662 the
file was rebuilt from the render alone and every one of them was dropped on
the next bring-up. Three sources meet in it, lowest precedence first:

1. the rendered ``.dev.vars``,
2. the operator's own values from the previous ``.env``,
3. the local overrides (the local digikey DSN, the local Supabase URL, the
   omniroute password), which always win.

Which of the first two a value came from is recorded in a managed block at the
bottom of the ``.env`` itself (digests, never values). The block travels with
the values it describes: it is written in the same atomic write, so it can
never describe a file that is no longer there. A record in a second file
could, and a stale record froze a rotated secret - the value in the ``.env``
read as the operator's and the render's new value never reached compose. With
the block in the same file the two cannot drift apart, and a value the
operator changed is still theirs.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
import sys
import tempfile
from pathlib import Path
from typing import Dict, Mapping, Optional, Tuple

try:  # imported as part of a package
    from .supabase_ports import PORT_ENV, api_port
except ImportError:  # run as a script
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from supabase_ports import PORT_ENV, api_port

#: Names the namespace the local stack works in, so a local render finds the
#: local material and not a shared one. The contract's shared namespace
#: ("digithings/") holds the digithings secrets every deployment shares; it
#: is the only namespace a shared secret is read from.
KEYCHAIN_PREFIX_ENV = "DT_SECRETS_KEYCHAIN_PREFIX"
DEFAULT_KEYCHAIN_PREFIX = "digithings-local/"

#: Points the CORE_SUPABASE_SERVICE_KEY generation at the generated workdir
#: instead of the checked-in project dir, so the value comes from the local
#: instance that is actually running.
GENERATE_CWD_ENV = "DT_GENERATE_CWD_CORE_SUPABASE_SERVICE_KEY"
SUPABASE_WORKDIR_REL = "digiquant/.supabase-local"

#: The compose service's own local default. The contract's digikey DSN names
#: 127.0.0.1:54329, which on this host is Paperclip's own board database.
LOCAL_DIGIKEY_DATABASE_URL = "sqlite:////data/digikey.db"

#: The digisearch service's own monitor store. The contract renders a
#: postgres DSN for this key, but the consumer is a SQLite store:
#: ``get_store()`` hands the value straight to sqlite3
#: (digisearch/src/digisearch/monitors/store.py), and the local stack has
#: no ``digivault`` database for a DSN to name. The compose digisearch
#: service sets DIGI_WORKSPACE=/data/monitors (docker-compose.yml) and
#: keeps that home on the digisearch_monitors volume, so the store's own
#: fallback resolves to this path.
LOCAL_DIGISEARCH_MONITORS_DB = "/data/monitors/.digisearch/monitors.sqlite3"

#: The provenance of the root .env travels with the values it describes: a
#: managed block at the bottom of the same file, holding digests and never
#: values. The .env is git-ignored, mode 0600, and written in one atomic
#: write, so the block can never describe a file that is no longer there.
STATE_HEADER = "# --- digithings localstack provenance (managed; do not edit) ---"
STATE_MARKER = "# digithings-localstack-state:"

#: The value in the .env is the one the render wrote.
SOURCE_RENDER = "render"
#: The value in the .env is the operator's own.
SOURCE_OPERATOR = "operator"
#: The value in the .env is the local stack's own; it always wins.
SOURCE_OVERRIDE = "override"

#: A name in a KEY=value file: what the shell exports and what compose reads.
ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def apply_defaults(root: Path, env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Set the local-stack defaults without overriding the operator.

    The port is written back as the RESOLVED port, not the raw knob: a
    value that cannot carry the whole port set never becomes one, and the
    health gate, this file and the generated config all have to read the
    same port.
    """
    env = os.environ if env is None else env
    env[PORT_ENV] = str(api_port(env))
    env.setdefault(KEYCHAIN_PREFIX_ENV, DEFAULT_KEYCHAIN_PREFIX)
    env.setdefault(GENERATE_CWD_ENV, str(Path(root) / SUPABASE_WORKDIR_REL))
    return env


def read_env_file(path: Path) -> Dict[str, str]:
    """Read a KEY=value file. Values are returned as they are stored.

    A line whose name is not an env identifier is not an entry: the host
    bring-up sources this file under `set -e`, so a line like "FOO BAR=baz"
    is read as a command and aborts the bring-up. The rewrite before
    DIG-4662 dropped such lines, so this one does not carry them over
    either.
    """
    values: Dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        name, sep, value = line.partition("=")
        if sep and ENV_NAME.match(name.strip()):
            values[name.strip()] = value
    return values


def local_overrides(env: Mapping[str, str], existing: Mapping[str, str]) -> Dict[str, str]:
    """The values the local stack sets over the rendered ones."""
    port = api_port(env)
    overrides = {
        # The contract's digikey DSN names 127.0.0.1:54329 - Paperclip's own
        # board database on this host. The local stack uses the compose
        # service's own sqlite default instead; digikey creates its own
        # schema in it.
        "DIGIKEY_DATABASE_URL": LOCAL_DIGIKEY_DATABASE_URL,
        # The contract's digisearch monitors DSN names 127.0.0.1:54329 -
        # Paperclip's own board database on this host - and it is a postgres
        # DSN the SQLite monitor store cannot open. The local stack uses
        # the digisearch service's own monitor store path instead.
        "DIGISEARCH_MONITORS_DB": LOCAL_DIGISEARCH_MONITORS_DB,
        # The compose default is 0 (production wants a stable PEM). Local
        # Docker dev opts in explicitly.
        "DIGIKEY_ALLOW_EPHEMERAL_KEY": "1",
        # The local Supabase instance, on the port the stack actually uses.
        "SUPABASE_URL": f"http://127.0.0.1:{port}",
        "CORE_SUPABASE_URL": f"http://127.0.0.1:{port}",
    }
    # OMNIROUTE_AUTH_PASSWORD is a contract secret with no secrets.yaml entry,
    # and the core profile's omniroute-auth-guard refuses to start without it
    # (the compose file keeps it a plain ${VAR:-} because there is no safe
    # placeholder for it). Keep one value and reuse it: the guard and
    # omniroute read the same .env.
    overrides["OMNIROUTE_AUTH_PASSWORD"] = (
        existing.get("OMNIROUTE_AUTH_PASSWORD") or secrets.token_hex(24)
    )
    return overrides


def digest(value: str) -> str:
    """The digest of a value. The provenance block stores these, never the values."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_state(path: Path) -> Dict[str, Dict[str, str]]:
    """Read the provenance block out of the .env.

    A missing or broken block reads as empty: the write still happens, the
    render decides for the names it claims.
    """
    if not path.exists():
        return {}
    try:
        raw = path.read_text()
    except OSError:
        return {}
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped.startswith(STATE_MARKER):
            continue
        try:
            payload = json.loads(stripped[len(STATE_MARKER) :].strip())
        except ValueError:
            return {}
        if not isinstance(payload, dict):
            return {}
        state: Dict[str, Dict[str, str]] = {}
        for name, entry in payload.items():
            if isinstance(entry, dict):
                state[name] = {k: v for k, v in entry.items() if isinstance(v, str)}
        return state
    return {}


def state_block(sources: Mapping[str, str], values: Mapping[str, str]) -> str:
    """The managed provenance block: sources and digests, never values.

    The digest is of the value in the .env, so the next run can tell whether
    the operator changed it in the meantime.
    """
    payload = {
        name: {"source": source, "digest": digest(values.get(name, ""))}
        for name, source in sorted(sources.items())
    }
    return f"{STATE_HEADER}\n{STATE_MARKER} {json.dumps(payload, sort_keys=True)}\n"


def operator_owns(
    value: str,
    entry: Optional[Mapping[str, str]] = None,
) -> bool:
    """Is the value in the .env the operator's own?

    The provenance block says what was decided last time:

    - the value in the .env is not the one we wrote -> the operator changed
      it, so it is theirs;
    - it is the one we wrote and we wrote the operator's -> it stays theirs;
    - it is the one we wrote and we wrote the render's -> the render decides
      again, so a rotated secret lands.

    Without a record the render decides for the names it claims: a value
    nobody recorded cannot be told apart from a stale copy of a rotated
    secret, and the stale copy is the dangerous one.
    """
    if not entry:
        return False
    known = entry.get("digest")
    if not known:
        return False
    if digest(value) != known:
        return True
    return entry.get("source") == SOURCE_OPERATOR


def recorded_source(entry: Optional[Mapping[str, str]]) -> str:
    """The source the provenance block recorded for a name.

    Only the three known sources are honoured; a broken or unknown record
    reads as the operator's own value.
    """
    source = (entry or {}).get("source")
    if source in (SOURCE_RENDER, SOURCE_OPERATOR, SOURCE_OVERRIDE):
        return str(source)
    return SOURCE_OPERATOR


def compose_env(
    rendered: Mapping[str, str],
    existing: Mapping[str, str],
    overrides: Mapping[str, str],
    state: Mapping[str, Mapping[str, str]],
) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Merge the rendered secrets, the operator's .env and the local overrides.

    Returns the values to write and, for each of them, where it came from.
    """
    values: Dict[str, str] = {}
    sources: Dict[str, str] = {}

    for name, value in rendered.items():
        values[name] = value
        sources[name] = SOURCE_RENDER

    for name, value in existing.items():
        if name in overrides:
            # The local stack decides this one; the operator's copy is not used.
            continue
        if name not in rendered:
            # The render does not claim this name any more. The recorded
            # source still says who owns the value: a value the render wrote
            # keeps the render's source, so a later render that claims the
            # name again decides it and a rotated secret lands. Calling it
            # the operator's here would freeze that value in the .env for
            # good. Without a record the operator owns it.
            values[name] = value
            sources[name] = recorded_source(state.get(name))
            continue
        if operator_owns(value, state.get(name)):
            values[name] = value
            sources[name] = SOURCE_OPERATOR
        else:
            sources[name] = SOURCE_RENDER

    for name, value in overrides.items():
        values[name] = value
        sources[name] = SOURCE_OVERRIDE

    return values, sources


def _write_private(path: Path, body: str) -> Path:
    """Write a file atomically, mode 0600. The content is never echoed."""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f"{path.name}.")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(body)
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return path


def write_env(root: Path, env: Optional[Mapping[str, str]] = None) -> Path:
    """Write the .env docker compose reads, mode 0600.

    The rendered .dev.vars are the base, the operator's values from the
    previous .env are kept, and the local overrides win over both.
    """
    env = os.environ if env is None else env
    root = Path(root)
    target = root / ".env"
    existing = read_env_file(target)
    rendered = read_env_file(root / ".dev.vars")
    overrides = local_overrides(env, existing)
    state = read_state(target)
    values, sources = compose_env(rendered, existing, overrides, state)
    body = "".join(f"{name}={value}\n" for name, value in sorted(values.items()))
    # The values and their provenance go out in one atomic write: a record in
    # a second file can describe a file that is no longer there, and a stale
    # record froze a rotated secret.
    body += state_block(sources, values)
    _write_private(target, body)
    return target


def main(argv: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Write the .env docker compose reads.")
    parser.add_argument("--root", default=None, help="repository root")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[2]
    apply_defaults(root)
    target = write_env(root)
    print(f"localenv: wrote {target} (mode 0600)")
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
