"""`digiquant gloomberb ...` — bring your own Gloomberb session (DIG-2752).

The Gloomberb session cookie belongs to whoever deploys the digithings stack:
it comes from that deployer's own Gloomberb account and lives in that
deployment's own secret store. digithings never mints one, never shares one
and never replays one. Nothing in this module prints, logs or echoes the value
— `status` reports a non-reversible fingerprint instead, and `shell` injects
the value into a child process environment without writing it anywhere.

Subcommands
-----------
``login``   walk through copying the cookie out of the operator's own browser,
            validate it against api.gloom.sh, then store it in the macOS
            Keychain, in a gitignored ``.env`` (mode 0600), or print the exact
            Cloudflare ``wrangler secret put`` command.
``status``  report the kill switch, which stores hold a cookie, and whether the
            session tools are currently advertised.
``logout``  drop the local copies (Keychain item + ``.env`` line) and print the
            command that deletes or rotates the secret in the deployment the
            caller actually owns.
``shell``   run a command with the stored cookie already in its environment,
            which is what makes a Keychain-only deployment usable at all.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path

import click

from digiquant.data.gloomberb.client import (
    GLOOMBERB_ENABLED_ENV,
    GLOOMBERB_SESSION_COOKIE_ENV,
    gloomberb_enabled,
    session_cache_fingerprint,
)
from digiquant.data.gloomberb.entitlements import TOOL_ENTITLEMENTS
from digiquant.data.gloomberb.session_gate import session_gate_status

__all__ = ["gloomberb"]

_KEYCHAIN_SERVICE = "digithings.gloomberb"
_KEYCHAIN_ACCOUNT = "GLOOMBERB_SESSION_COOKIE"
_SECURITY_BIN = "/usr/bin/security"
_DEFAULT_ENV_FILE = Path(".env")
_SESSION_ENTITLEMENTS = frozenset({"session", "preview", "pro"})
_GATED_TOOL_COUNT = sum(1 for value in TOOL_ENTITLEMENTS.values() if value in _SESSION_ENTITLEMENTS)


# ─── stores ──────────────────────────────────────────────────────────────────


def _keychain_binary() -> str | None:
    """Absolute path to the macOS `security` tool, or None off macOS."""
    if os.path.exists(_SECURITY_BIN):
        return _SECURITY_BIN
    return shutil.which("security")


def _keychain_write(cookie: str) -> tuple[bool, str]:
    binary = _keychain_binary()
    if binary is None:
        return False, "the macOS `security` tool is not available on this host"
    proc = subprocess.run(
        [
            binary,
            "add-generic-password",
            "-U",
            "-a",
            _KEYCHAIN_ACCOUNT,
            "-s",
            _KEYCHAIN_SERVICE,
            "-w",
            cookie,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    # The value is an argv element, so stderr can repeat it: never surface stderr.
    if proc.returncode != 0:
        return False, f"the Keychain refused the write (exit {proc.returncode})"
    return True, ""


def _keychain_read() -> str | None:
    binary = _keychain_binary()
    if binary is None:
        return None
    proc = subprocess.run(
        [
            binary,
            "find-generic-password",
            "-a",
            _KEYCHAIN_ACCOUNT,
            "-s",
            _KEYCHAIN_SERVICE,
            "-w",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def _keychain_delete() -> bool:
    binary = _keychain_binary()
    if binary is None:
        return False
    proc = subprocess.run(
        [
            binary,
            "delete-generic-password",
            "-a",
            _KEYCHAIN_ACCOUNT,
            "-s",
            _KEYCHAIN_SERVICE,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0


def _env_file(explicit: Path | None) -> Path:
    return explicit if explicit is not None else _DEFAULT_ENV_FILE


def _env_read(path: Path) -> str | None:
    """Return the cookie stored in `path`, or None. Never logs."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{GLOOMBERB_SESSION_COOKIE_ENV}="):
            value = stripped.split("=", 1)[1].strip().strip('"').strip("'")
            return value or None
    return None


def _env_write(path: Path, cookie: str) -> None:
    """Write the cookie into `path`, creating it 0600 before the value lands."""
    lines: list[str] = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
    assignment = f"{GLOOMBERB_SESSION_COOKIE_ENV}={cookie}"
    for index, line in enumerate(lines):
        if line.strip().startswith(f"{GLOOMBERB_SESSION_COOKIE_ENV}="):
            lines[index] = assignment
            break
    else:
        lines.append(assignment)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        stream.write("\n".join(lines) + "\n")
    os.chmod(path, 0o600)


