"""The `gh` wrapper that sits in front of the host gh guard.

The host gh guard (Board-owned, `~/paperclip-workspace/tools/seat-gh-guard/bin/gh`)
refuses the merges and the secret writes a seat must not do. This shim sits in
front of it and does three things the guard does not:

* it refuses a pull request against a repository outside the digithings-ai
  organization -- Chris's rule of 21 October, and the reason no seat can open
  an upstream pull request under any identity;
* it expands a field value of `@<path>` into the contents of that file, for
  both `-f/--raw-field` and `-F/--field`, so a comment body is the text that
  was written and not the path that was typed;
* in `app` mode it asks the broker for a token scoped to this run's own
  repository and hands that token to the guard's `gh` for this one call.

The order of those matters. The refusals happen before the broker is asked
for anything, so a refusal costs nothing and leaks nothing. The refusals and
the field rewrite also happen whether or not this is a seat run: they are
rules about what may be sent to GitHub, and they cost nothing when they pass.

The shim never execs the real `gh` itself. It execs the guard, which execs the
real `gh`. That is the whole point: a seat that could point the shim at the
real binary would have turned the guard off, which the operating rules forbid
in as many words. For the same reason the guard's path is a constant here and
not an environment variable: a seat that could name its own program as "the
guard" would have taken the guard out of the chain.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .core import (
    APP_MODE,
    DEFAULT_SOCKET_PATH,
    AuthError,
    decode_jwt_claims,
    read_auth_mode,
    redact_secrets,
)

#: The exit codes the shim uses. They are distinct so a caller can tell a
#: refusal from a crash from a missing broker.
EXIT_OK = 0
EXIT_USAGE = 64
EXIT_AUTH = 66
EXIT_UNAVAILABLE = 69
EXIT_INTERNAL = 70
EXIT_REFUSED = 76

#: The Board-owned guard. The shim execs this, never the real `gh`. It is a
#: constant: there is no environment override, because a seat that could
#: point the shim at a program of its own would have turned the guard off.
GUARD_PATH = Path("~/paperclip-workspace/tools/seat-gh-guard/bin/gh")

#: The real `gh` binaries. The shim refuses to exec these: handing a call to
#: the real binary is how the guard would be turned off.
REAL_GH_PATHS: tuple[str, ...] = ("/opt/homebrew/bin/gh", "/usr/local/bin/gh")

#: The organization whose repositories a seat may open a pull request against.
#: Every repository in it is allowed; every repository outside it is refused.
ORG = "digithings-ai"

#: The socket the broker listens on. There is deliberately no environment
#: override: a seat that could point the shim at a socket of its own would be
#: talking to a broker it wrote, and the one-repo wall, the run-scoped
#: lifetime and the audit trail would all be its own. The tests change the
#: module constant instead.
BROKER_SOCKET = str(DEFAULT_SOCKET_PATH)

#: The host's own credentials. They are removed from the environment the
#: guard and the real `gh` run with, so a seat cannot fall back to the host's
#: token when the broker is in charge.
HOST_CREDENTIAL_ENV: tuple[str, ...] = (
    "GITHUB_TOKEN",
    "GH_ENTERPRISE_TOKEN",
    "GITHUB_ENTERPRISE_TOKEN",
    "GH_HOST",
)

#: The prefix of the per-run scratch directory. The shim makes this
#: directory itself; a caller that could name it could point it at the
#: host's own configuration and have it emptied.
RUN_TMP_PREFIX = "dt-broker-"

#: Where the per-run scratch directories live. A constant for the same
#: reason as the socket: a caller that could name the directory could name
#: the host's own configuration directory.
RUN_TMP_ROOT = Path(tempfile.gettempdir())

#: The rollback flag, read from the account that owns the broker. There is
#: deliberately no environment override for the path: a seat that could point
#: the shim at a file it owns could turn the broker off by writing `host`
#: into it. The tests change the module constant instead.
AUTH_MODE_PATH = Path("/Users/_dtbroker/.config/digithings/github-auth-mode")

#: The fields that carry a comment body. A body that is a path to a file is
#: a mistake, and a mistake that silently damages a review is worse than a
#: mistake that stops.
BODY_KEYS: frozenset[str] = frozenset({"body"})

#: The largest file a field may read. A comment body is text; a body of a
#: hundred megabytes is not a comment.
MAX_FIELD_BYTES = 1 << 20

#: The flags that carry a field, and the flag as it was written. A field gh
#: was told to type stays typed: `-F` turns `true` into a boolean and fills
#: `{owner}` in, `-f` sends the text. Only the field the shim expands is
#: rewritten, and only because a file's contents are text.
FIELD_FLAGS: dict[str, str] = {
    "-f": "-f",
    "--raw-field": "--raw-field",
    "-F": "-F",
    "--field": "--field",
}

#: The flag that sends a value as plain text. An expanded file goes out as
#: text: the contents of a review are a body, not a boolean.
TEXT_FLAGS: dict[str, str] = {
    "-f": "-f",
    "--raw-field": "--raw-field",
    "-F": "-f",
    "--field": "--raw-field",
}

#: The flag that says the gh shim is already in the chain. A shim that called
#: itself would loop for ever, so the second one refuses.
SHIM_MARKER = "DT_BROKER_SHIM_ACTIVE"

#: The flags that carry a comment body as a plain string.
BODY_FLAGS: frozenset[str] = frozenset({"--body", "-b"})


class Refusal(Exception):
    """A call the shim will not make, with the reason it will not make it."""


class AuthRefusal(Refusal):
    """A call the shim will not make because there is nothing to sign it with."""


@dataclass
class Plan:
    """What the shim decided to do with one call."""

    argv: list[str]
    env: dict[str, str] = field(default_factory=dict)
    removed_env: tuple[str, ...] = ()
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# the guard
# ---------------------------------------------------------------------------


def guard_path(env: dict[str, str]) -> Path:
    """The guard to exec.

    The shim refuses to hand a call to the real `gh`, so a guard path that
    resolves to one of the real binaries is a refusal rather than a
    configuration.
    """
    path = Path(GUARD_PATH).expanduser()
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path
    for real in REAL_GH_PATHS:
        try:
            if resolved == Path(real).resolve():
                raise Refusal(
                    f"{real} is the real gh, not the guard; the shim will not bypass the guard"
                )
        except OSError:  # pragma: no cover - the paths exist on the host
            continue
    return path


# ---------------------------------------------------------------------------
# the run context
# ---------------------------------------------------------------------------


def is_seat_process(env: dict[str, str]) -> bool:
    """True when this process looks like a seat run.

    The guard uses the same three variables to decide whether it is talking
    to a seat, so the two agree about who is being protected. The shim
    decides nothing on this: what the shim decides on is the run
    credential, which the broker hands to the Paperclip API, and the API
    answers for the agent, the run and the ticket.
    """
    return any(
        str(env.get(name) or "").strip()
        for name in ("PAPERCLIP_AGENT_ID", "PAPERCLIP_RUN_ID", "PAPERCLIP_TASK_ID")
    )


def run_credential(env: dict[str, str]) -> str:
    """The run credential this process carries, if it carries one.

    This is what decides whether a token can be minted. It is not a name
    the caller chose: the broker hands it to the Paperclip API and the API
    answers for the agent, the run and the ticket. A caller that shows
    nothing gets no token, and -- while the broker is in charge -- no host
    credential either.
    """
    return str(env.get("PAPERCLIP_API_KEY") or "").strip()


def socket_path(env: dict[str, str]) -> str:
    """Where the broker listens.

    The path is a constant of the program. A caller that could name the
    socket could point the shim at a broker it wrote itself, and then the
    one-repo wall, the run-scoped lifetime and the audit trail would be its
    own.
    """
    return BROKER_SOCKET


def run_tmp(env: dict[str, str]) -> Path:
    """The scratch directory for this run.

    `GH_CONFIG_DIR` points inside it, so the `gh` that runs reads an empty
    configuration and not the host's. The shim names the directory: the run
    id is hashed into the name, so a run id with a path in it cannot send
    the directory somewhere else, and a caller cannot choose where a
    configuration is emptied.
    """
    run_id = str(env.get("PAPERCLIP_RUN_ID") or "no-run")
    digest = hashlib.sha256(run_id.encode("utf-8", "replace")).hexdigest()[:16]
    return Path(RUN_TMP_ROOT) / f"{RUN_TMP_PREFIX}{digest}"


def auth_mode(env: dict[str, str]) -> str:
    """The rollback flag, as this process sees it.

    The flag lives with the account that owns the broker, so a seat process
    can read it and cannot write it. A flag that cannot be read, or that
    says something else, reads as `app`: the broker stays in charge and the
    seat cannot turn the broker off by damaging a file.
    """
    return read_auth_mode(AUTH_MODE_PATH, default=APP_MODE)


# ---------------------------------------------------------------------------
# the field rewrite
# ---------------------------------------------------------------------------


def _split_field(argument: str) -> tuple[str, str] | None:
    """Split `key=value` into its two halves, or answer None."""
    if "=" not in argument:
        return None
    key, _, value = argument.partition("=")
    return key, value


def _safe(value: object) -> str:
    """A value the caller sent, with anything credential-shaped taken out.

    The shim's refusals and notes are read in a seat's run log. A caller
    that sent a token by mistake must not have it written down because the
    shim quoted it back.
    """
    return redact_secrets(str(value))


def _no_nul(value: str, what: str) -> str:
    """Refuse a value that carries a NUL byte.

    A NUL byte cannot be passed to a program: `execve` refuses it, and the
    refusal arrives as a crash rather than as a message. The shim says so
    instead.
    """
    if "\x00" in value:
        raise Refusal(
            f"{what} carries a NUL byte, which cannot be passed to a program"
        )
    return value


@dataclass
class _FieldArg:
    """One field argument, and the shape it was written in."""

    #: The flag as it was written: `-f`, `--raw-field`, `-F` or `--field`.
    flag: str
    key: str
    raw: str
    #: `attached` (`-fkey=value`), `long` (`--field=key=value`) or `spaced`
    #: (`-f key=value`).
    shape: str

    def render(self, flag: str, value: str) -> list[str]:
        """The argument again, with a new flag and a new value."""
        if self.shape == "attached":
            return [f"{flag}{self.key}={value}"]
        if self.shape == "long":
            return [f"{flag}={self.key}={value}"]
        return [flag, f"{self.key}={value}"]


def _parse_field_arg(argv: list[str], index: int) -> tuple[_FieldArg, int] | None:
    """Read the field argument at `index`, if there is one.

    The three shapes a field flag is written in are all read: `-f key=value`,
    `-fkey=value` and `--field=key=value`. The second and the third carry
    the value inside the argument, so the shape is remembered and the
    argument is written back the way it came in.
    """
    argument = argv[index]
    if argument in FIELD_FLAGS:
        if index + 1 >= len(argv):
            raise Refusal(f"{argument} was given without a value")
        parts = _split_field(argv[index + 1])
        if parts is None:
            raise Refusal(
                f"{argument} needs a key=value pair, not {_safe(argv[index + 1])!r}"
            )
        key, raw = parts
        return _FieldArg(flag=FIELD_FLAGS[argument], key=key, raw=raw, shape="spaced"), index + 1
    if argument.startswith("--") and "=" in argument:
        head, _, tail = argument.partition("=")
        canonical = FIELD_FLAGS.get(head)
        if canonical is None:
            return None
        parts = _split_field(tail)
        if parts is None:
            raise Refusal(f"{head} needs a key=value pair, not {_safe(tail)!r}")
        key, raw = parts
        return _FieldArg(flag=canonical, key=key, raw=raw, shape="long"), index
    if argument.startswith("-") and not argument.startswith("--") and len(argument) > 2:
        head = argument[:2]
        canonical = FIELD_FLAGS.get(head)
        if canonical is None:
            return None
        parts = _split_field(argument[2:])
        if parts is None:
            raise Refusal(f"{head} needs a key=value pair, not {_safe(argument[2:])!r}")
        key, raw = parts
        return _FieldArg(flag=canonical, key=key, raw=raw, shape="attached"), index
    return None


def _looks_like_a_file(value: str) -> bool:
    """True when a value is a path to a file that exists.

    A body that is `/tmp/review.md` is a mistake: the author meant the text
    in the file, and posting the path is how a review gets silently
    replaced by a filename. The same is true of `review.md` next to the
    seat: the path is relative, but the mistake is the same one.
    """
    if not value or value.startswith("@"):
        return False
    if "\n" in value or "\x00" in value or len(value) > 4096:
        return False
    try:
        candidate = Path(value).expanduser()
        return candidate.is_file()
    except OSError:  # pragma: no cover - depends on the host
        return False


def _read_field_file(path_text: str) -> str:
    """Read a file a field points at, refusing anything that is not text."""
    if path_text == "-":
        raise Refusal(
            "a field of `@-` would read the standard input, which this shim does not do; "
            "write the body to a file and use `@<path>`"
        )
    path = Path(path_text).expanduser()
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise Refusal(f"the file {_safe(path)} cannot be read: {exc}") from exc
    if size > MAX_FIELD_BYTES:
        raise Refusal(
            f"the file {_safe(path)} is too large to send as a field ({size} bytes)"
        )
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise Refusal(
            f"the file {_safe(path)} is not readable text: {exc}"
        ) from exc
    return _no_nul(content, f"the file {_safe(path)}")


def rewrite_fields(argv: list[str]) -> tuple[list[str], list[str]]:
    """Expand `@<path>` field values, and refuse a body that is a path.

    `gh api -F body=@review.md` reads the file and `gh api -f body=@review.md`
    sends the text `@review.md`. The first is what the author meant and the
    second is what happened. This makes both send the file's contents, as a
    string, so the body that arrives is the body that was written.

    A body that is a bare path -- no `@`, but pointing at a file that exists
    -- is refused rather than posted, because posting it is the same damage
    with one more keystroke of typing.

    Only `gh api` has field flags, so only `gh api` is rewritten: `-F` means
    `--body-file` to `gh pr comment`, and that flag is already correct.
    """
    if not argv or argv[0] != "api":
        return list(argv), []
    out: list[str] = []
    notes: list[str] = []
    index = 0
    while index < len(argv):
        parsed = _parse_field_arg(argv, index)
        if parsed is None:
            out.append(argv[index])
            index += 1
            continue
        field_arg, index = parsed
        _no_nul(field_arg.raw, f"the {field_arg.key} field")
        if field_arg.raw.startswith("@"):
            content = _read_field_file(field_arg.raw[1:])
            out.extend(field_arg.render(TEXT_FLAGS.get(field_arg.flag, "-f"), content))
            notes.append(f"expanded {field_arg.key} from {_safe(field_arg.raw)}")
            index += 1
            continue
        if field_arg.key in BODY_KEYS and _looks_like_a_file(field_arg.raw):
            raise Refusal(
                f"the {field_arg.key} field is a path to a file ({_safe(field_arg.raw)}); "
                "the shim will not post a path where a body belongs. Use `@<path>` to send "
                "the file's contents."
            )
        out.extend(field_arg.render(field_arg.flag, field_arg.raw))
        index += 1
    return out, notes


def rewrite_body_flags(argv: list[str]) -> tuple[list[str], list[str]]:
    """Expand `@<path>` in `--body`, and refuse a body that is a path.

    `gh pr comment --body @review.md` posts the text `@review.md`: the
    `--body` flag has no file magic. `--body-file` is the correct flag and
    is left exactly as it is.
    """
    out: list[str] = []
    notes: list[str] = []
    index = 0
    while index < len(argv):
        argument = argv[index]
        if argument in BODY_FLAGS:
            if index + 1 >= len(argv):
                raise Refusal(f"{argument} was given without a value")
            value = argv[index + 1]
            _no_nul(value, f"the {argument} body")
            if value.startswith("@"):
                content = _read_field_file(value[1:])
                out.extend([argument, content])
                notes.append(f"expanded the body from {_safe(value)}")
                index += 2
                continue
            if _looks_like_a_file(value):
                raise Refusal(
                    f"the body is a path to a file ({_safe(value)}); the shim will not post "
                    "a path where a body belongs. Use `--body-file <path>` to send the file."
                )
            out.extend([argument, value])
            index += 2
            continue
        out.append(argument)
        index += 1
    return out, notes


# ---------------------------------------------------------------------------
# the organization check
# ---------------------------------------------------------------------------


def _git_remote_url(cwd: Path, name: str) -> str | None:
    """The URL of one remote, when the checkout has one."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(cwd), "remote", "get-url", name],
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    url = proc.stdout.decode("utf-8", "replace").strip()
    return url or None


