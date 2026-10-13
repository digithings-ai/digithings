#!/usr/bin/env python3
"""Fail when a tracked file carries a plaintext mailbox or account credential.

DIG-179. A live Proton Mail account name and password sat in plain text in a
committed twelve-x chat transcript (``inbox/chat/twelve-x/2026-05-28.txt`` in the
digithings-books repo). The shape that carried it was ordinary prose: a chat line
that names an account and then a bare token, and a line with the word "password"
and then the value. ``check_example_credentials.py`` cannot see either -- it only
reads ``VAR=value`` lines out of ``.example``/``.template`` files -- so a credential
typed into a chat export or a doc walked straight past the whole guard fleet.

This module is the prose half of the guard. It is deliberately standalone:

* **Coordinate, do not fork.** DIG-50 owns ``check_example_credentials.py`` and
  DIG-42 owns its CI wiring. Both are unmerged. Sharing a module with either would
  have coupled this fix to a merge that has not happened, so this file shares no
  code and can land first; unify the two once DIG-50 merges (see DIG-179).
* **Never prints a value.** A finding is ``path:line rule-id``. That is the whole
  output contract, because the CI log of a leaked-secret guard is the one place
  the value is most likely to get copied into a ticket.

Stdlib only; no install step. Add it to CI as its own unconditional job -- the
verdict is a property of the whole tracked tree, not of the diff, so a path filter
is the wrong tool for it.
"""

from __future__ import annotations

import math
import re
import subprocess
import sys
from pathlib import Path

# --------------------------------------------------------------------------
# Token model
# --------------------------------------------------------------------------

# Single non-space run. Used for "account then token" (shape A).
BARE_TOKEN = r"[A-Za-z0-9!@#$%^&*+=_.,:~-]{8,}"

# Private-mailbox domains. A company domain in a chat log is not a finding; a
# consumer mailbox that arrives with a bare token next to it is the DIG-179 shape.
PRIVATE_MAIL_DOMAINS = (
    "protonmail.com",
    "proton.me",
    "tutanota.com",
    "tuta.io",
    "fastmail.com",
    "gmx.com",
    "gmx.de",
    "gmx.net",
    "zohomail.com",
    "yahoo.com",
    "yahoo.fr",
    "hotmail.com",
    "hotmail.it",
    "outlook.com",
    "icloud.com",
    "me.com",
    "mail.com",
    "mail.ru",
    "yandex.com",
    "aol.com",
    "live.com",
    "orange.fr",
    "wanadoo.fr",
    "free.fr",
    "laposte.net",
    "sfr.fr",
    "bbox.fr",
    "numericable.fr",
    "club-internet.fr",
)

MAILBOX_RULE = re.compile(
    r"[A-Za-z0-9._%+-]+@(?:" + "|".join(re.escape(d) for d in PRIVATE_MAIL_DOMAINS) + r")"
    r"[\s:=|>,\-]{1,3}"
    r"(" + BARE_TOKEN + r")",
    re.IGNORECASE,
)

# Label-driven rule. DIG-179 shape B: "Le user password <value>" -- the label has
# no separator and the value is a passphrase that may contain spaces, so the tail
# of the line is captured and judged as prose-or-passphrase.
#
# Two labels are deliberately NOT here. `pass` alone is excluded because it is an
# ordinary English verb ("callers should pass threads already sorted") and cost 8
# false positives the moment it was switched on. `api key` / `access token` /
# `client secret` are excluded because they are assignment labels in source
# (`const apiKey = await resolve...`) and cost 107 more; that lane already belongs
# to check_example_credentials.py and gitleaks, and a second opinion there buys
# nothing but noise. What is left is the prose lane neither of them reaches.
LABEL_RULES: dict[str, re.Pattern[str]] = {
    "password-label": re.compile(
        r"\b(?:password|passwd|passphrase|pwd|mot\s+de\s+passe)\b"
        r"[\s:=|>]{0,3}(?:is|are|=|:)?[\s:=|>]*"
        r"([^\n]{8,64})",
        re.IGNORECASE,
    ),
}