def _env_clear(path: Path) -> bool:
    """Drop the cookie value, leaving the key present as an empty knob."""
    if not path.exists():
        return False
    lines = path.read_text(encoding="utf-8").splitlines()
    changed = False
    for index, line in enumerate(lines):
        if line.strip().startswith(f"{GLOOMBERB_SESSION_COOKIE_ENV}="):
            if line.strip() != f"{GLOOMBERB_SESSION_COOKIE_ENV}=":
                lines[index] = f"{GLOOMBERB_SESSION_COOKIE_ENV}="
                changed = True
            break
    if not changed:
        return False
    handle = os.open(path, os.O_WRONLY | os.O_TRUNC)
    with os.fdopen(handle, "w", encoding="utf-8") as stream:
        stream.write("\n".join(lines) + "\n")
    return True


def _cloudflare_command(action: str) -> str:
    if action == "delete":
        return "npx wrangler secret delete GLOOMBERB_SESSION_COOKIE"
    return (
        "printf '%s' \"$GLOOMBERB_SESSION_COOKIE\" | "
        "env -u CLOUDFLARE_API_TOKEN npx wrangler secret put GLOOMBERB_SESSION_COOKIE"
    )


def _stored_cookie(env_file: Path) -> str:
    """First non-empty cookie across environment, Keychain, .env."""
    return (
        os.environ.get(GLOOMBERB_SESSION_COOKIE_ENV, "").strip()
        or _keychain_read()
        or _env_read(env_file)
        or ""
    )


# ─── commands ────────────────────────────────────────────────────────────────


@click.group()
def gloomberb() -> None:
    """Bring your own Gloomberb session cookie (Keychain, .env or Cloudflare)."""


@gloomberb.command("login")
@click.option(
    "--store",
    type=click.Choice(["keychain", "env", "cloudflare"]),
    default=None,
    help="Where to keep the cookie. Default: keychain on macOS, else env.",
)
@click.option(
    "--env-file",
    type=click.Path(path_type=Path),
    default=None,
    help="Gitignored .env to write. Default: ./.env",
)
def login(store: str | None, env_file: Path | None) -> None:
    """Validate a Gloomberb session cookie, then store it for this deployment."""
    target = store or ("keychain" if _keychain_binary() else "env")
    click.echo("1. Sign in to your own Gloomberb account, in your own browser.")
    click.echo("")
    click.echo("Your browser holds a session for that account. Reading it out of your")
    click.echo("browser is a step you perform; digithings does not publish the route, and")
    click.echo("DIG-1434 removed it from this repository on purpose.")
    click.echo("")
    click.echo("The value is your own account's credential. digithings cannot mint, share")
    click.echo("or replay it, and it is never echoed, logged or written to a repository.")
    cookie = click.prompt("2. Paste the value", hide_input=True, default="")
    cookie = cookie.strip()
    if not cookie:
        click.echo("No cookie was pasted, so nothing was stored.", err=True)
        raise SystemExit(1)

    verdict = session_gate_status(cookie=cookie)
    if not verdict.authenticated:
        click.echo(f"That cookie is not usable: {verdict.code} ({verdict.detail}).", err=True)
        click.echo("Nothing was stored. Sign in again, obtain a fresh value, and retry.", err=True)
        raise SystemExit(1)

    if target == "keychain":
        stored, reason = _keychain_write(cookie)
        if not stored:
            click.echo(f"Validated, but the Keychain refused the write: {reason}.", err=True)
            click.echo(
                "Nothing was stored. Use --store env or --store cloudflare instead.", err=True
            )
            raise SystemExit(1)
        click.echo(f"Stored in the macOS Keychain (service {_KEYCHAIN_SERVICE}).")
        click.echo("Caveat: `security add-generic-password` takes the value as an argument, so it")
        click.echo("is briefly visible in this host's process list. On a shared host prefer")
        click.echo("--store env (written 0600) or --store cloudflare.")
        click.echo("Use it without writing it anywhere: digiquant gloomberb shell -- <command>")
    elif target == "env":
        path = _env_file(env_file)
        _env_write(path, cookie)
        click.echo(f"Stored in {path} with mode 0600. Never commit that file.")
    else:
        click.echo("Validated. Put it on Cloudflare with this command; it reads the value from")
        click.echo("your shell, so the value never appears in the command line or the history:")
        click.echo("")
        click.echo(f"  {shlex.quote(_cloudflare_command('put'))}")
        click.echo("")

    click.echo(f"Validated against api.gloom.sh, fingerprint {session_cache_fingerprint(cookie)}.")
    click.echo(f"The {_GATED_TOOL_COUNT} session, preview and pro tools are now advertised.")
    click.echo(f"The kill switch still has to be on: set {GLOOMBERB_ENABLED_ENV}=1.")
    click.echo("Revoke this credential at your own Gloomberb account, or drop it locally with")
    click.echo("digiquant gloomberb logout.")