def _repo_from_url(url: str) -> str | None:
    """`owner/name` from a remote URL."""
    if not url:
        return None
    cleaned = url.removesuffix(".git")
    if cleaned.startswith("git@"):
        cleaned = cleaned.split(":", 1)[-1]
    elif "://" in cleaned:
        cleaned = cleaned.split("://", 1)[-1]
    parts = [part for part in cleaned.split("/") if part]
    if len(parts) < 2:
        return None
    return f"{parts[-2]}/{parts[-1]}"


def _git_remote_repo(cwd: Path) -> str | None:
    """The `owner/name` of the repository in `cwd`, read from git.

    The remotes are read in the order gh reads them -- `upstream`, then
    `github`, then `origin` -- because a checkout that has an `upstream` is
    a fork, and gh will open the pull request against the fork's upstream
    while a shim that only looked at `origin` would have cleared a
    different repository.
    """
    for name in ("upstream", "github", "origin"):
        url = _git_remote_url(cwd, name)
        if url is None:
            continue
        return _repo_from_url(url)
    return None


def _no_repository_named() -> Refusal:
    """The refusal for a repository flag that names no repository."""
    return Refusal(
        "this call names a repository but gives none, so the target cannot be checked "
        f"against the {ORG} organization"
    )


#: The flags of `gh pr create` that take a value, in the long and the short
#: spelling. The value of one of these is a value and not a flag: a title
#: that begins `-R` is a title, and reading it as the repository is how the
#: wall was made to answer for a call it was not about. The set is the
#: flag list of gh 2.102.0; a flag this shim does not know is refused.
_PR_CREATE_VALUE_FLAGS: frozenset[str] = frozenset(
    {
        "--assignee",
        "-a",
        "--attach",
        "--base",
        "-B",
        "--body",
        "-b",
        "--body-file",
        "-F",
        "--head",
        "-H",
        "--label",
        "-l",
        "--milestone",
        "-m",
        "--project",
        "-p",
        "--recover",
        "--reviewer",
        "-r",
        "--template",
        "-T",
        "--title",
        "-t",
    }
)