# --------------------------------------------------------------------------
# Placeholder / reference / prose rejection
# --------------------------------------------------------------------------

# A value that is obviously a stand-in, a reference or a redaction marker. All
# comparisons are case-insensitive on the whole candidate.
PLACEHOLDER_SUBSTRINGS = (
    "redacted",
    "placeholder",
    "changeme",
    "change_me",
    "change-me",
    "replace",
    "your_",
    "your-",
    "your.",
    "example",
    "dummy",
    "sample",
    "fake",
    "xxxx",
    "****",
    "####",
    "....",
    "notareal",
    "not-a-real",
    "insert",
    "todo",
    "fixme",
    "tbd",
    "removed",
    "scrubbed",
)

# Characters/prefixes that mean "this is a pointer at something else", not a
# value: a path, a command, an env lookup, an interpolation.
REFERENCE_PREFIXES = (
    "$",
    "{",
    "%",
    "`",
    "#",
    "<",
    "(",
    "[",
    "@",
    "~/",
    "./",
    "/",
)

# Function words. A multi-word candidate that contains one is a sentence, not a
# passphrase. This is the single most important false-positive brake: real prose
# in this repo is full of "password is rotated every 90 days", and a passphrase
# does not contain "is".
STOPWORDS = frozenset(
    """
    a about above across after against all along also although always among and
    another any are around as at above behind below beneath beside besides between
    beyond both but by can cannot could did do does doing done down during each
    either else even ever every except few for from further had has have having
    he her here hers herself him himself his how however i if in inside instead
    into is it its itself just like made make makes many may maybe me might mine
    more most much must my myself neither never next no none nor not nothing now
    of off on once one only onto or other others ought our ours ourselves out
    outside over own perhaps please rather really same shall she should since so
    some still such than that the their theirs them themselves then there these
    they this those though through throughout thus till to together too toward
    towards under until up upon us use used using usually very via was way we
    well were what whatever when whenever where whereas wherever whether which
    while who whoever whom whose why will with within without would yet you your
    yours yourself yourselves get gets give given keep keeps kept must need needs
    read reads see sees set sets store stored stores storing value values
    get's let lets put puts
    """.split()
)

# Path and shell references that show up constantly in this repo's prose, plus
# the names of the sanctioned stores: a doc that says "password is in Bitwarden"
# is telling you where the value lives, not leaking it.
REFERENCE_SUBSTRINGS = (
    "/",
    "\\",
    "://",
    ".md",
    ".py",
    ".ts",
    ".yml",
    ".yaml",
    ".json",
    ".toml",
    ".sh",
    "os.environ",
    "process.env",
    "bws",
    "bw ",
    "dt-keys",
    "security find",
    "keychain",
    "bitwarden",
    "gitleaks",
    "dt-login",
    "supabase",
    "env(",
    "npx",
    "npm run",
    "make ",
    "uv run",
    "pnpm",
    "yarn",
    "grep ",
    "jq ",
    "curl ",
)

MIN_ENTROPY = 3.0
MIN_BARE_LEN = 8
MIN_PASSPHRASE_LEN = 16
MIN_PASSPHRASE_WORDS = 3
MAX_PASSPHRASE_WORDS = 8

# Characters that mean "this is code or punctuation, not a passphrase".
STRUCTURAL_CHARS = ('"', "{", "}", "[", "]", "|", "$")

# Reviewed exemptions. A prose guard is a heuristic, so a small, explicit and
# reasoned allowlist is the honest failure mode -- the alternative is a
# whole-tree path ignore, which is how guards quietly stop working. Every entry
# carries its reason; `_assert_allowlist_is_reviewed` fails the run if one loses
# its reason, and `test_check_plaintext_credentials.py` fails if the list grows
# past ALLOWLIST_CAP without a deliberate edit here.
ALLOWLIST: dict[str, str] = {
    "scripts/rls_proof/00_supabase_shim.sql:52": (
        "local-only stand-in role password for an offline RLS proof; no remote "
        "system is reachable with it (raised by this guard on DIG-179)"
    ),
}
ALLOWLIST_CAP = 10


