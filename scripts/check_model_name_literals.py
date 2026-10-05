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

One known gap, inherent to matching names by shape: a name assembled from
pieces evades the pattern. ``"gpt-" + "4o-mini"`` and `` `gpt-${x}-mini` `` are
not literals the matcher can see. That is a deliberate trade rather than an
oversight — the alternatives are a constant-folding build step or a data-flow
analysis, and both cost far more than the hole is worth in a guard whose job
is to catch the copy-paste of a real id. Python's *implicit* concatenation
(``"gpt-" "4o-mini"``) is caught, because the parser folds it into one constant
before the matcher sees it.

Run from the repo root:  python scripts/check_model_name_literals.py
"""

from __future__ import annotations

import ast
import json
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Anything shaped like a model id. Deliberately broad on the family and narrow
#: on the version, so a new release of a known family trips it but prose about
#: "gpt" alone does not.
#:
#: Two rules this pattern learned the hard way. A family must be followed by a
#: version digit or an explicit pin, or prose trips it — an earlier revision
#: matched bare `kimi-` and bare `nemotron`, so the string `"nemotron adapter"`
#: in error copy counted as a model name. And `qwen`/`glm`/`kimi` are matched
#: case-insensitively, because this repo's own catalog contains `zai-org/GLM-
#: 5.3-Flash` and `moonshotai/Kimi-K3`, and a case-sensitive pattern waved them
#: through while flagging the lowercase spelling.
MODEL_ID_PATTERN = re.compile(
    r"gpt-[0-9]"
    r"|claude-(?:sonnet|haiku|opus|fable|[34])"
    r"|gemini-[0-9]"
    r"|grok-[0-9]"
    r"|llama-[0-9]"
    r"|deepseek-(?:chat|reasoner|r1|v[34])"
    r"|qwen[0-9]"
    r"|glm-[0-9]"
    r"|kimi-[a-z0-9]"
    r"|nemotron-[0-9]"
    r"|phi-[0-9]"
    r"|gemma-[0-9]",
    re.IGNORECASE,
)
#: OpenAI's reasoning line carries no family word at all — `o3`, `o4-mini` — so
#: it needs its own rule. The trailing group requires a version digit, an
#: optional `-suffix`, or end-of-token, so `o1` matches in `"o1"` and
#: `"o4-mini"` but not inside `o123` or a word that merely starts `o1`.
REASONING_ID_PATTERN = re.compile(r"\bo[134](?![0-9a-z])")

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
#:
#: The filename is only a hint — a hand-written `foo.generated.ts` would wave
#: away every literal in it (the real one waives 405, seven times the whole
#: allowlist) on nothing but its own name. So the waiver is two-part: the name
#: marks it a candidate, and a generator banner on the first line confirms it.
GENERATED_MARKERS = (".generated.",)

#: A first line containing this is the claim "a generator wrote me", and it is
#: the only thing that backs a `GENERATED_MARKERS` match.
GENERATED_BANNER = "GENERATED FILE"

#: Whole paths exempt from the check, each with the reason it is exempt rather
#: than a file that happened to trip the guard once.
EXEMPT_PREFIXES: dict[str, str] = {
    # `@digithings/ui` is a workspace package consumed as TypeScript source —
    # `"private": true`, an `exports` map, and `scripts` of `test`/`typecheck`
    # with no build step — and a chat skin is *a provider binding*: the skin
    # exists to present one provider's model, so naming one is its job, not a
    # violation. Exempting the directory rather than the two files first seen
    # in it (grok, perplexity) because the base skin names models for the same
    # reason and listing files here would just be a list that rots.
    #
    # Note what this is NOT: the package cannot be *technically* prevented from
    # reaching root `config/` (a relative import would resolve fine). It is a
    # judgement that a shipped skin owns its provider vocabulary, and it is
    # recorded as a judgement so a later reader can disagree with it.
    "packages/ui/src/components/chat/skins/": "workspace source package; a skin is a provider binding",
    # Vendored third-party reference material (assistant-ui templates), listed
    # in apps/digichat/tsconfig.json's `exclude` alongside `node_modules` and
    # `cli`, with provenance in
    # reference/assistant-ui-templates/SOURCE.md. Not our code to configure.
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


ROUTE_FILENAMES = ("route.ts", "route.tsx", "route.js", "route.jsx")


def _is_test_path(path: Path) -> bool:
    """True for a file the guard must not read.

    A test *directory* at any depth is a fixture tree. A test *file* is one
    whose name follows a test convention. The file case is the narrow one and
    the comment on `TEST_FILE_STEMS` says why: a bare `test.ts` is a route, not
    a fixture.

    The directory case has the same trap, one level up. This repo carries the
    same BYOK probe twice: `apps/digithings-web/functions/api/byok/test.ts` (a
    Pages Function, whose name comes from its route) and
    `apps/digichat/src/app/api/byok/test/route.ts` (the same endpoint as a
    Next.js route handler, so `test` is a *route segment*). Exempting any dir
    named `test` hid 5 literals in that second file -- the exact false negative
    `TEST_FILE_STEMS` exists to prevent, reached through the directory instead.
    So a `TEST_DIR_PARTS` match is overridden when that directory holds a route
    file, which is what makes a path segment a segment.
    """
    rel = path.relative_to(REPO_ROOT)
    for index, part in enumerate(rel.parts[:-1]):
        if part not in TEST_DIR_PARTS:
            continue
        segment = REPO_ROOT.joinpath(*rel.parts[: index + 1])
        if not any((segment / name).is_file() for name in ROUTE_FILENAMES):
            return True
    return bool(TEST_FILE_STEMS.search(rel.stem))


def _is_exempt(path: Path) -> bool:
    """True for a production file the guard deliberately does not read."""
    rel = path.relative_to(REPO_ROOT).as_posix()
    if any(rel.startswith(prefix) for prefix in EXEMPT_PREFIXES):
        return True
    if not any(marker in rel for marker in GENERATED_MARKERS):
        return False
    # A generated-looking name alone is a claim anyone can make by renaming.
    # Read the banner: `scripts/refresh_model_catalog.py` writes it, and a
    # hand-written file with a `.generated.` name and no banner is scanned.
    try:
        first = path.read_text(encoding="utf-8").split("\n", 1)[0]
    except (OSError, UnicodeDecodeError):
        return False
    return GENERATED_BANNER in first


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


def names_a_model(value: str, markers: frozenset[str]) -> bool:
    """True when *value* carries a model name by shape *or* by configuration.

    Substring, not equality, for the configured half: `"gpt-4o-mini"` contains
    the `"gpt-4o"` marker, so an equality check would miss the exact literal
    this guard is about. That is the rule #5046's digigraph guard used, and it
    is why a marker set of *prefixes* can enforce anything at all.

    Both halves matter and they catch different things. Shape catches a model
    nobody has put in config yet — the literal arrives first, the config entry
    later if ever. Configured catches an id this stack routes on even when its
    shape does not look like a model id, which is eight of the sixteen markers
    in `config/model-policy.json` (`o1-`, `o3-`, `o4-`, `claude-3-opus`,
    `claude-3-5-sonnet`, `claude-4`): they are prefixes of ids, not id-shaped
    text, so the shape pattern alone would wave them through.
    """
    if MODEL_ID_PATTERN.search(value) or REASONING_ID_PATTERN.search(value):
        return True
    return any(marker in value for marker in markers)


def _python_hits(path: Path, markers: frozenset[str]) -> list[tuple[int, str]]:
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
            and names_a_model(node.value, markers)
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

    Regex literals are a fourth state, and getting them wrong is a *false
    negative with a very innocent face*: `/^https?:\\/\\//` opens with `//` inside
    a regex, and a scanner that does not know that will treat everything from
    the second slash to end of line as a comment. In `const u = /^https?:\\/\\//,
    m = "gpt-4o-mini";` that swallows a real literal on the same line and the
    guard reports nothing. The tell is what precedes the `/`: a `/` after an
    identifier, number, `)`, `]` or `}` is division, and anything else opens a
    regex. Inside a regex, `//` and `/*` are ordinary characters.
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

    def _opens_regex(at: int) -> bool:
        """True when the `/` at *at* starts a regex literal, not division.

        Looked up from the previous non-space character, which is the only
        signal available without a full parser. After a value-ending token a
        `/` is division; anywhere else (start of line, `=`, `(`, `,`, `:`, `;`,
        `return`, …) it opens a regex.
        """
        k = at - 1
        while k >= 0 and source[k] in " \t":
            k -= 1
        if k < 0:
            return True
        prev = source[k]
        return not (prev.isalnum() or prev in "_$)]}")

    while i < n:
        ch = source[i]
        if state is None:
            # Comment tests come first, and they have to: a `/` at the start of
            # a line, or after `=`, is far more often a comment than a regex,
            # and `//` cannot open a regex anyway (`//` is an empty regex,
            # which JavaScript treats as a comment). Testing the regex case
            # first would make every line comment a regex run.
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
            if ch == "/" and _opens_regex(i):
                # Regex literal: scan to its unescaped closing slash on this
                # line, passing its contents through untouched so a model id
                # written inside a pattern is still visible.
                j = i + 1
                while j < n and source[j] != "\n":
                    if source[j] == "\\":
                        j += 2
                        continue
                    if source[j] == "/":
                        break
                    if source[j] == "[":
                        # Character class: `//` inside one is literal too.
                        j += 1
                        while j < n and source[j] != "]" and source[j] != "\n":
                            j += 2 if source[j] == "\\" else 1
                    j += 1
                i = min(j + 1, n)
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


class _Span(NamedTuple):
    """A start/end pair, so a configured-marker hit can reuse `.search()`'s
    interface. `re.Match` already provides one; a marker hit has no match object,
    and wrapping the indices is cheaper than branching at every call site."""

    start: int
    end: int


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


def _script_hits(path: Path, markers: frozenset[str]) -> list[tuple[int, str]]:
    """`(line, literal)` for every comment-free source line naming a model."""
    masked = _mask_js_comments(path.read_text(encoding="utf-8"))
    hits = []
    for lineno, line in enumerate(masked.splitlines(), start=1):
        # Checked in this order so a shape match wins the span: its offsets are
        # tighter, so _enclosing_literal quotes the smallest sensible literal.
        # The configured fallback exists because a marker can sit inside a
        # string with no id-shaped text anywhere in it (a bare "o3" pin), and
        # skipping it would reintroduce the exact hole this guard was written
        # to close.
        match = MODEL_ID_PATTERN.search(line) or REASONING_ID_PATTERN.search(line)
        # Both branches end up as a _Span so the two never get read through the
        # wrong interface. A re.Match has .start()/.end() *methods*; a _Span
        # has start/end *fields*. Calling match.start() on the configured
        # fallback raised 'int' object is not callable — and because every
        # marker in the shipped policy is also shape-matched, that branch
        # never ran on the real tree, so the guard stayed green over a crash.
        span = _Span(*match.span()) if match is not None else None
        if span is None:
            for marker in markers:
                index = line.find(marker)
                if index >= 0:
                    span = _Span(index, index + len(marker))
                    break
        if span is not None:
            hits.append((lineno, _enclosing_literal(line, span.start, span.end)))
    return hits


def scan(path: Path, markers: frozenset[str] = frozenset()) -> list[tuple[int, str]]:
    """Every model-name literal in one production file.

    *markers* is the configured id set. It defaults to empty so a caller that
    only wants the shape sweep can omit it, but `main()` always passes the real
    set — an empty default is what let the configured half of this guard exist
    in documentation without existing in the matcher.
    """
    if path.suffix == ".py":
        return _python_hits(path, markers)
    return _script_hits(path, markers)


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
class _Allowance(NamedTuple):
    """What `KNOWN_REMAINING` expects a file to contain, and why.

    Both counts are pinned because one is not enough. An occurrence count alone
    cannot see a swap between two repeats of the same name, so `o3` written
    twice and later replaced by two different models would still match; the
    distinct count catches that.

    The *names* are deliberately not pinned. Enumerating them shows why: many
    are `_enclosing_literal` span artifacts rather than names at all --
    `'o3: "OpenAI API",'`, `'o3: { inPerM: ... },'` -- and pinning those would
    encode an accident of the matcher's line-column arithmetic. Pinning real
    message text (`'Model is required for ${provider} (e.g. grok-4.3).'`) would
    make an unrelated copy edit a CI failure, and a guard that cries wolf gets
    switched off, which is worse than the gap it leaves. The residual gap is
    therefore named rather than hidden: swapping one allowlisted literal for a
    different one of the same distinct count is not detected.
    """

    occurrences: int
    distinct: int


#: Production files that still name models, with the literal counts they carry.
#: #5029 phase 2 generates these away; each removal here is that work landing.
KNOWN_REMAINING: dict[str, _Allowance] = {
    # Phase-2 targets. `digillm/client.py` must be *generated*, not read at
    # runtime: digillm/AGENTS.md forbids runtime file reads in an installable
    # library. `functions/api/byok/test.ts` is a Cloudflare Pages Function
    # serving POST /api/byok/test -- production code whose name comes from its
    # route, which is why it is here and not treated as a fixture.
    "apps/digichat/src/hooks/use-byok-key.ts": _Allowance(17, 12),
    # The Next.js half of that same endpoint. `test` is a route segment here,
    # not a test directory, which is why this file is scanned at all.
    "apps/digichat/src/app/api/byok/test/route.ts": _Allowance(5, 5),
    "apps/digithings-web/functions/api/byok/test.ts": _Allowance(10, 10),
    "apps/digithings-web/lib/providerSettings.ts": _Allowance(15, 15),
    # New under the widened pattern: `GPT-5.6 Sol`, `GPT-5.6 Luna`, `o3`, and a
    # pricing-provenance URL carrying three model names and their prices.
    "apps/digithings-web/lib/ragCost.ts": _Allowance(4, 4),
    # Also new. Four of the seven distinct values are `o3:`-prefixed span
    # fragments (see `_Allowance`), the concrete reason names are not pinned.
    "apps/digithings-web/lib/stackCatalog.ts": _Allowance(8, 7),
    # One of the two is prose in marketing copy naming o3 as a price reference.
    # Allowlisted rather than silently dropped: a literal that names a model
    # belongs in config even in copy, and phase 2 decides which entries are a
    # routing table and which are a description.
    "apps/digithings-web/lib/appPresets.ts": _Allowance(2, 2),
    "digillm/src/digillm/client.py": _Allowance(17, 17),
    # One refusal message naming the fallback model. A message is as much a
    # literal as a routing table -- the same reasoning #5046 applied when it
    # replaced digigraph's per-provider refusal examples.
    "scripts/validate_model_routing.py": _Allowance(1, 1),
}


def main() -> int:
    markers = configured_markers()
    all_files = list(iter_source_files())
    if not all_files:
        raise SystemExit("no production sources found; the guard would pass vacuously")

    found: dict[str, list[tuple[int, str]]] = {}
    for path in all_files:
        hits = scan(path, frozenset(markers))
        if hits:
            found[path.relative_to(REPO_ROOT).as_posix()] = hits

    unexpected = {name: hits for name, hits in found.items() if name not in KNOWN_REMAINING}
    stale = {
        name: (allowance, len(found.get(name, [])), len({text for _, text in found.get(name, [])}))
        for name, allowance in KNOWN_REMAINING.items()
        if len(found.get(name, [])) != allowance.occurrences
        or len({text for _, text in found.get(name, [])}) != allowance.distinct
    }

    for name, hits in sorted(unexpected.items()):
        detail = ", ".join(f"{line}: {text!r}" for line, text in hits[:5])
        more = f" (+{len(hits) - 5} more)" if len(hits) > 5 else ""
        print(f"FAIL {name}: {len(hits)} model name literal(s) — {detail}{more}", file=sys.stderr)
    for name, (allowance, occurrences, distinct) in sorted(stale.items()):
        print(
            f"FAIL {name}: allowlist expects {allowance.occurrences} literal(s) "
            f"({allowance.distinct} distinct), found {occurrences} ({distinct} distinct). "
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