#: The boolean flags of `gh pr create`. They take no value, so the argument
#: after one is a flag position, and a repository flag there is the call's
#: own target.
_PR_CREATE_BOOLEAN_FLAGS: frozenset[str] = frozenset(
    {
        "--draft",
        "-d",
        "--dry-run",
        "--editor",
        "-e",
        "--fill",
        "-f",
        "--fill-first",
        "--fill-verbose",
        "--help",
        "-h",
        "--no-maintainer-edit",
        "--web",
        "-w",
    }
)

#: The flags of `gh api` that take a value. `gh api` takes the repository
#: only when the endpoint uses the `{owner}`/`{repo}` placeholders, but the
#: same scan answers for it.
_API_VALUE_FLAGS: frozenset[str] = frozenset(
    {
        "--cache",
        "--field",
        "-F",
        "--header",
        "-H",
        "--hostname",
        "--input",
        "--jq",
        "-q",
        "--method",
        "-X",
        "--preview",
        "-p",
        "--raw-field",
        "-f",
        "--template",
        "-t",
    }
)

#: The boolean flags of `gh api`.
_API_BOOLEAN_FLAGS: frozenset[str] = frozenset(
    {
        "--allow-escape-sequences",
        "--help",
        "-h",
        "--include",
        "-i",
        "--paginate",
        "--silent",
        "--slurp",
        "--verbose",
    }
)


