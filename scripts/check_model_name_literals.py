#!/usr/bin/env python3
"""Fail if production code hardcodes a provider model name. (#5029 phase 3)

#5029 moved the model names this stack routes on out of Python and TypeScript
and into `config/`. That change was verified once, by hand. This script is the
thing that keeps it true, and it exists because of how the first attempt at the
same idea went wrong: the digichat deploy table used to be duplicated byte for
byte into two consumers, no test noticed for as long as it lived, and every
test that existed passed with the duplication restored. Coverage nobody can
falsify is not coverage. So this reports the *count* per file, keeps an explicit
allowlist of files still carrying literals, and treats a stale entry in that
allowlist as a failure rather than tidying it away silently.

Two independent ways a name is caught:

* **shape** — `MODEL_ID_PATTERN` matches anything id-shaped (`gpt-4o-mini`,
  `claude-sonnet-4-6`, `grok-4.3`, ...). This is the one that catches a model
  nobody has put in config yet, which is the whole failure mode: the literal
  arrives first and the config entry later, if ever.
* **configured** — the name is one this stack actually routes on, read from
  `config/model-policy.json` (flagship markers, balanced flagship markers, the
  fallback model). Precise, and it fails the moment an id is promoted into
  config and then hardcoded somewhere.

Prose is allowed. A docstring may say "OpenAI BYOK models are bare ids"; what
is forbidden is an id that code routes on. Python is matched through `ast`, so
only real string constants count; TypeScript is matched after comments are
masked, so a commented-out example never trips the guard but a string literal
always does.

Test fixtures are exempt by decision (#5029): a test that names a model is
testing that the name works, and moving those to config would make the tests
test the config instead of the behaviour.

Run from the repo root:  python scripts/check_model_name_literals.py
"""

from __future__ import annotations

import ast
import json
import re
import sys
from collections.abc import Iterator
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Anything shaped like a model id. Deliberately broad on the family and narrow
#: on the version, so a new release of a known family trips it but prose about
#: "gpt" alone does not.
MODEL_ID_PATTERN = re.compile(
    r"gpt-[0-9]"
    r"|claude-(?:sonnet|haiku|opus|fable)"
    r"|gemini-[0-9]"
    r"|grok-[0-9]"
    r"|llama-[0-9]"
    r"|deepseek-(?:chat|reasoner|v[34])"
    r"|qwen[0-9]"
    r"|glm-[0-9]"
    r"|kimi-"
    r"|nemotron"
    r"|phi-[0-9]"
    r"|gemma-[0-9]"
)

#: Source extensions worth reading. Config, docs and lockfiles are not code.
SOURCE_SUFFIXES = frozenset({".py", ".ts", ".tsx", ".js", ".jsx", ".mjs"})

#: Directories that hold no first-party source.
SKIP_DIR_PARTS = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".next",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "site-packages",
        "venv",
    }
)

#: Generated files. Their whole content is the output of a generator, so a name
#: in one is the generator's business, not this check's.
GENERATED_MARKERS = (".generated.",)

#: Whole paths exempt from the check, each with the reason it is exempt rather
#: than a file that happened to trip the guard once.
EXEMPT_PREFIXES: dict[str, str] = {
    # `@digithings/ui` is a published package with an `exports` map, built on
    # its own. It cannot import repo-root `config/` at build time, and a chat
    # skin is *a provider binding* — the skin exists to present one provider's
    # model, so naming one is its job, not a violation. Exempting the directory
    # rather than the two files first seen in it (grok, perplexity) because the
    # base skin names models for the same reason and listing files here would
    # just be a list that rots.
    "packages/ui/src/components/chat/skins/": "published package; a skin is a provider binding",
    # Vendored third-party reference material (assistant-ui templates), listed
    # in apps/digichat/tsconfig.json's `exclude` alongside `node_modules` and
    # `cli`, with provenance in reference/SOURCE.md. Not our code to configure.
    "apps/digichat/reference/": "vendored third-party reference, excluded from tsconfig",
    # This file. The pattern has to be written down somewhere, and matching it
    # against itself would make the guard fail on every run. Named explicitly so
    # the exemption is one reviewed line rather than a pattern that can be
    # widened by accident.
    "scripts/check_model_name_literals.py": "this file holds the pattern",
}

#: Test fixtures, by decision (#5029): a test that names a model is testing that
#: the name works. Matched on any path part, so `tests/`, `__tests__/` and a
#: co-located `foo.test.ts` are all covered by one rule.
TEST_DIR_PARTS = frozenset({"tests", "test", "__tests__", "fixtures", "e2e"})

#: Test *files*, by naming convention: `test_x.py`, `x_test.py`, `x.test.ts`,
#: `x.spec.ts`.
#:
#: Deliberately NOT matching a bare `test` stem. `apps/digithings-web/functions/
#: api/byok/test.ts` is production code — a Cloudflare Pages Function serving
#: `POST /api/byok/test`, whose name comes from the route segment, and whose
#: real test is the `test.test.ts` beside it. A bare-stem rule exempted it, and
#: that is a false negative in the one place a false negative is worst: the
#: guard would have gone quiet about a file that ships.
TEST_FILE_STEMS = re.compile(r"^test_|_test$|\.test$|\.spec$")