def shannon_entropy(value: str) -> float:
    """Bits per character over the raw string."""
    if not value:
        return 0.0
    counts: dict[str, int] = {}
    for ch in value:
        counts[ch] = counts.get(ch, 0) + 1
    total = len(value)
    return -sum(
        (n / total) * math.log2(n / total) for n in counts.values()
    )


def char_classes(value: str) -> int:
    """How many of lower / upper / digit / symbol the value uses."""
    classes = 0
    if any(c.islower() for c in value):
        classes += 1
    if any(c.isupper() for c in value):
        classes += 1
    if any(c.isdigit() for c in value):
        classes += 1
    if any(not c.isalnum() for c in value):
        classes += 1
    return classes


def looks_masked(value: str) -> bool:
    """Runs of one repeated character standing in for a value."""
    if len(value) < 4:
        return False
    for ch in set(value):
        if ch.isalnum() and value.count(ch) / len(value) >= 0.75:
            return True
    return False


def is_placeholder(candidate: str) -> bool:
    low = candidate.lower()
    if any(p in low for p in PLACEHOLDER_SUBSTRINGS):
        return True
    if any(low.startswith(p) for p in REFERENCE_PREFIXES):
        return True
    if any(s in low for s in REFERENCE_SUBSTRINGS):
        return True
    if looks_masked(candidate.strip()):
        return True
    # An env-var style reference in the middle: $FOO, ${FOO}, %FOO%, <FOO>.
    if re.search(r"[$%<{]\s*[A-Z][A-Z0-9_]{2,}\s*[}%>]?$", candidate):
        return True
    return False


def is_prose(candidate: str) -> bool:
    """True when the candidate reads as a sentence rather than a value."""
    words = re.findall(r"[A-Za-z']+", candidate.lower())
    if not words:
        return True
    return any(w in STOPWORDS for w in words)


def _has_sentence_ending(candidate: str) -> bool:
    """Trim a captured tail at the first sentence boundary."""
    m = re.search(r"(?<=[.!?;])\s", candidate)
    if m:
        return True
    return False


def _trim_candidate(candidate: str) -> str:
    """Trim punctuation/quoting a chat line or doc sentence leaves behind."""
    value = candidate.strip()
    # Cut at the first inline-code span or markdown emphasis boundary.
    for stop in ("`", "**", "__", "\t"):
        idx = value.find(stop)
        if idx != -1:
            value = value[:idx]
    value = value.strip()
    value = value.rstrip(".,;:!?)]}\"'")
    return value.strip()


def judge_bare_token(token: str) -> tuple[bool, str]:
    """Decide whether a single whitespace-free token is a credential.

    Returns ``(is_credential, reason)``. The reason is a fixed vocabulary, never
    the token.
    """
    if len(token) < MIN_BARE_LEN:
        return False, "too-short"
    if is_placeholder(token):
        return False, "placeholder-or-reference"
    classes = char_classes(token)
    if classes < 2:
        return False, "single-char-class"
    entropy = shannon_entropy(token)
    if entropy < MIN_ENTROPY:
        return False, "low-entropy"
    if not any(c.isdigit() for c in token):
        # No digits and more than one class means a CamelCase or dashed word --
        # a product name, not a credential.
        return False, "no-digit"
    return True, "credential"