def _flag_tables(command: str) -> tuple[frozenset[str], frozenset[str]]:
    """The value flags and the boolean flags of the command being scanned.

    `gh pr create` and `gh api` do not share a flag list. A caller that is
    neither -- the tests call the scanner directly -- gets both lists, so
    a known flag of either command is still placed correctly.
    """
    if command == "api":
        return _API_VALUE_FLAGS, _API_BOOLEAN_FLAGS
    if command == "pr":
        return _PR_CREATE_VALUE_FLAGS, _PR_CREATE_BOOLEAN_FLAGS
    return (
        _PR_CREATE_VALUE_FLAGS | _API_VALUE_FLAGS,
        _PR_CREATE_BOOLEAN_FLAGS | _API_BOOLEAN_FLAGS,
    )


def _short_flag_repo(
    argument: str,
    value_flags: frozenset[str],
    boolean_flags: frozenset[str],
    argv: list[str],
    index: int,
) -> tuple[str | None, int]:
    """The repository a short-flag cluster names, and the arguments it eats.

    pflag reads a short flag in a cluster one letter at a time: the letters
    before a flag that takes a value are booleans, and the rest of the
    cluster is that flag's value. `-fR owner/name` names the repository on
    `gh pr create` (`-f` is `--fill`), so a scan that only looked at the
    start of the argument would not see the flag gh acts on.

    An attached value is whatever follows the flag letter, `=` included:
    pflag strips one `=` only when something follows it, so `-t=` is the
    title `=` and `-t=x` is the title `x`. Neither one eats the next
    argument. Only a value flag with nothing attached does that, and
    reading `-t=` as "value comes next" is how the scan lost sight of a
    `--repo` that gh still read.

    The answer is the repository name (or None) and how many arguments the
    cluster consumes: 1 for the cluster alone, 2 when its last flag takes
    the next argument as its value.
    """
    chars = argument[1:]
    while chars:
        char = chars[0]
        if char == "R":
            rest = chars[1:]
            if not rest:
                if index + 1 >= len(argv):
                    raise _no_repository_named()
                value = argv[index + 1]
                if not value:
                    raise _no_repository_named()
                return value, 2
            if len(rest) > 1 and rest.startswith("="):
                # pflag strips one `=` only when a value follows it, so
                # `-R=owner/name` is `-R owner/name` and `-R=` is `-R "="`.
                return rest[1:], 1
            return rest, 1

        flag = f"-{char}"
        if flag in boolean_flags:
            chars = chars[1:]
            continue
        if flag in value_flags:
            if chars[1:]:
                # The value is attached, `=` included; the rest of the
                # cluster is the value, so no later letter is a flag of its
                # own and the next argument is not consumed (`-t=` is the
                # title `=`, not a title taken from the next argument).
                return None, 1
            if index + 1 < len(argv):
                return None, 2
            return None, 1

        # A shorthand this shim does not know. gh will refuse the call, but
        # the shim cannot know where its value ends, so it refuses too.
        raise Refusal(
            f"this call uses {_safe(argument)}, a flag the shim does not know; it cannot "
            "tell which repository the call is about, so it refuses it"
        )
    return None, 1