@gloomberb.command("status")
@click.option(
    "--env-file",
    type=click.Path(path_type=Path),
    default=None,
    help="Gitignored .env to read. Default: ./.env",
)
def status(env_file: Path | None) -> None:
    """Report whether the session tools are advertised. Never prints a cookie."""
    path = _env_file(env_file)
    env_value = os.environ.get(GLOOMBERB_SESSION_COOKIE_ENV, "").strip()
    keychain_value = _keychain_read()
    file_value = _env_read(path)
    cookie = env_value or keychain_value or file_value or None

    sources = []
    if env_value:
        sources.append("process environment")
    if keychain_value:
        sources.append("macOS Keychain")
    if file_value:
        sources.append(str(path))

    click.echo(
        f"kill switch        : {'on' if gloomberb_enabled() else 'off'} ({GLOOMBERB_ENABLED_ENV})"
    )
    click.echo(f"cookie configured  : {', '.join(sources) if sources else 'no'}")
    if cookie:
        click.echo(f"cookie fingerprint : {session_cache_fingerprint(cookie)} (never the value)")
    verdict = session_gate_status() if env_value else session_gate_status(cookie=cookie)
    click.echo(f"session validation : {verdict.code} - {verdict.detail}")
    click.echo(
        f"gated tools        : {'advertised' if verdict.authenticated else 'hidden'} "
        f"({_GATED_TOOL_COUNT} session/preview/pro tools)"
    )
    if not verdict.authenticated:
        click.echo("")
        click.echo("To authenticate: sign in to your own Gloomberb account, then run")
        click.echo("digiquant gloomberb login.")


@gloomberb.command("logout")
@click.option(
    "--env-file",
    type=click.Path(path_type=Path),
    default=None,
    help="Gitignored .env to clear. Default: ./.env",
)
@click.option("--yes", is_flag=True, help="Do not ask for confirmation.")
def logout(env_file: Path | None, yes: bool) -> None:
    """Remove the local copies of the Gloomberb session cookie."""
    if not yes:
        click.confirm("Remove the local Gloomberb session cookie?", abort=True)
    path = _env_file(env_file)
    removed = []
    if _keychain_delete():
        removed.append("macOS Keychain")
    if _env_clear(path):
        removed.append(str(path))
    if os.environ.get(GLOOMBERB_SESSION_COOKIE_ENV, "").strip():
        removed.append("this shell's environment")
    click.echo("Removed: " + ", ".join(removed) if removed else "Nothing was stored locally.")
    click.echo("")
    click.echo("A Cloudflare secret is not ours to delete. In the deployment you own run:")
    click.echo(f"  {_cloudflare_command('delete')}")
    click.echo(
        "Then revoke the session at your own Gloomberb account so the credential is dead everywhere."
    )


@gloomberb.command(
    "shell",
    context_settings={"ignore_unknown_options": True},
)
@click.option(
    "--env-file",
    type=click.Path(path_type=Path),
    default=None,
    help="Gitignored .env to read. Default: ./.env",
)
@click.argument("command", nargs=-1, type=click.UNPROCESSED)
def shell_command(env_file: Path | None, command: tuple[str, ...]) -> None:
    """Run a command with the stored cookie in its environment, never printed."""
    cookie = _stored_cookie(_env_file(env_file))
    if not cookie:
        click.echo(
            "No Gloomberb session cookie is stored. Sign in to your own account and run "
            "digiquant gloomberb login.",
            err=True,
        )
        raise SystemExit(1)
    if not gloomberb_enabled():
        click.echo(
            f"note: {GLOOMBERB_ENABLED_ENV} is not on, so the whole family stays off even with the cookie",
            err=True,
        )
    env = dict(os.environ)
    env[GLOOMBERB_SESSION_COOKIE_ENV] = cookie
    shell_bin = "/bin/zsh" if os.path.exists("/bin/zsh") else "/bin/sh"
    argv = [shell_bin, "-c", shlex.join(command)] if command else [shell_bin]
    os.execve(shell_bin, argv, env)
