"""FRED_API_KEY is retired as a credential. This guard is the rerunnable proof (DIG-335).

FRED was dropped as a data provider on 2026-10-04. The key *value* was committed
to this repository in ``bdd42541`` (2026-04-18) and that commit is publicly
retrievable from ``digithings-ai/digithings``, so the repository can no longer
be the thing that keeps the key safe. The end state this file enforces is the
one that makes revocation possible at all: **no live surface reads or requires
the name**, so Security can revoke the key at the provider and delete the
``FRED_API_KEY`` organization secret without breaking a scheduled workflow.

This is a *text* guard, not a runtime one, and that is deliberate. The failure
we are preventing is "someone re-adds a ``secrets.FRED_API_KEY`` line to a
workflow" or "someone re-registers the ``fred`` MCP server so an operator
provisions the key again" -- neither ever reaches a test that runs the code.
A text guard sees both. What it cannot see is a differently-named secret
holding the same value; that stays with ``make secrets-scan`` (gitleaks) and
with history rewriting, neither of which is this file's job.

Scope is split so a partial fix is legible:

* ``test_live_*`` -- the digiquant + workflow surfaces DIG-335 owns. Green here
  is the claim "the key is no longer needed by anything we run on develop".
* ``test_cloudflare_worker_does_not_forward_the_retired_key`` -- the Worker
  ``envVars`` block. ``apps/digithings-stack-cloudflare`` is Platform-owned code,
  so this leaf edited four files there together: the ``envVars`` entry, the ``Env``
  interface field, the ``MCP_SCOPED_VARS`` pin in ``env-vars-pin.test.js``, and the
  two operator-facing docs. The pin test does two-way source checks, so the four
  cannot move separately -- which is why this is one test and not four.

Run from the repo root::

    pytest tests/scripts/test_fred_credential_retired.py -m unit
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
from pathlib import Path

import pytest

# Every test here carries its own mark rather than a module-level ``pytestmark``,
# because the allowlisted-path tests must be able to assert on *why* a path is
# exempt and the scanning tests must fail loudly when the shape of the tree
# changes. A module-wide mark would also silently drag the exempt-path tests
# into any other selection someone runs (``-m integration``, ``-m slow``).

REPO_ROOT = Path(__file__).resolve().parents[2]

RETIRED_NAME = "FRED_API_KEY"

# Globs whose ``FRED_API_KEY`` mention is a *live requirement*: an environment
# injection, an ``os.environ`` read, or a declaration that makes some process
# ask an operator for the key. Only these paths can break a run when the org
# secret disappears.
#
# The match is a plain substring scan (``_lines_with_name``), so it is
# deliberately BROADER than "can only break a run": it also fires on prose in
# comments and docstrings. That is the intended behaviour. An earlier version of
# this comment claimed prose never reached these globs, which was false, and the
# merge of develop 8d7c5edbf proved it by failing the guard on a docstring that
# only narrates a past measurement. Fail closed on every mention and make each
# exception an explicit, reviewed entry in ALLOWED_LIVE_MENTIONS below.
LIVE_CODE_GLOBS = (
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    "digiquant/src/**/*.py",
    "digiquant/scripts/**/*.py",
    "scripts/**/*.py",
)

# Config that *registers* a FRED consumer. Same reasoning: no operator should be
# able to point a process at FRED from a checked-in file after this lands.
LIVE_CONFIG_FILES = (
    "config/mcp_servers.yaml",
    "digiquant/src/digiquant/research/config/mcp.claude-desktop.fragment.json",
)

# The single row allowed to keep the name, and the file allowed to keep the
# literal history about it. Kept as data (path -> reason) so a failing run
# names the exception that has to be widened, and why.
#
# The exception is scoped to the exact allowed *line text*, never to the whole
# path. A path-level skip is a hole: it lets any future live read in that file
# through, which is the "test that passes on stub code" failure this file exists
# to prevent. Verified 2026-10-05 by appending a real
# `os.environ.get("FRED_API_KEY")` read to an allowlisted file -- with a
# path-level skip the guard stayed green (6 passed).
ALLOWED_LIVE_MENTIONS = {
    "digiquant/src/digiquant/research/config/mcp.secrets.env.example": (
        {
            "FRED_API_KEY=replace-with-your-fred-api-key": (
                "placeholder row; cleaned and human-owned by DIG-78 / PR #5034, "
                "do not remove the row"
            ),
        }
    ),
    "scripts/secret_staleness_check.py": (
        {
            "were `CURSOR_API_KEY` and `FRED_API_KEY` at 165 days.": (
                "module docstring naming FRED_API_KEY as one of the oldest org "
                "secret names in a hand-recorded rotation audit. Prose about a "
                "past measurement, not a read: the script only calls `gh secret "
                "list` / `gh api .../actions/secrets`, which return names and "
                "dates, never values. Added 2026-10-05 when develop's 8d7c5edbf "
                "brought it in and the guard correctly failed closed on it"
            ),
        }
    ),
}

# Paths that keep the name on purpose, for a reason that is *not* a live
# requirement. Anything added here is a decision to review, not a default.
ALLOWED_ELSEWHERE = {
    "docs/ops/SECRETS_INVENTORY.md": (
        "human lock held by DIG-124; the inventory records the exposure and "
        "must not be edited from this leaf"
    ),
    "apps/digiquant-runner/src/commands.test.ts": (
        "negative assertion -- asserts FRED_API_KEY is absent from the spec"
    ),
    "apps/digiquant-runner/src/runner.test.ts": (
        "negative assertion -- asserts FRED_API_KEY is not forwarded"
    ),
}

# FRED splits its API in two. ``api.stlouisfed.org`` is the JSON/CSV
# observations API and it *requires* a key; ``fred.stlouisfed.org/graph/...csv``
# is the public graph CSV and needs none. Two validation scripts still use the
# public one on purpose -- one of them says so in its docstring -- so the guard
# keys on the host, not on the word "fred".
KEYED_FRED_HOST = "api.stlouisfed.org"

# A keyed FRED fetch behind any name. ``scripts/validation/build_m2_composite.py``
# defines ``_fetch_fred`` against the *public* graph CSV; it is listed, not
# silently tolerated by a substring match, because a substring match on
# ``fetch_fred`` also catches ``_fetch_fred``.
KEYED_FRED_CALLS = {"fetch_fred"}
ALLOWED_KEYLESS_FRED_FETCHERS = {
    "scripts/validation/build_m2_composite.py": (
        "`_fetch_fred` reads the public graph CSV (line 68), no key; documented "
        "as deliberate in the script's own docstring"
    ),
}


def _tracked_files() -> list[str]:
    """Repo-relative paths of every tracked file.

    A guard that cannot scan must fail loudly. Silently passing on a checkout
    where ``git`` is missing would be the worst possible bug in a file whose
    whole purpose is to be believed.
    """
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-z"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(f"git ls-files failed, cannot scan the tree: {result.stderr.strip()}")
    return [p for p in result.stdout.split("\0") if p]


def _tracked_matching(globs: tuple[str, ...]) -> list[str]:
    import fnmatch

    files = _tracked_files()
    matched: list[str] = []
    for path in files:
        # Pathspecs are matched against the repo-relative path. `fnmatch` treats
        # `*` as matching `/` too, so `**` collapses to `*` here -- which is
        # exactly what we want for these globs (a prefix + any depth).
        for pattern in globs:
            flat = pattern.replace("**/", "")
            if fnmatch.fnmatch(path, flat) or fnmatch.fnmatch(path, pattern):
                matched.append(path)
                break
    return sorted(set(matched))


def _lines_with_name(path: str, needle: str = RETIRED_NAME) -> list[tuple[int, str]]:
    try:
        text = (REPO_ROOT / path).read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return []
    out = []
    for i, line in enumerate(text.splitlines(), start=1):
        if needle in line:
            out.append((i, line.strip()))
    return out


@pytest.mark.unit
def test_live_code_surfaces_do_not_require_the_retired_key() -> None:
    """No workflow or Python entry point may reference FRED_API_KEY.

    This is the assertion that makes revocation safe. ``pipeline-digiquant-prices``
    used to inject ``${{ secrets.FRED_API_KEY }}`` and ``prices.py`` used to
    ``raise click.ClickException`` when it was absent, so deleting the org
    secret would have turned three green scheduled runs red.
    """
    offenders: list[str] = []
    for path in _tracked_matching(LIVE_CODE_GLOBS):
        allowed_lines = ALLOWED_LIVE_MENTIONS.get(path, {})
        for lineno, line in _lines_with_name(path):
            # Exception is per exact line text, not per file: a different line in
            # an allowlisted file is still an offender.
            if line in allowed_lines:
                continue
            offenders.append(f"{path}:{lineno}: {line}")

    assert not offenders, (
        "FRED_API_KEY is retired (DIG-335) but these live surfaces still "
        "reference it. Removing the org secret will break them:\n  "
        + "\n  ".join(offenders)
        + "\n\nIf a mention is legitimate, add the path to "
        "ALLOWED_LIVE_MENTIONS with a reason, and say why in the PR."
    )


@pytest.mark.unit
def test_retired_key_is_not_re_registered_in_the_mcp_registry() -> None:
    """``config/mcp_servers.yaml`` must not offer a FRED provider.

    The registry entry was ``free_providers -> fred -> api_key_env: FRED_API_KEY``.
    Leaving it in place is the quiet failure mode: nothing crashes, an operator
    just reads the registry, provisions the key again, and the exposure is back.
    """
    path = "config/mcp_servers.yaml"
    offenders = [f"{path}:{n}: {hit}" for n, hit in _lines_with_name(path)]
    assert not offenders, (
        "FRED_API_KEY must not appear in the MCP server registry (DIG-335):\n  "
        + "\n  ".join(offenders)
    )

    text = (REPO_ROOT / path).read_text(encoding="utf-8", errors="replace")
    assert not re.search(r"^\s*-?\s*name:\s*fred\s*$", text, re.MULTILINE), (
        f"{path} still registers a provider named `fred` (DIG-335)."
    )


@pytest.mark.unit
def test_retired_key_is_not_in_the_claude_desktop_mcp_fragment() -> None:
    """The ``fred`` MCP server entry must be gone from the desktop fragment.

    The entry was ``uvx fred-mcp-server`` with ``FRED_API_KEY: ${env:FRED_API_KEY}``,
    which resolves the key straight out of the operator's shell on every launch.
    """
    path = "digiquant/src/digiquant/research/config/mcp.claude-desktop.fragment.json"
    assert (REPO_ROOT / path).exists(), f"{path} vanished; this guard needs updating"

    data = json.loads((REPO_ROOT / path).read_text(encoding="utf-8"))
    servers = data.get("mcpServers", {})
    assert "fred" not in servers, (
        f"{path} still registers the `fred` MCP server (DIG-335); it needs "
        "FRED_API_KEY to start."
    )

    offenders: list[str] = []
    for name, spec in servers.items():
        env = spec.get("env") or {}
        if RETIRED_NAME in env:
            offenders.append(f"{name}.env.{RETIRED_NAME}")
    assert not offenders, (
        f"{path} still passes {RETIRED_NAME} to: " + ", ".join(offenders)
    )


def _mentions_fred(path: str) -> bool:
    """Cheap text prefilter: does this file mention FRED in any casing?"""
    text = (REPO_ROOT / path).read_text(encoding="utf-8", errors="replace")
    return "fred" in text.lower()


def _code_strings_and_calls(path: str) -> tuple[set[str], set[str]]:
    """Return ``(called_names, string_literals)`` for a Python file, docstrings excluded.

    Text matching was the first cut of this guard and it failed for the wrong
    reason: ``macro_ingest.py`` mentions ``fetch_fred`` and
    ``fred/series/observations`` only inside its module docstring, where the text
    records that the fetcher was *removed*. A guard that cannot tell a call from
    a comment about a deleted call gets ignored, and a guard that gets ignored
    is worse than no guard, because it still reads as coverage.

    So this walks the AST: names of called functions, and string constants that
    are not docstrings.

    A ``SyntaxError`` here is reported, never swallowed. The repo requires
    Python >= 3.12 (``digiquant/pyproject.toml``), and running this guard under
    an older interpreter fails on PEP 695 generics -- a failure that looks like
    a finding but is really a wrong interpreter. That distinction is why the
    caller reports it separately from an actual FRED hit.
    """
    tree = ast.parse((REPO_ROOT / path).read_text(encoding="utf-8", errors="replace"), filename=path)

    # Bare `Expr(Constant(str))` statements are docstrings (module, class, and
    # the first statement of every function). They describe, they do not do.
    docstring_nodes: set[int] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            docstring_nodes.add(id(node.value))

    calls: set[str] = set()
    strings: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                calls.add(func.id)
            elif isinstance(func, ast.Attribute):
                calls.add(func.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in docstring_nodes:
                strings.add(node.value)
    return calls, strings


@pytest.mark.unit
def test_no_keyed_fred_api_call_remains_in_python() -> None:
    """The keyed FRED API must not be reachable at all, under any name.

    Measured on ``origin/develop`` at DIG-335 open: the only live reference left
    was ``macro_ingest.py``'s ``FRED_OBS_URL``, declared at line 37 and
    re-exported in ``__all__`` but never called -- dead config pointing at a
    keyed endpoint, which is exactly the kind of thing someone wires back up
    later. The public ``fredgraph.csv`` path stays; two validation scripts use it
    and neither sends a key.
    """
    # Text prefilter first: only files that mention FRED at all can fail, so
    # only they are parsed. Keeps the guard fast and keeps parse errors
    # meaningful (they can then only come from a file that really mentions FRED).
    candidates = [
        path
        for path in _tracked_matching(LIVE_CODE_GLOBS)
        if path.endswith(".py") and _mentions_fred(path)
    ]

    offenders: list[str] = []
    unanalysable: list[str] = []
    for path in candidates:
        try:
            calls, strings = _code_strings_and_calls(path)
        except SyntaxError as exc:
            unanalysable.append(f"{path}: {exc.msg} (line {exc.lineno})")
            continue

        for host in sorted(s for s in strings if KEYED_FRED_HOST in s):
            offenders.append(f"{path}: string literal -> {host}")
        if path not in ALLOWED_KEYLESS_FRED_FETCHERS:
            for name in sorted(calls & KEYED_FRED_CALLS):
                offenders.append(f"{path}: calls {name}()")

    assert not offenders, (
        f"A keyed FRED API reference ({KEYED_FRED_HOST}) is reachable in the tree "
        "(DIG-335). The public fredgraph.csv stays; the observations API does not:\n  "
        + "\n  ".join(offenders)
    )
    assert not unanalysable, (
        "The FRED guard could not analyse these files. Run it on Python >= 3.12 "
        "(repo requires-python); under an older interpreter PEP 695 generics "
        "raise SyntaxError and the guard would silently skip real findings:\n  "
        + "\n  ".join(unanalysable)
    )


@pytest.mark.unit
def test_allowed_mentions_are_all_documented() -> None:
    """Every exemption names a reason, and each exemption is still needed.

    Without this the allowlist is a silent hole: a path added "temporarily"
    keeps its exemption forever. Two staleness modes are covered:

    - the exempt *path* no longer exists -> drop the row;
    - the exempt *line text* no longer appears in that path -> drop the row, so
      an exemption cannot outlive the prose it was written for.
    """
    for path, allowed_lines in ALLOWED_LIVE_MENTIONS.items():
        assert allowed_lines, f"{path} is exempt from the FRED guard with no allowed line"
        assert (REPO_ROOT / path).exists(), (
            f"{path} is exempt from the FRED guard but no longer exists -- drop the row"
        )
        present = {line for _, line in _lines_with_name(path)}
        for line_text, reason in allowed_lines.items():
            assert reason.strip(), f"{path}:{line_text!r} is exempt with no reason"
            assert line_text in present, (
                f"{path}: exempt line no longer appears in the file, so the "
                f"exemption is stale -- drop it: {line_text!r}"
            )

    for path, reason in ALLOWED_ELSEWHERE.items():
        assert reason.strip(), f"{path} is exempt from the FRED guard with no reason"
        assert (REPO_ROOT / path).exists(), (
            f"{path} is exempt from the FRED guard but no longer exists -- drop the row"
        )


@pytest.mark.unit
def test_cloudflare_worker_does_not_forward_the_retired_key() -> None:
    """The stack Worker must stop forwarding FRED_API_KEY into its MCP container.

    Both halves are checked because they are one edit. ``env-vars-pin.test.js``
    asserts ``MCP_SCOPED_VARS`` is present on the MCP ``envVars`` block and absent
    from the stack one, and it ``checkKeyMatchesRef``'s each key against the
    ``Env`` interface -- so dropping the ``Env`` field without the pin (or the pin
    without the field) fails that test instead of silently passing here.
    """
    index = "apps/digithings-stack-cloudflare/src/index.ts"
    offenders = [f"{index}:{n}: {hit}" for n, hit in _lines_with_name(index)]
    assert not offenders, (
        "The stack Worker still reads/forwards FRED_API_KEY (DIG-335):\n  "
        + "\n  ".join(offenders)
    )

    pin = "apps/digithings-stack-cloudflare/src/env-vars-pin.test.js"
    pin_text = (REPO_ROOT / pin).read_text(encoding="utf-8", errors="replace")
    assert RETIRED_NAME not in pin_text, (
        f"{pin} still pins FRED_API_KEY as an MCP-scoped var (DIG-335); the "
        "pin has to move in the same commit as the Worker envVars block."
    )