def _repo_from_flag(argv: list[str]) -> str | None:
    """The `--repo owner/name` a call names, if it names one.

    The last one wins: gh's `--repo` is a plain string flag, and the last
    value set is the value gh uses.

    The short form is read in every shape gh accepts it -- `-R owner/name`,
    `-Rowner/name` and `-R=owner/name` -- because a shape this function
    does not understand is a shape the wall does not see, and a call that
    hides its target from the wall is the one the wall exists to stop. A
    repository flag that names nothing is refused rather than ignored: an
    ignored flag is a flag the call did not make, and the fallback to
    `GH_REPO` or to the checkout's own remote would then answer for it.

    A repository flag is read only where a flag can start. The value of a
    value-taking flag is not a flag position: a title of
    `-Rdigithings-ai/digithings` is a title, and reading it as the
    repository made the wall check the title's repository while gh used
    `GH_REPO`. A flag this shim
    does not know is refused, because the shim cannot place its value and a
    flag it cannot place could be the repository. The same is true after
    `--`: gh treats everything after it as a positional, so no repository
    flag starts there.
    """
    command = argv[0] if argv else ""
    value_flags, boolean_flags = _flag_tables(command)
    named: str | None = None
    index = 0
    while index < len(argv):
        argument = argv[index]
        if argument == "--":
            break
        if argument in ("--repo", "-R"):
            if index + 1 >= len(argv) or not argv[index + 1]:
                raise _no_repository_named()
            named = argv[index + 1]
            index += 2
            continue
        if argument.startswith("--repo="):
            named = argument.split("=", 1)[1]
            if not named:
                raise _no_repository_named()
            index += 1
            continue
        if argument.startswith("--"):
            head, separator, _ = argument.partition("=")
            if separator:
                # The value is inside this argument, so gh cannot read it as
                # a separate repository flag.
                index += 1
                continue
            if head in boolean_flags:
                index += 1
                continue
            if head in value_flags:
                # The next argument is this flag's value, whatever it looks
                # like. gh consumes it even when it begins with `-`.
                index += 2 if index + 1 < len(argv) else 1
                continue
            raise Refusal(
                f"this call uses {_safe(argument)}, a flag the shim does not know; it "
                "cannot tell which repository the call is about, so it refuses it"
            )
        if argument.startswith("-") and len(argument) > 1:
            found, consumed = _short_flag_repo(
                argument, value_flags, boolean_flags, argv, index
            )
            if found is not None:
                named = found
            index += consumed
            continue
        index += 1
    return named


def _pr_subcommand(argv: list[str]) -> int | None:
    """Where the subcommand of `gh pr` sits in the arguments, if there is one.

    Cobra finds a subcommand by walking the arguments and skipping every
    flag and flag value it meets on the way, so a `gh pr` call may carry a
    flag in front of the subcommand: `gh pr --repo owner/name create` runs
    `create`, and against the repository named in front of it. A check that
    read argv[1] for the subcommand never saw that shape, and a refusal it
    never saw is a pull request it opened.

    The walk uses the flag tables DIG-5415 added, exactly as the repository
    scan does, and answers the index of the first bare argument: that is
    where the subcommand sits. `--repo` and `-R` are the flags of `gh pr`
    itself, so they are valid in front of the subcommand and their value is
    skipped whatever it looks like; the other flag tables are there so a
    known flag is still placed correctly. A flag the shim does not know
    raises rather than is skipped: a flag the shim cannot place is a value
    it cannot place, and whatever sits behind it -- the subcommand
    included -- is a position the wall does not read. Verified against gh
    2.102.0: every shape gh runs in front of the subcommand is in these
    tables, so the refusal is not stricter than gh is.

    The answer is the index, not the subcommand: `create` has the alias
    `new`, and the caller decides what it does with the name it finds.
    """
    value_flags, boolean_flags = _flag_tables("pr")
    index = 1
    while index < len(argv):
        argument = argv[index]
        if argument == "--":
            # After the terminator the arguments are positionals, so the
            # subcommand gh will act on cannot be back there.
            return None
        if argument in ("--repo", "-R"):
            # A flag of `gh pr` itself, so it is valid in front of the
            # subcommand. It takes the next argument with it, whatever
            # that argument looks like.
            if index + 1 >= len(argv):
                return None
            index += 2
            continue
        if argument.startswith("--repo="):
            index += 1
            continue
        if argument.startswith("--"):
            head, separator, _ = argument.partition("=")
            if separator:
                # The value is inside this argument, so the next argument
                # is still in flag position.
                index += 1
                continue
            if head in value_flags:
                # The next argument is this flag's value, whatever it looks
                # like.
                if index + 1 >= len(argv):
                    return None
                index += 2
                continue
            if head in boolean_flags:
                index += 1
                continue
            raise Refusal(
                f"this call uses {_safe(argument)}, a flag the shim does not know; it "
                "cannot tell where the subcommand of the call sits, so it refuses it"
            )
        if argument.startswith("-") and len(argument) > 1:
            _, consumed = _short_flag_repo(
                argument, value_flags, boolean_flags, argv, index
            )
            index += consumed
            continue
        return index
    return None


