"""The local-stack service catalogue.

Every default URL in ``BUILTIN_CHECKS`` is **sourced**: the ``source`` field
records the file and line, or the documented tool default, it came from. A
reader can re-derive each one. An unsourced default is a defect, so the ones we
could not source are declared with ``url=None`` and a ``requires`` key instead
of an invented path -- they report ``skipped`` until configured and never
``passed``.

On top of the built-in list this module **feature-detects** the S1 config
contract so that when the contract lands (DIG-2759 / DIG-2769, two competing
implementations) the gate picks it up with no code change. Two shapes are
accepted because two S1 PRs are open and this leaf must not invent a third:

* ``config/contract/services.yaml``  (PR #5352)
* ``config/contract/contract.yaml``  (PR #5359)

Every default URL here addresses the loopback host, and the only part of it
that moves is the port, which an operator's knob carries. A knob value that
is not a port number is refused (:class:`InvalidPort`) instead of being
substituted: ``8000@evil.com`` is a legal userinfo string, so
``urlsplit("http://127.0.0.1:8000@evil.com/healthz")`` reports the host as
``evil.com`` and the probe would leave this machine.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.parse
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

try:  # imported as part of a package
    from .supabase_ports import DEFAULT_API_PORT, PORT_ENV
except ImportError:  # imported as a plain module
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from supabase_ports import DEFAULT_API_PORT, PORT_ENV

#: The Supabase API port the local stack probes. The whole Supabase port set
#: moves with it (see localstack.supabase_ports), so one knob keeps the gate
#: and the instance the CLI started on the same port. Only the PORT is
#: templated - the host stays 127.0.0.1, and the substituted port is
#: validated, so the gate can never point off this machine.
_SUPABASE_API_PORT = "${%s:-%d}" % (PORT_ENV, DEFAULT_API_PORT)

PROFILES: tuple[str, ...] = ("core", "quant", "chat", "trace", "all")

#: Contract paths probed, in priority order. Both are read-only probes.
CONTRACT_PATHS: tuple[str, ...] = (
    "config/contract/services.yaml",
    "config/contract/contract.yaml",
)

#: Statuses a check can report. ``skipped`` is load-bearing: it is how a check
#: that could not run is distinguished from one that passed.
PASSED = "passed"
FAILED = "failed"
SKIPPED = "skipped"

#: The host every built-in probe stays on.
LOOPBACK_HOST = "127.0.0.1"

#: A port number: ASCII digits, 1-65535. ``str.isdigit`` is not enough -- it
#: accepts non-ASCII digits -- and ``int()`` is not enough either: it reads
#: ``8_000`` and ``+8000`` as numbers a URL may not carry. The pattern is
#: anchored with ``fullmatch`` (never ``$``, which also accepts a trailing
#: newline).
_PORT_RE = re.compile(r"[0-9]{1,5}")

#: The lowest port a probe may address.
MIN_PORT = 1

#: The highest port a probe may address.
MAX_PORT = 65535


class InvalidPort(ValueError):
    """A port knob carried something that is not a port.

    Raised instead of building a URL out of the value. The gate opens the URL
    it resolves, so a knob value is the one thing that can move a probe off
    this machine: ``urlsplit("http://127.0.0.1:8000@evil.com/healthz")``
    reports the host as ``evil.com``.

    A refusal, not a fallback and not a skip: the operator sees which knob is
    wrong, and the gate does not report a check it never ran as a pass
    (DIG-4911).
    """


@dataclass(frozen=True)
class Check:
    """One health probe."""

    name: str
    kind: str
    #: Absolute or relative URL, or ``None`` when the check needs configuration.
    url: str | None
    #: Which ``--profile`` values include this check.
    profiles: tuple[str, ...]
    #: Where the default came from -- a ``file:line`` or a documented default.
    source: str
    #: Config key that must be set for this check to run. ``None`` = always runnable.
    requires: str | None = None
    method: str = "GET"
    expect_status: tuple[int, ...] = (200,)
    #: Path used to read back a value written by a ``roundtrip`` check.
    read_path: str | None = None
    #: Probe path appended to a ``requires`` base URL. ``None`` = use the
    #: configured URL exactly as given (the default, and what every check
    #: except dashboard-api relies on).
    path: str | None = None

    def in_profile(self, profile: str) -> bool:
        return profile in self.profiles or "all" in self.profiles

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "url": self.url,
            "profiles": list(self.profiles),
            "source": self.source,
            "requires": self.requires,
            "method": self.method,
            "expect_status": list(self.expect_status),
            "read_path": self.read_path,
            "path": self.path,
        }


_ALL = ("all",)
_CORE = ("core",)
_QUANT = ("core", "quant")
_CHAT = ("core", "chat")
_TRACE = ("core", "trace")


BUILTIN_CHECKS: tuple[Check, ...] = (
    # ── supabase (plan section 6: REST + auth) ───────────────────────────────
    # Supabase CLI local defaults, documented in the plan. The API port is a
    # knob (DT_SUPABASE_PORT): the whole port set moves with it, because
    # core-local already holds the canonical 54321-54324 set and the CLI has
    # no port flags of its own. The host stays 127.0.0.1: the gate must never
    # be able to point off this machine.
    Check(
        name="supabase-rest",
        kind="http",
        url="http://127.0.0.1:" + _SUPABASE_API_PORT + "/rest/v1/",
        profiles=_CORE,
        source=(
            "localstack/supabase_ports.py: the API port of the Supabase set the "
            "local stack starts (default %d)" % DEFAULT_API_PORT
        ),
    ),
    Check(
        name="supabase-auth",
        kind="http",
        url="http://127.0.0.1:" + _SUPABASE_API_PORT + "/auth/v1/health",
        profiles=_CORE,
        source=(
            "localstack/supabase_ports.py: the API port of the Supabase set the "
            "local stack starts (default %d)" % DEFAULT_API_PORT
        ),
    ),
    # ── python services: every path below read out of the service source ────
    Check(
        name="digikey",
        kind="http",
        url="http://127.0.0.1:8005/healthz",
        profiles=_ALL,
        source="digikey/src/digikey/server.py:116",
    ),
    Check(
        name="digigraph",
        kind="http",
        url="http://127.0.0.1:${DT_DIGIGRAPH_PORT:-8000}/healthz",
        profiles=_ALL,
        # The HOST-published port, and the only one a probe can reach. compose
        # publishes digigraph as 127.0.0.1:8000 -> 8000 (docker-compose.yml),
        # and the host dev server (scripts/run_local.sh) binds 18000 so it does
        # not collide with the containers. A host where 8000 already belongs to
        # another stack makes this probe read that other service and report a
        # healthy digigraph as FAIL: measured, 8000 answered 204 (a woodpecker
        # server) while the real digigraph on 18000 answered 200.
        #
        # DT_DIGIGRAPH_PORT is the knob for the port digigraph actually serves;
        # the default follows the compose publish port. The ${...:-default}
        # syntax is expanded by _expand_env() at resolve time, so an operator
        # who exports the knob moves the probe with the service. It takes a
        # port number: the gate reads the process environment, not the root
        # .env, and a value that is not a port is refused (InvalidPort)
        # rather than substituted -- '8000@evil.com' would make the probe
        # leave this machine.
        #
        # The value is validated as a plain integer port *before* it is
        # templated: ASCII digits only, 1-65535, and an empty value keeps the
        # default. Anything else is refused, never templated and never
        # silently replaced by the default. The reason is that a value that is
        # not a port does not make the URL unparseable - it makes the URL
        # point somewhere else: "8000@evil.com" expands to
        # "http://127.0.0.1:8000@evil.com/healthz", where "127.0.0.1:8000" is
        # userinfo and the host is "evil.com" (same for "8000/@evil.com" and
        # "8000#x"). The resolved URL is then parsed and refused unless it is
        # still the loopback probe on the validated port, so the guarantee
        # test_builtin_urls_are_labelled_local_loopback relies on holds on the
        # URL the probe actually opens and not only on the template.
        #
        # Only the PORT is templated, for the digichat reason: templating the
        # host would let this gate point off the developer's machine, and
        # test_builtin_urls_are_labelled_local_loopback requires a provably
        # loopback default.
        #
        # Not to be confused with the contract key DIGIGRAPH_PORT ("the port
        # the digigraph dev server binds to"), which nothing reads today.
        source=(
            "digigraph/src/digigraph/server.py:332 serves /healthz; "
            "docker-compose.yml digigraph ports: 127.0.0.1:8000:8000"
        ),
    ),
    Check(
        name="digisearch",
        kind="http",
        url="http://127.0.0.1:8002/healthz",
        profiles=_ALL,
        source="digisearch/src/digisearch/server.py:558",
    ),
    Check(
        name="digivault",
        kind="http",
        url="http://127.0.0.1:8004/healthz",
        profiles=("core", "quant", "all"),
        source="digivault/src/digivault/server.py:532",
    ),
    Check(
        name="digitrace",
        kind="http",
        url="http://127.0.0.1:8003/healthz",
        profiles=_TRACE,
        source="digitrace/src/digitrace/server.py:59",
    ),
    Check(
        name="digichat",
        kind="http",
        url="http://127.0.0.1:${DIGICHAT_PUBLISH_PORT:-3005}/api/health",
        profiles=_CHAT,
        # The HOST-published port, not the container port. compose publishes
        # 127.0.0.1:${DIGICHAT_PUBLISH_PORT:-3005} -> 3000 (docker-compose.yml),
        # so probing 3000 reports a healthy container as "Connection refused".
        # The Makefile's digichat-health target curls 3000 because that target
        # probes the *host* dev server (make digichat-dev), a different run mode.
        #
        # Only the PORT is templated. DIGICHAT_PUBLISH_HOST may be set to 0.0.0.0
        # for a LAN bind, but a bind on 0.0.0.0 still answers on 127.0.0.1, and
        # test_builtin_urls_are_labelled_local_loopback requires a default that
        # is provably loopback. Templating the host would let this gate point off
        # the developer's machine. The substituted port is validated, so the
        # knob cannot carry a host either.
        # The ${...:-default} syntax mirrors compose's own line and is expanded
        # by _expand_env() at resolve time, so the default follows the variable.
        source=(
            "docker-compose.yml digichat ports: "
            '"${DIGICHAT_PUBLISH_HOST:-127.0.0.1}:${DIGICHAT_PUBLISH_PORT:-3005}:3000"'
        ),
    ),
    Check(
        name="dashboard-api",
        kind="http",
        url="http://127.0.0.1:${DT_DASHBOARD_API_PORT:-8887}/healthz",
        profiles=("core", "chat", "all"),
        # /healthz, never the origin. dashboard-api routes only /healthz,
        # /ledger, /v1/tables/* and the MCP path; every other GET falls
        # through to errorResponse("bad_request", "unknown route ...") at
        # :244/:255, so probing the origin alone reads 400 from a healthy
        # service and the gate reports it as down. Measured on the running
        # local stack: 127.0.0.1:8887/ -> 400 unknown route,
        # 127.0.0.1:8887/healthz -> 200 {"ok":true,"service":"dashboard-api"}.
        #
        # DIG-2697 (2026-10-15, board answer on card 2f3d600f): this row
        # used to require DT_DASHBOARD_API_URL, which has NO producer
        # anywhere in the repo, so resolve() returned (None, "... not set"),
        # the check was permanently SKIPPED, and health.py counts a skipped
        # check as a failure under REQUIRE_ALL=1 -- so that one key made
        # the gate unreachable. A literal loopback default removes the
        # no-producer condition instead of masking it.
        #
        # Only the PORT is templated, for the digichat reason: templating
        # the host would let this gate point off the developer's machine,
        # and test_builtin_urls_are_labelled_local_loopback requires a
        # provably loopback default. The substituted port is validated, so
        # the knob cannot carry a host either.
        #
        # 8887 is the measured wrangler-dev port for dashboard-api (workerd
        # listening there, answering for this service). orchestrate.py passes
        # no --port, so the default follows the variable rather than the
        # worker argv. S3 still owns the full port table (PR #5353); when it
        # lands it supersedes this default rather than replacing the row.
        source=(
            "apps/dashboard-api/src/index.ts:174 serves /healthz; "
            ":244/:255 answer 400 on any other path"
        ),
    ),
    # ── checks with no source we are willing to fake ────────────────────────
    Check(
        name="mcp-tools-list",
        kind="jsonrpc",
        url=None,
        profiles=("core", "quant", "all"),
        source=(
            "no MCP HTTP tools/list path is declared in our source; the mcp "
            "library owns the protocol and S3 owns the transport port"
        ),
        requires="DT_MCP_URL",
        method="POST",
    ),
    Check(
        name="digitrace-ingest-roundtrip",
        kind="roundtrip",
        url=None,
        profiles=_TRACE,
        source=(
            "digitrace/src/digitrace/server.py exposes /healthz and /v1/status "
            "only; there is no ingest route in source to round-trip against"
        ),
        requires="DT_DIGITRACE_INGEST_URL",
    ),
    Check(
        name="r2-put-get",
        kind="roundtrip",
        url=None,
        profiles=_ALL,
        source="R2 local binding ids are generated by S3 (PR #5353)",
        requires="DT_R2_URL",
    ),
    Check(
        name="kv-put-get",
        kind="roundtrip",
        url=None,
        profiles=_ALL,
        source="KV local binding ids are generated by S3 (PR #5353)",
        requires="DT_KV_URL",
    ),
    Check(
        name="d1-put-get",
        kind="roundtrip",
        url=None,
        profiles=_ALL,
        source="D1 local binding ids are generated by S3 (PR #5353)",
        requires="DT_D1_URL",
    ),
)


def _load_yaml(path: Path) -> Any:
    """Load YAML, or JSON if the file is JSON. Never guesses."""
    text = path.read_text(encoding="utf-8")
    try:
        import yaml
    except ModuleNotFoundError as exc:  # pragma: no cover - env guard
        raise RuntimeError(
            f"contract {path} found but PyYAML is not installed; "
            "run through the repo venv (uv run --frozen)"
        ) from exc
    try:
        return yaml.safe_load(text)
    except Exception:  # pragma: no cover - fall through to the JSON reader
        return json.loads(text)


def _normalise_profiles(raw: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    if raw is None:
        return default
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, list) and all(isinstance(x, str) for x in raw):
        return tuple(raw)
    return default


def _compose_url(port: Any, path: Any, host: str = "127.0.0.1") -> str | None:
    if port is None:
        return None
    suffix = path if isinstance(path, str) and path.startswith("/") else ""
    return f"http://{host}:{int(port)}{suffix or '/healthz'}"


def checks_from_contract(doc: Any) -> tuple[Check, ...]:
    """Build checks from either accepted S1 contract shape.

    Accepts a bare list, or a mapping whose ``services`` value is the list.
    Per-row keys are tolerant (``url``/``health_url``, ``port``+``health_path``)
    because two S1 PRs are open and neither has merged. Rows we cannot read are
    skipped rather than guessed at.
    """
    rows: Any = doc
    if isinstance(doc, dict):
        rows = doc.get("services")
        if rows is None:
            rows = doc.get("checks")
    if not isinstance(rows, list):
        return ()

    out: list[Check] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("name") or row.get("id")
        if not isinstance(name, str):
            continue
        url = row.get("url") or row.get("health_url")
        if not isinstance(url, str) or not url:
            url = _compose_url(row.get("port"), row.get("health_path"))
        out.append(
            Check(
                name=name,
                kind=str(row.get("kind") or "http"),
                url=url,
                profiles=_normalise_profiles(row.get("profiles"), _ALL),
                source=f"config contract row {name!r}",
                requires=row.get("requires"),
                method=str(row.get("method") or "GET").upper(),
            )
        )
    return tuple(out)


def load_checks(root: Path) -> tuple[tuple[Check, ...], str]:
    """Return ``(checks, origin)`` for the stack rooted at ``root``.

    ``origin`` names where the catalogue came from, so a gate run can always
    say whether it used a contract or the built-in defaults.
    """
    for rel in CONTRACT_PATHS:
        candidate = root / rel
        if not candidate.is_file():
            continue
        checks = checks_from_contract(_load_yaml(candidate))
        if checks:
            return merge_contract(checks), rel
    return BUILTIN_CHECKS, "built-in defaults"


def merge_contract(checks: tuple[Check, ...]) -> tuple[Check, ...]:
    """Overlay contract rows onto the built-ins, matched by name.

    A contract can retune or replace a built-in row. It cannot delete one: the
    plan names the surfaces, so a contract that simply omits ``digichat`` must
    not silently stop probing it.
    """
    by_name = {c.name: c for c in checks}
    merged: list[Check] = []
    for builtin in BUILTIN_CHECKS:
        override = by_name.pop(builtin.name, None)
        if override is None:
            merged.append(builtin)
            continue
        merged.append(
            replace(
                builtin,
                url=override.url or builtin.url,
                profiles=override.profiles,
                method=override.method,
                kind=override.kind if override.kind else builtin.kind,
            )
        )
    merged.extend(by_name.values())
    return tuple(merged)


def select(checks: tuple[Check, ...], profile: str) -> tuple[Check, ...]:
    """Checks in ``profile``; ``all`` selects everything."""
    if profile == "all":
        return checks
    return tuple(c for c in checks if c.in_profile(profile))


#: ``${VAR}`` / ``${VAR:-default}`` in a default URL, matching the syntax the
#: compose files already use for the same variables.
_ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def _port_value(name: str, value: str) -> int:
    """The port ``name`` carries, or refuse.

    A port is ASCII decimal digits only, at most five of them, with a value
    in 1-65535. Anything else is refused with the variable and the value
    named: never templated, and never silently replaced by the default,
    because a value that is not a port does not make the URL unparseable - it
    makes the URL point somewhere else.
    """
    if not _PORT_RE.fullmatch(value):
        raise InvalidPort(
            f"{name}={value!r} is not a port: expected {MIN_PORT}-{MAX_PORT} "
            "written as plain decimal digits"
        )
    port = int(value)
    if not MIN_PORT <= port <= MAX_PORT:
        raise InvalidPort(
            f"{name}={value!r} is not a port: outside {MIN_PORT}-{MAX_PORT}"
        )
    return port


def _assert_loopback_port(url: str, name: str, port: int) -> None:
    """Refuse a resolved URL that is not the loopback probe on ``port``.

    Defence in depth. The value is validated before it is templated, so this
    cannot fire on the shipped templates; it is here so that a change to a
    template (a second host, another expansion, a different default) cannot
    quietly move the probe off the machine. It also catches the shape the
    digit check cannot see on its own: a URL that parses into a host other
    than 127.0.0.1, or into a port other than the validated one.
    """
    split = urllib.parse.urlsplit(url)
    try:
        host = split.hostname
        resolved_port = split.port
    except ValueError:  # a netloc that does not carry a numeric port
        host, resolved_port = None, None
    if host != LOOPBACK_HOST or resolved_port != port:
        raise InvalidPort(
            f"{name} resolved to {url!r}: the probe must stay on "
            f"http://{LOOPBACK_HOST}:{port}"
        )


def _authority_span(url: str) -> tuple[int, int]:
    """The character range of a URL template's authority (the host:port part).

    ``(0, 0)`` when the template carries no ``scheme://`` prefix: a bare
    ``host:port`` string is not a URL and has no authority to point at.
    """
    marker = url.find("://")
    if marker < 0:
        return (0, 0)
    start = marker + 3
    end = len(url)
    for index in range(start, len(url)):
        if url[index] in "/?#":
            end = index
            break
    return (start, end)


def _fills_the_port_slot(url: str, start: int) -> bool:
    """True when the reference at ``start`` stands for the URL's port.

    The port slot is the ``:`` that separates the host from the port inside
    the authority. A reference behind a ``/`` is in the path and one that
    follows ``://`` is the host -- neither of them is a port.
    """
    auth_start, auth_end = _authority_span(url)
    if not (auth_start <= start < auth_end):
        return False
    if start == 0 or url[start - 1] != ":":
        return False
    # '://' is the scheme separator, not the port separator.
    return start < 2 or url[start - 2] != "/"


def _expand_env(url: str | None, config: dict[str, str]) -> str | None:
    """Expand ``${VAR:-default}`` references in a built-in default URL.

    Only applied to the *default* URL. A ``requires`` value is returned exactly
    as configured (see :func:`resolve`), because a caller-configured local
    binding route is keyed on the exact path it supplies.

    A reference that fills the port slot has to carry a port number. The
    value lands in a URL the gate then opens, and a value that is not a port
    is the one thing that can move that URL off this machine: ``8000@evil.com``
    makes ``urlsplit(...).hostname`` read ``evil.com``. So such a value is
    refused loudly (:class:`InvalidPort`) rather than substituted.

    Surrounding whitespace is noise around a number, not a different number:
    the Supabase port knob already strips (localstack.supabase_ports), so the
    gate agrees with it rather than refusing a value the stack accepts.

    The URL that comes out is then parsed and refused unless it is still the
    loopback probe on the validated port (:func:`_assert_loopback_port`), so
    the guarantee holds on the URL the probe actually opens and not only on
    the shape of the value.
    """
    if url is None or "${" not in url:
        return url

    ports: dict[str, int] = {}

    def sub(match: re.Match[str]) -> str:
        name, default = match.group(1), match.group(2)
        # Surrounding whitespace is noise around a number, not a different
        # number: the Supabase port knob already strips (localstack
        # .supabase_ports), so the gate must agree with it.
        value = (config.get(name) or default or "").strip()
        if _fills_the_port_slot(url, match.start()):
            # The value has to be a port before it is templated: a value that
            # is not a port is the one thing that can move the URL off this
            # machine, so it is refused loudly instead of substituted.
            ports[name] = _port_value(name, value)
        return value

    expanded = _ENV_REF.sub(sub, url)
    # Defence in depth: the resolved URL is the one the probe opens, so it is
    # parsed and refused unless it still is the loopback probe on the port the
    # knob was validated to carry.
    for name, port in ports.items():
        _assert_loopback_port(expanded, name, port)
    return expanded


def _with_path(base: str, path: str) -> str:
    """Return ``base`` with ``path`` appended to its URL path.

    Uses the same ``urlsplit``/``urlunsplit`` idiom as ``health.py``'s
    ``read_path`` handling, so query and fragment survive. If ``base`` already
    ends with ``path`` the value is returned unchanged, so an operator who
    exports the full probe URL gets the same URL as one who exports the origin.
    """
    split = urllib.parse.urlsplit(base)
    if split.path == path or split.path.endswith(path):
        return base
    joined = split.path.rstrip("/") + path
    return urllib.parse.urlunsplit(
        (split.scheme, split.netloc, joined, split.query, split.fragment)
    )


def resolve(check: Check, config: dict[str, str]) -> tuple[str | None, str | None]:
    """Resolve a check's URL from configuration.

    Returns ``(url, skip_reason)``. Exactly one is ``None``. A check that needs
    configuration and has none is *skipped with a reason* -- never passed.

    Raises :class:`InvalidPort` when a port knob carries a value that is not
    a port. That is a refusal and not a skip: a skip would let the gate report
    a check it never ran as a pass, so the caller turns it into a failure.
    The caller has to catch it -- ``health.run_gate`` does, and turns it into
    a FAILED result that names the knob.
    """
    if check.requires:
        value = config.get(check.requires)
        if not value:
            return None, f"{check.requires} not set"
        # Returned exactly as configured: a local binding route is keyed on the
        # path it is given, so appending or stripping a trailing slash here
        # would silently address a route that does not exist.
        if check.path:
            return _with_path(value, check.path), None
        return value, None
    return _expand_env(check.url, config), None