def judge_passphrase(candidate: str) -> tuple[bool, str]:
    """Decide whether a labelled, possibly multi-word value is a credential."""
    if len(candidate) < MIN_PASSPHRASE_LEN:
        return False, "too-short"
    if any(ch in candidate for ch in STRUCTURAL_CHARS):
        # A pipe is how a doc enumerates labels ("password|api_key|token"), and
        # quotes/braces are how a minified JSON blob keeps going. A passphrase
        # does not contain them; both shapes cost a false positive each when they
        # were allowed through.
        return False, "structural-characters"
    if is_placeholder(candidate):
        return False, "placeholder-or-reference"
    if _has_sentence_ending(candidate):
        return False, "sentence"
    words = candidate.split()
    if len(words) > MAX_PASSPHRASE_WORDS:
        return False, "too-many-words"
    if len(words) > 1:
        # A passphrase reads as 3+ content words. Two words is how compound
        # noun phrases after a label usually look ("leaked-password protection",
        # "password manager expressions"), and it is where the false positives
        # were.
        if len(words) < MIN_PASSPHRASE_WORDS:
            return False, "too-few-words"
        if is_prose(candidate):
            return False, "prose"
        if any(len(w.strip(".,;:!?")) < 3 for w in words):
            return False, "short-word"
    if shannon_entropy(candidate) < MIN_ENTROPY:
        return False, "low-entropy"
    return True, "credential"


def scan_text(text: str) -> list[tuple[int, str, str]]:
    """Return ``(line_number, rule_id, reason)`` for every finding in ``text``.

    The candidate value never leaves this function: findings carry the line
    number, the rule that fired and a fixed reason string.
    """
    findings: list[tuple[int, str, str]] = []
    seen: set[tuple[int, str]] = set()
    for lineno, line in enumerate(text.splitlines(), start=1):
        for match in MAILBOX_RULE.finditer(line):
            ok, reason = judge_bare_token(match.group(1))
            if ok and (lineno, "mailbox-account") not in seen:
                seen.add((lineno, "mailbox-account"))
                findings.append((lineno, "mailbox-account", reason))
        for rule_id, pattern in LABEL_RULES.items():
            for match in pattern.finditer(line):
                candidate = _trim_candidate(match.group(1))
                if not candidate:
                    continue
                ok, reason = judge_passphrase(candidate)
                if ok and (lineno, rule_id) not in seen:
                    seen.add((lineno, rule_id))
                    findings.append((lineno, rule_id, reason))
    return findings


def findings_for(rel_path: str, text: str) -> list[str]:
    """Rendered findings for one file, honouring the allowlist.

    Split out of ``main`` so the allowlist path is reachable in-process: the CLI
    runs the scan in a subprocess, where a test's in-memory allowlist edit would
    be invisible.
    """
    rendered = []
    for lineno, rule_id, reason in scan_text(text):
        location = f"{rel_path}:{lineno}"
        if location in ALLOWLIST:
            continue
        rendered.append(f"{location} {rule_id} ({reason})")
    return rendered


# --------------------------------------------------------------------------
# File selection
# --------------------------------------------------------------------------

# The guard must contain the shape it hunts, so its own source and its own test
# module are exempt. Nothing else in ``scripts/`` or ``tests/`` is: the list is
# exact, and `_assert_skip_list_is_tight` fails the run if it ever grows to cover
# anything but those two files and fixture corpora.
SELF_FILES = frozenset(
    {
        "scripts/check_plaintext_credentials.py",
        "tests/scripts/test_check_plaintext_credentials.py",
    }
)
FIXTURE_DIR_MARKERS = ("testdata/", "fixtures/")

BINARY_SUFFIXES = frozenset(
    {
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip", ".gz",
        ".bz2", ".xz", ".tar", ".7z", ".mp3", ".mp4", ".mov", ".woff", ".woff2",
        ".ttf", ".otf", ".eot", ".so", ".dylib", ".dll", ".exe", ".wasm",
        ".lock", ".sqlite", ".db", ".parquet", ".bin", ".safetensors",
    }
)

# Text-ish everything else; the read below sniffs for NUL rather than trusting it.
MAX_FILE_BYTES = 2_000_000


def is_skipped(path: str) -> bool:
    if path in SELF_FILES:
        return True
    normalised = path.replace("\\", "/")
    if any(f"/{marker}" in f"/{normalised}" for marker in FIXTURE_DIR_MARKERS):
        return True
    return False