def current_repo(argv: list[str], env: dict[str, str]) -> str | None:
    """The repository a call is about, as `owner/name`."""
    named = _repo_from_flag(argv)
    if named:
        return named
    from_env = str(env.get("GH_REPO") or "").strip()
    if from_env:
        return from_env
    return _git_remote_repo(Path(os.getcwd()))


def _check_org(repo: str, what: str) -> None:
    """Refuse a repository outside our organization.

    The repository the caller named is redacted before it reaches the
    message: a refusal is printed into the run log, and a caller that put
    a credential where a repository belongs would have it written down.
    """
    owner = repo.split("/", 1)[0] if "/" in repo else repo
    if owner.lower() != ORG.lower():
        raise Refusal(
            f"{what} names {_safe(repo)}, which is outside the {ORG} organization; a seat "
            "never opens a pull request against a repository we do not own"
        )


#: The GraphQL mutation that opens a pull request. The repository it names
#: is inside a query string and cannot be checked honestly, so it is refused
#: outright.
_CREATE_PULL_REQUEST = "createPullRequest"

#: The `gh pr` subcommands that take the number of a pull request.
_PR_SUBCOMMANDS: frozenset[str] = frozenset(
    {
        "assign",
        "checkout",
        "close",
        "comment",
        "diff",
        "edit",
        "labels",
        "merge",
        "ready",
        "reopen",
        "review",
        "view",
    }
)

#: The number of a pull request in a REST path.
_PULLS_NUMBER_RE = re.compile(r"(?:^|/)pulls/(?P<number>\d+)(?:/|$|\?)")

#: The flags of `gh pr` that take a value. The value of such a flag is not
#: the pull request the call is about: `gh pr view --json title 42` is
#: about pull request 42, and reading `title` as the pull request would
#: refuse a call that names one.
_PR_VALUE_FLAGS: frozenset[str] = frozenset(
    {
        "--repo",
        "-R",
        "--json",
        "--jq",
        "--template",
        "--body",
        "-b",
        "--body-file",
        "--title",
        "-t",
        "--comment",
        "-c",
        "--assignee",
        "-a",
        "--reviewer",
        "-r",
        "--label",
        "-l",
        "--milestone",
        "-m",
        "--author",
        "-A",
        "--project",
        "-p",
    }
)


def _path_segments(text: str) -> list[str]:
    """The path segments of an argument, with `.` and `..` resolved.

    A path that walks out of its own directory is resolved before it is
    read, so `repos/digithings-ai/../evilorg/evil/pulls` is read as the
    repository it actually names. The comparison is on the path as GitHub
    will see it, not on the text as it was typed.
    """
    segments: list[str] = []
    for segment in str(text).replace("\\", "/").split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            if segments:
                segments.pop()
            continue
        segments.append(segment)
    return segments


def _input_files(argv: list[str]) -> list[Path]:
    """The files `gh api --input` would send."""
    files: list[Path] = []
    for index, argument in enumerate(argv):
        value: str | None = None
        if argument == "--input" and index + 1 < len(argv):
            value = argv[index + 1]
        elif argument.startswith("--input="):
            value = argument.split("=", 1)[1]
        if value:
            files.append(Path(value).expanduser())
    return files


