"""The local stack's environment defaults.

Three things have to line up for the stack to come up beside core-local: the
Supabase ports, the keychain namespace the local material actually lives in,
and a ``.env`` docker compose can read. The compose services declare
``env_file: .env`` and compose itself needs that file present to interpolate
``${VAR}``, while the render step only ever writes ``.dev.vars``.
"""
from __future__ import annotations

import os
import secrets
import stat
import sys
import tempfile
from pathlib import Path
from typing import Dict, Mapping, Optional

try:  # imported as part of a package
    from .supabase_ports import PORT_ENV, api_port
except ImportError:  # run as a script
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from supabase_ports import PORT_ENV, api_port

#: Overrides the contract's keychain_service_prefix. The local material
#: lives under this namespace; the contract's default ("digithings/") is
#: where the shared digithings secrets live.
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
    """Read a KEY=value file. Values are returned as they are stored."""
    values: Dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        name, sep, value = line.partition("=")
        if sep and name.strip():
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


def write_env(root: Path, env: Optional[Mapping[str, str]] = None) -> Path:
    """Write the .env docker compose reads, mode 0600.

    The rendered .dev.vars are the base; the local overrides win over them,
    and the previous .env wins over the generated omniroute password so the
    value stays stable across runs.
    """
    env = os.environ if env is None else env
    root = Path(root)
    target = root / ".env"
    existing = read_env_file(target)
    values = read_env_file(root / ".dev.vars")
    values.update(local_overrides(env, existing))
    body = "".join(f"{name}={value}\n" for name, value in sorted(values.items()))
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=".env.")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(body)
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
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