def tracked_files(root: Path) -> list[Path]:
    """Tracked files under ``root``, or every file under it when not a repo.

    ``git ls-files`` prints paths relative to the **repository root**, not to the
    directory passed to ``-C``. Joining its output onto ``root`` therefore built
    paths that did not exist whenever ``root`` was a subdirectory of a repo --
    the scan read nothing and exited 0, which for a leak guard is the worst
    outcome available: green, and having checked zero files. Hence the toplevel
    probe: only trust ``ls-files`` when ``root`` really is the toplevel, and fall
    back to a filesystem walk otherwise.
    """
    try:
        toplevel = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=True,
        ).stdout.strip()
        if Path(toplevel).resolve() == root.resolve():
            result = subprocess.run(
                ["git", "-C", str(root), "ls-files", "-z"],
                stdout=subprocess.PIPE,
                text=True,
                check=True,
            )
            return [root / name for name in result.stdout.split("\0") if name]
    except Exception:
        pass
    return sorted(p for p in root.rglob("*") if p.is_file())


def read_text(path: Path) -> str | None:
    try:
        if path.suffix.lower() in BINARY_SUFFIXES:
            return None
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\0" in raw[:8192]:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")


def _assert_skip_list_is_tight() -> list[str]:
    """Return an error list; empty means the skip list is still honest."""
    problems = []
    for path in sorted(SELF_FILES):
        if not Path(__file__).resolve().parents[1].joinpath(path).is_file():
            problems.append(f"self-exempt path no longer exists: {path}")
    for path in sorted(UNEXPECTED_SKIPS):
        problems.append(f"skip list covers a non-self, non-fixture path: {path}")
    problems.extend(_assert_allowlist_is_reviewed())
    return problems


def _assert_allowlist_is_reviewed() -> list[str]:
    """Every exemption keeps a reason, and the list stays small."""
    problems = []
    for location, reason in sorted(ALLOWLIST.items()):
        if not reason or len(reason) < 20:
            problems.append(f"allowlist entry has no real reason: {location}")
        if not location.count(":") >= 1:
            problems.append(f"allowlist entry is not path:line: {location}")
    if len(ALLOWLIST) > ALLOWLIST_CAP:
        problems.append(
            f"allowlist holds {len(ALLOWLIST)} entries, over the cap of "
            f"{ALLOWLIST_CAP}: the heuristic is being papered over, not fixed"
        )
    return problems


# Kept empty on purpose; the test asserts it stays empty. A future edit that adds
# a real hit here would be papering over a leak rather than fixing it.
UNEXPECTED_SKIPS: frozenset[str] = frozenset()


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    root = Path.cwd()
    paths: list[Path] = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--root":
            index += 1
            root = Path(argv[index])
        elif arg == "--quiet":
            pass
        else:
            paths.append(Path(arg))
        index += 1

    if not paths:
        paths = tracked_files(root)
    else:
        # A relative positional path is relative to --root, not to the process
        # cwd. Resolving it against cwd instead made `--root X Y` silently read
        # nothing and exit 0, which for a leak guard is the worst possible
        # failure: a green build that checked no file.
        paths = [p if p.is_absolute() else root / p for p in paths]
        paths = [p for p in paths if p.is_file()]

    # A guard that reads zero files and prints OK is worse than no guard: it
    # converts a missing scan into a green build. Refuse to certify an empty set.
    if not paths:
        print(
            f"ERROR: no files to scan under {root}. A credential guard that "
            "checks nothing must not report OK.",
            file=sys.stderr,
        )
        return 2

    problems = _assert_skip_list_is_tight()
    findings: list[str] = []
    for path in paths:
        try:
            rel = path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            rel = path.as_posix()
        if is_skipped(rel):
            continue
        text = read_text(path)
        if text is None:
            continue
        findings.extend(findings_for(rel, text))

    if problems or findings:
        print(
            "ERROR: plaintext credential shapes found in tracked files. "
            "Only the path, line, rule and reason are printed -- the value is "
            "never echoed. Move the value into the sanctioned secret store, "
            "replace it in the file with a [REDACTED] marker, and rotate.",
            file=sys.stderr,
        )
        for line in problems + findings:
            print(f"  {line}", file=sys.stderr)
        return 1

    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())