def check_pull_request_target(argv: list[str], env: dict[str, str]) -> list[str]:
    """Refuse a pull request against a repository we do not own.

    Two shapes make a pull request: `gh pr create` and `gh api` against the
    pulls endpoint. The GraphQL mutation is refused outright, because the
    repository it names is inside a query string and cannot be checked
    honestly -- and "cannot be checked" is a reason to refuse, not a reason
    to allow.
    """
    notes: list[str] = []
    if not argv:
        return notes
    command = argv[0]
    if command == "pr":
        subcommand = _pr_subcommand(argv)
        if subcommand is not None and argv[subcommand] in ("create", "new"):
            repo = current_repo(argv, env)
            if not repo:
                raise Refusal(
                    "the repository for this pull request could not be identified, so it cannot "
                    f"be checked against the {ORG} organization; pass --repo owner/name"
                )
            _check_org(repo, "the pull request")
            notes.append(f"pull request against {_safe(repo)}")
        return notes
    if command != "api":
        return notes

    for argument in argv[1:]:
        segments = _path_segments(argument)
        for index, segment in enumerate(segments):
            if segment.lower() != "repos":
                continue
            if index + 2 >= len(segments):
                continue
            owner = segments[index + 1]
            repo_name = segments[index + 2]
            rest = segments[index + 3] if index + 3 < len(segments) else ""
            if not rest.lower().startswith("pulls"):
                continue
            if owner.startswith("{"):
                repo = current_repo(argv, env)
                if not repo:
                    raise Refusal(
                        "the repository for this pull request could not be identified, so it "
                        f"cannot be checked against the {ORG} organization"
                    )
                _check_org(repo, "the pull request")
            else:
                _check_org(f"{owner}/{repo_name}", "the pull request")
            notes.append(f"pull request against {_safe(f'{owner}/{repo_name}')}")

    bodies = [" ".join(argv[1:])]
    for path in _input_files(argv):
        try:
            bodies.append(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            # A body that cannot be read cannot be checked. The mutation is
            # refused on sight further down, so an unreadable file is only a
            # problem when it hides the mutation.
            continue
    if any(_CREATE_PULL_REQUEST in body for body in bodies):
        raise Refusal(
            "a GraphQL createPullRequest cannot be checked against the "
            f"{ORG} organization; use `gh pr create` against a {ORG} repository"
        )
    return notes


# ---------------------------------------------------------------------------
# the host and the pull request
# ---------------------------------------------------------------------------


def check_host_flags(argv: list[str]) -> None:
    """Refuse a call that names a host we do not control.

    The token the broker mints is a credential for one host. A call that
    chooses the host itself can carry that credential somewhere it does not
    belong, so the flag that chooses it is refused rather than honoured.
    """
    for argument in argv:
        if argument == "--hostname" or argument.startswith("--hostname="):
            raise Refusal(
                "this call names a GitHub host of its own; the broker's token only ever "
                "goes to the one host we control"
            )


def refuse_token_print(argv: list[str]) -> None:
    """Refuse `gh auth token`.

    The token the broker minted is in the environment of the call. Printing
    it puts it in a file, a log or a paste, where it is no longer scoped to
    the run and no longer in the chain that keeps it scoped.
    """
    if len(argv) > 1 and argv[0] == "auth" and argv[1] == "token":
        raise Refusal(
            "the token in this environment is scoped to this run; printing it takes it "
            "out of that scope, so the shim will not print it"
        )


def _as_pr_number(text: str) -> int | None:
    """A pull request number, when the text is one."""
    stripped = str(text).strip()
    if stripped.isdigit():
        try:
            return int(stripped)
        except ValueError:  # pragma: no cover - isdigit already answered
            return None
    return None


def pr_number(argv: list[str]) -> int | None:
    """The pull request a call is about, when the call names one.

    A review token is bound to one pull request, so the shim has to say
    which one it is about, and it has to check afterwards that the call it
    makes is about that same pull request.

    The number is the first bare argument that is a number. A bare
    argument that is not one is not the number -- a branch name is not,
    and neither is the value of a flag -- so the search goes on rather
    than stopping at the first thing it cannot read.
    """
    if argv and argv[0] == "pr":
        subcommand = _pr_subcommand(argv)
        if subcommand is not None and argv[subcommand] in _PR_SUBCOMMANDS:
            skip = False
            for argument in argv[subcommand + 1:]:
                if skip:
                    skip = False
                    continue
                if argument.startswith("-"):
                    # A flag that takes a value takes the next argument with
                    # it, so the value is not read as the pull request.
                    if argument in _PR_VALUE_FLAGS:
                        skip = True
                    continue
                number = _as_pr_number(argument)
                if number is not None:
                    return number
            return None
    if argv and argv[0] == "api":
        for argument in argv[1:]:
            for match in _PULLS_NUMBER_RE.finditer(argument):
                return int(match.group("number"))
    return None


# ---------------------------------------------------------------------------
# the token
# ---------------------------------------------------------------------------


def _credential_run_id(run_jwt: str) -> str:
    """The run a credential names, read without verifying it.

    The broker verifies the credential against the Paperclip API; this only
    says which run the shim asked about, so that an answer about another run
    is refused.
    """
    try:
        claims = decode_jwt_claims(run_jwt)
    except (AuthError, ValueError, TypeError):
        return ""
    return str(claims.get("run_id") or "")


def request_token(env: dict[str, str], *, pr: int | None = None) -> tuple[str, dict[str, Any]]:
    """Ask the broker for a token for this run.

    The answer is checked before it is used: it has to be an answer at all,
    it has to carry a token, and it has to be an answer about *this* run.
    The run is read out of the credential the shim presented, not out of
    anything the caller wrote, so an answer about another run is refused.
    """
    run_jwt = run_credential(env)
    if not run_jwt:
        raise AuthRefusal(
            "no run credential is in the environment, so no token can be asked for"
        )
    from . import client as broker_client

    try:
        answer = broker_client.github_token(
            run_jwt,
            socket_path=BROKER_SOCKET,
            pr_number=pr,
        )
    except Exception as exc:  # the client raises a BrokerError of its own
        raise BrokerUnavailable(f"the broker did not answer: {exc}") from exc
    if not answer.get("ok"):
        raise Refusal(_safe(answer.get("error") or "the broker refused"))
    token = str(answer.get("token") or "")
    if not token:
        raise Refusal("the broker answered without a token")
    expected = _credential_run_id(run_jwt)
    answered = str(answer.get("run_id") or "")
    if expected and answered and expected != answered:
        raise Refusal("the broker answered for a different run")
    return token, answer


class BrokerUnavailable(Exception):
    """The broker is not answering, so the call cannot be made safely."""


def empty_gh_config_dir(env: dict[str, str]) -> Path:
    """An empty directory for `GH_CONFIG_DIR`.

    `gh` reads its configuration from here. An empty directory means it reads
    none: the host's own `gh` configuration -- with whatever credentials the
    host keeps in it -- is not in the room.

    The directory is emptied by taking it away and making it again, not by
    unlinking what is inside it. A symlink inside it is removed rather than
    followed, and a directory that is not ours is refused rather than
    emptied: the shim never deletes a file it did not make.
    """
    base = run_tmp(env)
    if base.is_symlink():
        raise Refusal(
            f"the run scratch directory {_safe(base)} is a symlink; the shim will not "
            "use a directory it did not make"
        )
    try:
        base.mkdir(parents=True, exist_ok=True)
        base.chmod(0o700)
    except OSError as exc:
        raise Refusal(
            f"the run scratch directory {_safe(base)} cannot be made: {exc}"
        ) from exc
    target = base / "gh"
    if target.is_symlink():
        # Unlinking a symlink costs the caller the link and nothing else:
        # the path it pointed at is not touched.
        try:
            target.unlink()
        except OSError as exc:
            raise Refusal(
                f"the configuration directory {_safe(target)} cannot be replaced: {exc}"
            ) from exc
    elif target.exists():
        try:
            shutil.rmtree(target)
        except OSError as exc:
            raise Refusal(
                f"the configuration directory {_safe(target)} cannot be emptied: {exc}"
            ) from exc
    try:
        target.mkdir(parents=True, exist_ok=True)
        target.chmod(0o700)
    except OSError as exc:
        raise Refusal(
            f"the configuration directory {_safe(target)} cannot be made: {exc}"
        ) from exc
    return target


# ---------------------------------------------------------------------------
# the call
# ---------------------------------------------------------------------------


def plan_call(argv: list[str], env: dict[str, str], *, mint: bool = True) -> Plan:
    """Decide what to do with one `gh` call.

    The rewrite and the refusals always happen. While the broker is in
    charge, the host's own credentials are not in the room whatever the
    caller looks like, and the only credential a call runs with is the one
    the broker minted for this run. A caller that cannot show a run
    credential gets no credential at all, rather than the host's. In `host`
    mode the call is passed through unchanged: that mode is the rollback,
    and the flag that turns it on belongs to Chris.
    """
    rewritten, field_notes = rewrite_fields(argv)
    rewritten, body_notes = rewrite_body_flags(rewritten)
    notes = field_notes + body_notes
    notes.extend(check_pull_request_target(rewritten, env))
    check_host_flags(rewritten)

    plan = Plan(argv=rewritten, notes=notes)
    if auth_mode(env) != APP_MODE:
        plan.notes.append("host auth mode: the call is passed through unchanged")
        return plan

    if not mint:
        raise AuthRefusal(
            "the broker is in charge and this call carries no run credential, so the "
            "host's own credential is not used either"
        )

    # The host's own tokens are removed and `gh` is pointed at an empty
    # configuration, so the only credential in the room is the one the
    # broker minted for this run.
    plan.removed_env = HOST_CREDENTIAL_ENV
    config_dir = empty_gh_config_dir(env)
    plan.env["GH_CONFIG_DIR"] = str(config_dir)

    refuse_token_print(rewritten)
    pr = pr_number(rewritten)
    token, answer = request_token(env, pr=pr)
    bound_pr = answer.get("pr_number")
    if bound_pr is not None:
        if pr is None:
            raise Refusal(
                "the token is for a pull request and this call is not about one"
            )
        if int(bound_pr) != int(pr):
            raise Refusal(
                f"the token is for pull request {int(bound_pr)} and this call is about "
                f"pull request {int(pr)}"
            )
    plan.env["GH_TOKEN"] = token
    plan.notes.append("app auth mode: the call runs with a per-run token from the broker")
    return plan


def child_env(env: dict[str, str], plan: Plan) -> dict[str, str]:
    """The environment the guard and the real `gh` run with."""
    result = {key: value for key, value in env.items() if key not in plan.removed_env}
    result.update(plan.env)
    # The marker says the shim is in the chain, so a shim that is called by a
    # shim refuses instead of calling itself for ever.
    result[SHIM_MARKER] = "1"
    return result


def exec_guard(guard: Path, argv: list[str], env: dict[str, str]) -> int:
    """Hand the call to the guard, which hands it to the real `gh`."""
    if not guard.exists():
        sys.stderr.write(
            f"dt-broker: the gh guard is not at {guard}; refusing to call gh directly\n"
        )
        return EXIT_INTERNAL
    try:
        os.execve(str(guard), [str(guard), *argv], env)
    except ValueError as exc:
        sys.stderr.write(
            f"dt-broker: refusing: the call carries something that cannot be passed to a "
            f"program: {exc}\n"
        )
        return EXIT_USAGE
    except OSError as exc:
        sys.stderr.write(f"dt-broker: the gh guard could not be run: {exc}\n")
        return EXIT_INTERNAL
    return EXIT_INTERNAL  # pragma: no cover - execve does not return


def main(argv: list[str] | None = None, env: dict[str, str] | None = None) -> int:
    """Run one `gh` call."""
    environment = dict(os.environ if env is None else env)
    call = list(sys.argv[1:] if argv is None else argv)

    try:
        guard = guard_path(environment)
    except Refusal as exc:
        sys.stderr.write(f"dt-broker: refusing: {exc}\n")
        return EXIT_REFUSED

    if str(environment.get(SHIM_MARKER) or "").strip():
        sys.stderr.write(
            "dt-broker: refusing: the gh shim is already in the chain; it will not call itself\n"
        )
        return EXIT_REFUSED

    try:
        plan = plan_call(call, environment, mint=bool(run_credential(environment)))
    except AuthRefusal as exc:
        sys.stderr.write(f"dt-broker: refusing: {exc}\n")
        return EXIT_AUTH
    except Refusal as exc:
        sys.stderr.write(f"dt-broker: refusing: {exc}\n")
        return EXIT_REFUSED
    except BrokerUnavailable as exc:
        sys.stderr.write(
            f"dt-broker: {exc}; the call is not made with host credentials\n"
        )
        return EXIT_UNAVAILABLE

    for note in plan.notes:
        sys.stderr.write(f"dt-broker: {note}\n")
    return exec_guard(guard, plan.argv, child_env(environment, plan))


def main_gh() -> int:
    """The entry point the `gh` wrapper script calls."""
    return main()


__all__ = [
    "EXIT_AUTH",
    "EXIT_INTERNAL",
    "EXIT_OK",
    "EXIT_REFUSED",
    "EXIT_UNAVAILABLE",
    "EXIT_USAGE",
    "AuthRefusal",
    "Refusal",
    "auth_mode",
    "check_host_flags",
    "check_pull_request_target",
    "current_repo",
    "is_seat_process",
    "main",
    "plan_call",
    "pr_number",
    "refuse_token_print",
    "rewrite_body_flags",
    "rewrite_fields",
    "run_credential",
]
