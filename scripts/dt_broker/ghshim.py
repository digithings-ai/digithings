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

import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .core import APP_MODE, DEFAULT_SOCKET_PATH, read_auth_mode

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

#: The socket the broker listens on. `DT_BROKER_SOCKET` overrides it, which
#: is how the tests point the shim at a broker of their own.
DEFAULT_SOCKET = str(DEFAULT_SOCKET_PATH)

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
    """True when this process is a seat run.

    The guard uses the same three variables to decide whether it is talking
    to a seat, so the two agree about who is being protected.
    """
    return any(
        str(env.get(name) or "").strip()
        for name in ("PAPERCLIP_AGENT_ID", "PAPERCLIP_RUN_ID", "PAPERCLIP_TASK_ID")
    )


def socket_path(env: dict[str, str]) -> str:
    """Where the broker listens."""
    return str(env.get("DT_BROKER_SOCKET") or DEFAULT_SOCKET)


def run_tmp(env: dict[str, str]) -> Path:
    """The scratch directory for this run.

    `GH_CONFIG_DIR` points inside it, so the `gh` that runs reads an empty
    configuration and not the host's.
    """
    explicit = env.get("DT_BROKER_RUN_TMP")
    if explicit:
        return Path(explicit).expanduser()
    run_id = str(env.get("PAPERCLIP_RUN_ID") or "no-run")
    return Path(tempfile.gettempdir()) / f"dt-broker-{run_id}"


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
            raise Refusal(f"{argument} needs a key=value pair, not {argv[index + 1]!r}")
        key, raw = parts
        return _FieldArg(flag=FIELD_FLAGS[argument], key=key, raw=raw, shape="spaced"), index + 1
    if argument.startswith("--") and "=" in argument:
        head, _, tail = argument.partition("=")
        canonical = FIELD_FLAGS.get(head)
        if canonical is None:
            return None
        parts = _split_field(tail)
        if parts is None:
            raise Refusal(f"{head} needs a key=value pair, not {tail!r}")
        key, raw = parts
        return _FieldArg(flag=canonical, key=key, raw=raw, shape="long"), index
    if argument.startswith("-") and not argument.startswith("--") and len(argument) > 2:
        head = argument[:2]
        canonical = FIELD_FLAGS.get(head)
        if canonical is None:
            return None
        parts = _split_field(argument[2:])
        if parts is None:
            raise Refusal(f"{head} needs a key=value pair, not {argument[2:]!r}")
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
        raise Refusal(f"the file {path} cannot be read: {exc}") from exc
    if size > MAX_FIELD_BYTES:
        raise Refusal(f"the file {path} is too large to send as a field ({size} bytes)")
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise Refusal(f"the file {path} is not readable text: {exc}") from exc


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
        if field_arg.raw.startswith("@"):
            content = _read_field_file(field_arg.raw[1:])
            out.extend(field_arg.render(TEXT_FLAGS.get(field_arg.flag, "-f"), content))
            notes.append(f"expanded {field_arg.key} from {field_arg.raw}")
            index += 1
            continue
        if field_arg.key in BODY_KEYS and _looks_like_a_file(field_arg.raw):
            raise Refusal(
                f"the {field_arg.key} field is a path to a file ({field_arg.raw}); the shim "
                "will not post a path where a body belongs. Use `@<path>` to send the "
                "file's contents."
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
            if value.startswith("@"):
                content = _read_field_file(value[1:])
                out.extend([argument, content])
                notes.append(f"expanded the body from {value}")
                index += 2
                continue
            if _looks_like_a_file(value):
                raise Refusal(
                    f"the body is a path to a file ({value}); the shim will not post a path "
                    "where a body belongs. Use `--body-file <path>` to send the file."
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


def _repo_from_flag(argv: list[str]) -> str | None:
    """The `--repo owner/name` a call names, if it names one.

    The last one wins: gh's `--repo` is a plain string flag, and the last
    value set is the value gh uses.
    """
    named: str | None = None
    for index, argument in enumerate(argv):
        if argument in ("--repo", "-R") and index + 1 < len(argv):
            named = argv[index + 1]
        elif argument.startswith("--repo="):
            named = argument.split("=", 1)[1]
    return named


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
    """Refuse a repository outside our organization."""
    owner = repo.split("/", 1)[0] if "/" in repo else repo
    if owner.lower() != ORG.lower():
        raise Refusal(
            f"{what} names {repo}, which is outside the {ORG} organization; a seat never "
            "opens a pull request against a repository we do not own"
        )


#: The pulls endpoint of the REST API, wherever it sits in an argument. The
#: endpoint of `gh api` is a positional argument, and it may sit behind a
#: flag, so every argument is scanned rather than only the first one.
_PULLS_PATH_RE = re.compile(
    r"(?:^|/)repos/(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+)/pulls(?:/|$|\?)"
)

#: The GraphQL mutation that opens a pull request. The repository it names
#: is inside a query string and cannot be checked honestly, so it is refused
#: outright.
_CREATE_PULL_REQUEST = "createPullRequest"


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
    if command == "pr" and len(argv) > 1 and argv[1] in ("create", "new"):
        repo = current_repo(argv, env)
        if not repo:
            raise Refusal(
                "the repository for this pull request could not be identified, so it cannot "
                f"be checked against the {ORG} organization; pass --repo owner/name"
            )
        _check_org(repo, "the pull request")
        notes.append(f"pull request against {repo}")
        return notes
    if command != "api":
        return notes

    for argument in argv[1:]:
        for match in _PULLS_PATH_RE.finditer(argument):
            owner = match.group("owner")
            repo_name = match.group("repo")
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
            notes.append(f"pull request against {owner}/{repo_name}")

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
# the token
# ---------------------------------------------------------------------------


def request_token(env: dict[str, str]) -> str:
    """Ask the broker for a token for this run."""
    run_jwt = str(env.get("PAPERCLIP_API_KEY") or "")
    if not run_jwt:
        raise Refusal("no run credential is in the environment, so no token can be asked for")
    from . import client as broker_client

    try:
        answer = broker_client.github_token(run_jwt, socket_path=socket_path(env))
    except Exception as exc:  # the client raises a BrokerError of its own
        raise BrokerUnavailable(f"the broker did not answer: {exc}") from exc
    if not answer.get("ok"):
        raise Refusal(str(answer.get("error") or "the broker refused"))
    token = str(answer.get("token") or "")
    if not token:
        raise Refusal("the broker answered without a token")
    return token


class BrokerUnavailable(Exception):
    """The broker is not answering, so the call cannot be made safely."""


def empty_gh_config_dir(env: dict[str, str]) -> Path:
    """An empty directory for `GH_CONFIG_DIR`.

    `gh` reads its configuration from here. An empty directory means it reads
    none: the host's own `gh` configuration -- with whatever credentials the
    host keeps in it -- is not in the room.
    """
    target = run_tmp(env) / "gh"
    target.mkdir(parents=True, exist_ok=True)
    try:
        target.chmod(0o700)
    except OSError:
        pass
    for child in target.iterdir():
        try:
            if child.is_dir():
                continue
            child.unlink()
        except OSError:
            continue
    return target


# ---------------------------------------------------------------------------
# the call
# ---------------------------------------------------------------------------


def plan_call(argv: list[str], env: dict[str, str], *, mint: bool = True) -> Plan:
    """Decide what to do with one `gh` call.

    The rewrite and the refusals always happen. The token is only asked for
    when this is a seat run in `app` mode: a call that is not a seat run has
    no run to be scoped to, and `host` mode is the rollback.
    """
    rewritten, field_notes = rewrite_fields(argv)
    rewritten, body_notes = rewrite_body_flags(rewritten)
    notes = field_notes + body_notes
    notes.extend(check_pull_request_target(rewritten, env))

    plan = Plan(argv=rewritten, notes=notes)
    if not mint:
        plan.notes.append("not a seat run: the call is passed through unchanged")
        return plan
    if auth_mode(env) != APP_MODE:
        plan.notes.append("host auth mode: the call is passed through unchanged")
        return plan

    token = request_token(env)
    config_dir = empty_gh_config_dir(env)
    plan.env["GH_TOKEN"] = token
    plan.env["GH_CONFIG_DIR"] = str(config_dir)
    # The host's own tokens are removed, so the call cannot fall back to
    # them: the only credential in the room is the one the broker minted.
    plan.removed_env = (
        "GITHUB_TOKEN",
        "GH_ENTERPRISE_TOKEN",
        "GITHUB_ENTERPRISE_TOKEN",
    )
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
        plan = plan_call(call, environment, mint=is_seat_process(environment))
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
    "Refusal",
    "auth_mode",
    "check_pull_request_target",
    "current_repo",
    "is_seat_process",
    "main",
    "plan_call",
    "rewrite_body_flags",
    "rewrite_fields",
]