def _is_test_path(path: Path) -> bool:
    """True for a file the guard must not read.

    A test *directory* at any depth is a fixture tree. A test *file* is one
    whose name follows a test convention. The file case is the narrow one and
    the comment on `TEST_FILE_STEMS` says why: a bare `test.ts` is a route, not
    a fixture.
    """
    rel = path.relative_to(REPO_ROOT)
    if any(part in TEST_DIR_PARTS for part in rel.parts[:-1]):
        return True
    return bool(TEST_FILE_STEMS.search(rel.stem))


def _is_exempt(path: Path) -> bool:
    """True for a production file the guard deliberately does not read."""
    rel = path.relative_to(REPO_ROOT).as_posix()
    if any(rel.startswith(prefix) for prefix in EXEMPT_PREFIXES):
        return True
    return any(marker in rel for marker in GENERATED_MARKERS)


def iter_source_files() -> Iterator[Path]:
    """Every production source file in the repo, in a stable order.

    Dot-prefixed entries are skipped wholesale, which covers both `.git` and
    the scratch files this repo's own workflow creates — an editor backup or a
    `.env`-shaped file is a tool artifact, not code. That matters more than it
    sounds: a keep-your-backup-inside-the-worktree habit (which is the documented
    rule here, because a restore from `/tmp/opencode/` has already left
    production files reverted twice) otherwise turns every revert check into a
    guard failure that is about the scratch file rather than the revert.
    """
    for path in sorted(REPO_ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
            continue
        parts = path.relative_to(REPO_ROOT).parts
        if any(part.startswith(".") for part in parts):
            continue
        if SKIP_DIR_PARTS & set(parts):
            continue
        if _is_exempt(path) or _is_test_path(path):
            continue
        yield path


def _python_hits(path: Path) -> list[tuple[int, str]]:
    """`(line, literal)` for every string constant in a Python file that is not
    a docstring.

    Docstrings are excluded because prose is allowed to describe what a
    configured value looks like. The exclusion is by value, so any *other*
    string that happens to equal a docstring is also excused — acceptable,
    because the alternative (positional tracking) is a parser's job and the
    only cost here is a slightly quieter guard.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as exc:  # a file the interpreter itself cannot read
        raise SystemExit(f"{path}: cannot parse ({exc})") from exc

    docstrings: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            doc = ast.get_docstring(node, clean=False)
            if doc is not None:
                docstrings.add(doc)

    hits = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value not in docstrings
            and MODEL_ID_PATTERN.search(node.value)
        ):
            hits.append((node.lineno, node.value))
    return hits


def _mask_js_comments(source: str) -> str:
    """Return *source* with comment characters replaced by spaces.

    Length and offsets are preserved so a match found in the masked text points
    at the right line, and **string contents are left alone** — a model id in a
    string literal is exactly what this guard exists to find. Only comments go.

    It is a small state machine rather than a regex because the naive version
    gets it backwards in two ways that matter: it would treat the `//` in
    `https://…` as a comment and blank out real code, and it would blank out
    strings, which is the one thing that must survive. Template literals nest,
    so `${` re-enters code and the matching `}` returns to the template.
    """
    out = list(source)
    i = 0
    n = len(source)
    # None = code, or the quote character that opened the current string.
    state: str | None = None
    brace_depth = 0

    def blank(start: int, end: int) -> None:
        for k in range(start, min(end, n)):
            if out[k] != "\n":
                out[k] = " "

    while i < n:
        ch = source[i]
        if state is None:
            if source.startswith("//", i):
                end = source.find("\n", i)
                end = n if end == -1 else end
                blank(i, end)
                i = end
                continue
            if source.startswith("/*", i):
                end = source.find("*/", i + 2)
                end = n if end == -1 else end + 2
                blank(i, end)
                i = end
                continue
            if ch in "'\"`":
                state = ch
                brace_depth = 0
            i += 1
            continue
        # Inside a string.
        if ch == "\\":
            i += 2
            continue
        if state == "`" and source.startswith("${", i):
            state = "code"  # interpolation: back to code, brace-tracked
            brace_depth = 0
            i += 2
            continue
        if state == "code" and ch == "{":
            brace_depth += 1
        elif state == "code" and ch == "}":
            brace_depth -= 1
            if brace_depth <= 0:
                state = "`"
                brace_depth = 0
        elif ch == state:
            state = None
        i += 1
    return "".join(out)


_QUOTE_CHARS = "'\"`"


def _enclosing_literal(line: str, start: int, end: int) -> str:
    """The quoted literal in *line* containing the span `[start, end)`.

    A guard that reports `claude-sonnet` when the code says
    `'claude-sonnet-4-6'` makes the reader go and find it, which is work the
    guard should be doing. Python reports whole string constants, so the
    TypeScript side has to as well or the two disagree about what a "hit" is.
    Returns the whole line when the span is not inside quotes — a model name
    reached by concatenation, say — because reporting nothing would hide it.
    """
    open_at = -1
    quote = ""
    for index, char in enumerate(line[:start]):
        if char in _QUOTE_CHARS:
            open_at, quote = index, char
    if open_at < 0:
        return line.strip()
    close_at = line.find(quote, end)
    if close_at < 0:
        return line.strip()
    return line[open_at + 1 : close_at]


def _script_hits(path: Path) -> list[tuple[int, str]]:
    """`(line, literal)` for every comment-free source line naming a model."""
    masked = _mask_js_comments(path.read_text(encoding="utf-8"))
    hits = []
    for lineno, line in enumerate(masked.splitlines(), start=1):
        match = MODEL_ID_PATTERN.search(line)
        if match:
            hits.append((lineno, _enclosing_literal(line, match.start(), match.end())))
    return hits


def scan(path: Path) -> list[tuple[int, str]]:
    """Every model-name literal in one production file."""
    return _python_hits(path) if path.suffix == ".py" else _script_hits(path)


def configured_markers() -> set[str]:
    """The ids this stack routes on, read from `config/model-policy.json`.

    Read rather than hardcoded so that promoting a name into config and then
    hardcoding it is a failure. Raises if the file is missing or empty: a guard
    whose configured set has silently emptied out is a guard that passes.
    """
    policy_path = REPO_ROOT / "config" / "model-policy.json"
    if not policy_path.is_file():
        raise SystemExit(f"model policy not found: {policy_path}")
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    markers = {
        *policy.get("flagship_model_id_markers", []),
        *policy.get("balanced_flagship_markers", []),
    }
    fallback = policy.get("fallback_model")
    if fallback:
        markers.add(fallback)
    if not markers:
        raise SystemExit(f"{policy_path} declares no markers; the guard would pass vacuously")
    return markers


#: Production files still carrying model literals, with the count each was found
#: to hold on this branch. #5029 phase 2 (generate) shrinks this list toward
#: empty; a file that drops a literal without its entry being updated here is
#: reported, so the list cannot rot into a permanent exemption.
KNOWN_REMAINING: dict[str, int] = {
    # Phase-2 targets. `digillm/client.py` must be *generated*, not read at
    # runtime: digillm/AGENTS.md forbids runtime file reads in an installable
    # library. `functions/api/byok/test.ts` is a Cloudflare Pages Function
    # serving POST /api/byok/test — production code whose name comes from its
    # route, which is why it is here and not treated as a fixture.
    "apps/digichat/src/hooks/use-byok-key.ts": 17,
    "apps/digithings-web/functions/api/byok/test.ts": 10,
    "apps/digithings-web/lib/providerSettings.ts": 14,
    "digillm/src/digillm/client.py": 17,
    # One refusal message naming the fallback model. A message is as much a
    # literal as a routing table — the same reasoning #5046 applied when it
    # replaced digigraph's per-provider refusal examples.
    "scripts/validate_model_routing.py": 1,
}


def main() -> int:
    markers = configured_markers()
    all_files = list(iter_source_files())
    if not all_files:
        raise SystemExit("no production sources found; the guard would pass vacuously")

    found: dict[str, list[tuple[int, str]]] = {}
    for path in all_files:
        hits = scan(path)
        if hits:
            found[path.relative_to(REPO_ROOT).as_posix()] = hits

    unexpected = {name: hits for name, hits in found.items() if name not in KNOWN_REMAINING}
    stale = {
        name: (expected, len(found.get(name, [])))
        for name, expected in KNOWN_REMAINING.items()
        if len(found.get(name, [])) != expected
    }

    for name, hits in sorted(unexpected.items()):
        detail = ", ".join(f"{line}: {text!r}" for line, text in hits[:5])
        more = f" (+{len(hits) - 5} more)" if len(hits) > 5 else ""
        print(f"FAIL {name}: {len(hits)} model name literal(s) — {detail}{more}", file=sys.stderr)
    for name, (expected, actual) in sorted(stale.items()):
        print(
            f"FAIL {name}: allowlist expects {expected} literal(s), found {actual}. "
            "Update KNOWN_REMAINING in scripts/check_model_name_literals.py "
            "(#5029 phase 2 shrinks this list toward empty).",
            file=sys.stderr,
        )

    if unexpected or stale:
        print(
            f"\n{len(unexpected)} file(s) outside the allowlist, "
            f"{len(stale)} stale allowlist entr(ies). Model names belong in config/, "
            "not in code.",
            file=sys.stderr,
        )
        return 1

    total = sum(len(hits) for hits in found.values())
    print(
        f"check_model_name_literals: OK ({len(all_files)} production sources, "
        f"{len(markers)} configured markers, {total} known literal(s) in "
        f"{len(found)} allowlisted file(s))"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
