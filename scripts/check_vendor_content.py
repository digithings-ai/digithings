#!/usr/bin/env python3
"""Vendor-content CI gate (DIG-2583, lane S of DIG-1415).

Every ref of this repository is fetchable, so content cannot be unpublished by
reviewing it out of the tree later: a gate that only triggers on "is merged"
never fires, because the moment it matters the ref is already public. This gate
therefore triggers on **content**, on every run, on every ref.

Two rule classes, deliberately different in strictness:

**Method-shaped rules (M*)** — a step a reader with nothing else could execute
to acquire a vendor credential. These fail on **any** hit. There is no
baseline and no grandfathering: Security's rule 3 is that "a redaction is not
an amendment", so leaving the recipe in place and marking it as removed is
itself the violation. ``M6`` is the shape Security named as the DIG-1434
regression fixture — a redaction marker followed by its own removed content.

**Vendor-identifier rules (V*)** — the identifier surface of a vendor: our own
env-var names, the vendor's public endpoints, its cookie/storage slot names and
its public brand word. Naming a vendor is not per se the leak; what matters is
that new names are a decision somebody took. These fail only on occurrences
that are **new relative to the merge base with ``main``**, and only when no
allowlist entry covers the path+symbol.

The allowlist (``scripts/vendor_content_allowlist.json``) is the record of what
was decided, so removing a keep is a visible diff rather than a silent
grandfather. Two sections:

``approved``
    Security + Counsel recorded their exception (DIG-1418 rule 2: the
    ``PRIMEMARKET_*`` env names and the desk login URL stay). Covered hits are
    reported as allowlisted and do not fail. This is the only section that means
    "somebody decided to keep this".

``pending``
    Content this gate surfaces that **nobody has approved**, in two kinds:

    - a **known method-shaped violation** being removed by another ticket's PR
      (DIG-1434, PR #5157), and
    - a **vendor identifier added to develop since the merge base** that Security
      has not yet ruled on.

    Every entry names an owner and a ticket, prints as ``allowlisted: NO
    (pending …)`` so nobody can mistake it for a sanctioned exception, and does
    not fail the build. This is *explicit* grandfathering, the opposite of
    Security's "grandfather nothing silently": every occurrence the gate forgives
    is written down, with the party who still owes a decision. When the content
    goes away the entry prints as ``RETIRED`` and asks to be deleted in the same
    diff.

    An ``approved`` entry naming a method rule is a hard error: method-shaped
    content is never approvable, it is removed (DIG-1418 rule 3).

No ``nolint``, no inline suppression, no skip-if-green. The only paths not
scanned are this script, its allowlist and its baseline test — the rule tables
necessarily contain the strings they hunt for, and all three are reviewed like
code.

Usage:
    check_vendor_content.py [--base-ref REF] [--warn] [--json] [--list-retired]

Exit codes:
    0  clean (or --warn)
    1  at least one unsanctioned finding
    2  tool / usage error — **fails closed**, never reports "clean"
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ALLOWLIST_PATH = Path(__file__).resolve().parent / "vendor_content_allowlist.json"

# The rule tables themselves necessarily spell the patterns they hunt for.
# These three files are reviewed like any other code and are the only paths the
# scan skips.
SELF_PATHS = frozenset(
    {
        "scripts/check_vendor_content.py",
        "scripts/vendor_content_allowlist.json",
        "tests/baseline/test_vendor_content_gate.py",
    }
)

BINARY_SNIFF_BYTES = 8192

# Resolved, not hardcoded: every other script in this repo calls bare "git", and
# a path that only exists on one developer's machine turns this gate into a
# tool error (exit 2) on CI.
GIT = shutil.which("git") or "git"

# M6 is a proximity rule. How many lines either side of a redaction marker count
# as "the content the marker claims to have removed is still here".
REDACTION_WINDOW = 12


# --------------------------------------------------------------------------
# Rule table
# --------------------------------------------------------------------------
# ``ere`` is the POSIX-extended regex handed to ``git grep`` for the merge-base
# comparison (V rules only). ``re`` is the Python regex used for the working
# tree scan; for V rules the two are equivalent by construction.


@dataclass(frozen=True)
class Rule:
    id: str
    name: str
    why: str
    pattern: re.Pattern[str]
    cls: str  # "method" | "vendor"
    ere: str = ""


_VENDOR_SLOTS = r"pmt_auth_token|__Secure-gloomberb[.a-z0-9_-]*|gloomberb[.]session_token"
_VENDOR_HOSTS = r"https?://[a-z0-9.-]*prime-terminal[.]com|https?://[a-z0-9.-]*gloom[.]sh"

RULES: tuple[Rule, ...] = (
    # ---- method-shaped: any hit fails -----------------------------------
    Rule(
        id="M1",
        name="storage-slot-access",
        why="reads a named slot out of the browser's storage; Security DIG-1418 rule 2 rules this shape out",
        cls="method",
        pattern=re.compile(
            r"(?:local|session)Storage\s*[.[]|document\s*\.\s*cookie"
            r"|Storage\s*\.\s*getItem\s*\(",
            re.IGNORECASE,
        ),
    ),
    Rule(
        id="M2",
        name="devtools-to-storage-steps",
        why="turns 'look in the browser' into a mechanical unattended extraction",
        cls="method",
        pattern=re.compile(r"dev\s?tools?", re.IGNORECASE),
    ),
    Rule(
        id="M3",
        name="application-storage-navigation",
        why="the click path to the cookie jar; executable without any other input",
        cls="method",
        pattern=re.compile(
            r"Application\s*(?:/|→|->|›|>|\\|&#8212;)\s*Storage"
            r"|Application.{0,30}\bStorage\b\s*(?:→|->|›|>|tab|panel|pane)"
            r"|\bStorage\b\s*(?:→|->|›|>)\s*(?:→|->|›|>)?\s*\bCookies\b",
            re.IGNORECASE,
        ),
    ),
    Rule(
        id="M4",
        name="copy-the-credential-prose",
        why="an instruction to read a credential out of the page and put it somewhere",
        cls="method",
        pattern=re.compile(
            # `(?<![A-Za-z0-9_-])` keeps "single-copy secret drift-detectable"
            # and Docker's `COPY digikey/…` out; `[Cc]opy` keeps prose
            # ("Copy the value of …") in while leaving the all-caps Dockerfile
            # instruction alone.
            r"(?<![A-Za-z0-9_-])[Cc]opy\b\s+"
            r"(?:the\s+|its\s+|that\s+|your\s+|over\s+)?"
            r"(?:value\s+of\s+|contents?\s+of\s+)?[\w'\"`\-]{0,48}?"
            r"\b(?:tokens?|cookies?|sessions?|credentials?|secrets?|api[\s_-]?keys?)\b"
        ),
    ),
    Rule(
        id="M5",
        name="session-extraction-prose",
        why="names the acquisition act itself rather than the mechanism it uses",
        cls="method",
        pattern=re.compile(
            r"\bextract(?:s|ed|ing)?\s+the\s+(?:session|cookie|token|credential)s?\b"
            r"|\bsession\s+extraction\b",
            re.IGNORECASE,
        ),
    ),
    Rule(
        id="M6",
        name="redaction-marker-then-removed-content",
        why=(
            "DIG-1434 fixture: a marker saying the step was removed, with the step "
            "still present within REDACTION_WINDOW lines of it. Proximity is the "
            "whole rule: a marker on its own IS the shape Security DIG-1418 rule 3 "
            "prescribes ('mechanism named, key and steps absent'), so M6 must not "
            "fire on one — see _redaction_markers"
        ),
        cls="method",
        pattern=re.compile(
            r"(?:\[REDACTED|\[(?:acquisition|cookie|credential)[^\]]{0,40}removed[^\]]*\]"
            r"|\b(?:steps?|content|instructions?|acquisition|micro-steps?)\b[^.\n]{0,40}"
            r"\b(?:removed|redacted|withheld)\b"
            r"|\bnot\s+published\s+in\s+this\s+repo\b)",
            re.IGNORECASE,
        ),
    ),
    Rule(
        id="M7",
        name="committed-credential-shape",
        why=(
            "a value, not a name: nothing about a secret is publishable, whatever "
            "the vendor. Generic secret-shape sweeping (including non-vendor JWTs) "
            "is scripts/check_example_credentials.py's job, not this gate's"
        ),
        cls="method",
        pattern=re.compile(r"eyJ[A-Za-z0-9_-]{10,}[.][A-Za-z0-9_-]{4,}"),
    ),
    # ---- vendor identifiers: new-since-merge-base only -------------------
    Rule(
        id="V1",
        name="vendor-session-env-names",
        why="our own env names for a vendor session; Security DIG-1418 rule 2 keeps them, so they need an approver",
        cls="vendor",
        pattern=re.compile(r"\bPRIMEMARKET_[A-Z][A-Z0-9_]*\b|\bPMT_[A-Z][A-Z0-9_]{2,}\b"),
        ere=r"PRIMEMARKET_[A-Z][A-Z0-9_]*|PMT_[A-Z][A-Z0-9_]{2,}",
    ),
    Rule(
        id="V2",
        name="vendor-public-endpoint",
        why="the vendor's web surface; kept for provenance (DIG-1418 rule 2) but only with an approver",
        cls="vendor",
        pattern=re.compile(_VENDOR_HOSTS, re.IGNORECASE),
        ere=_VENDOR_HOSTS.replace("[.]", r"\."),
    ),
    Rule(
        id="V3",
        name="vendor-storage-slot-name",
        why="a name that exists only on the vendor's own page; the brief never allows this one",
        cls="vendor",
        pattern=re.compile(_VENDOR_SLOTS, re.IGNORECASE),
        ere=_VENDOR_SLOTS.replace("[.]", r"\."),
    ),
    Rule(
        id="V4",
        name="vendor-public-brand-word",
        why="new mentions of the vendor are a decision somebody took; the rename is out of scope here",
        cls="vendor",
        pattern=re.compile(r"(?<![A-Za-z0-9_])prime[ -]?market", re.IGNORECASE),
        ere=r"(^|[^A-Za-z0-9_])prime[ -]?market",
    ),
    Rule(
        id="V5",
        name="vendor-cookie-slot-and-endpoint",
        why="the Gloomberb cookie/endpoint surface; new occurrences need a named approver",
        cls="vendor",
        pattern=re.compile(
            r"https?://[a-z0-9.-]*gloom[.]sh|__Secure-gloomberb[.a-z0-9_-]*|gloomberb[.]session_token",
            re.IGNORECASE,
        ),
        ere=r"https?://[a-z0-9.-]*gloom\.sh|__Secure-gloomberb[.a-z0-9_-]*|gloomberb[.]session_token",
    ),
)

# V3 covers the storage-slot NAME. Where that name is reached through a storage
# API it is M1 (never allowlistable). M wins: an M hit is reported as M.
METHOD_RULES = tuple(r for r in RULES if r.cls == "method")
VENDOR_RULES = tuple(r for r in RULES if r.cls == "vendor")


# --------------------------------------------------------------------------
# Allowlist
# --------------------------------------------------------------------------

#: Finding statuses that a pending allowlist entry can produce. Neither is
#: blocking unless ``--enforce-pending`` is passed (board, 2026-10-09, DIG-2583).
#:
#: ``pending``       — a pending entry covers the hit and its recorded text is
#:                    still there. Report-only, decision still owed.
#: ``pending-drift`` — a pending entry covers the hit but the recorded ``match``
#:                    text no longer appears in what the rule matched, so the
#:                    entry has gone stale. Still report-only; reported loudly
#:                    because a stale entry is how an allowlist silently outlives
#:                    what it excuses.
PENDING_STATUSES = ("pending", "pending-drift")

DRIFT_NOTE = (
    " [DRIFT: the recorded 'match' text no longer appears here. Still report-only "
    "until Security rules, but this entry is stale and should be re-checked.]"
)


@dataclass
class Allowlist:
    approved: list[dict] = field(default_factory=list)
    pending: list[dict] = field(default_factory=list)

    def approved_for(self, rule_id: str, path: str, matched: str) -> dict | None:
        for entry in self.approved:
            if entry.get("rule") != rule_id:
                continue
            if not _path_covers(entry, path):
                continue
            if _symbol_covers(entry, matched):
                return entry
        return None

    def resolve_pending(
        self, rule_id: str, path: str, matched: str
    ) -> tuple[dict | None, bool]:
        """Find the pending entry covering ``rule_id`` at ``path``.

        Scope is **rule + path**. The ``match`` needle is *evidence*, not a
        condition of suppression.

        Why (board, 2026-10-09, DIG-2583): a pending entry records content nobody
        has ruled on yet, so it is report-only until Security rules. Scoping the
        suppression to a literal substring of the matched text meant that a
        cosmetic reword by an unrelated PR — ``localStorage['pmt_auth_token']``
        becoming ``localStorage.getItem('pmt_auth_token')``, which matches the same
        rule through a different alternative — silently ended the suppression and
        turned the recorded finding into a hard FAIL. That is exactly the cascade
        the board asked to be prevented: an undecided record blocking whatever PR
        happened to touch the line.

        A stale entry is therefore *reported* (``pending-drift``), never converted
        into a block. ``--enforce-pending`` restores the blocking behaviour in one
        flag when Security is ready to rule.

        Returns ``(entry, drifted)``. ``entry is None`` means no pending entry
        covers this rule at this path and the caller must fail the finding.
        """
        scoped: dict | None = None
        for entry in self.pending:
            if entry.get("rule") != rule_id:
                continue
            if not _path_covers(entry, path):
                continue
            needle = entry.get("match")
            if needle and needle.lower() in matched.lower():
                return entry, False
            if scoped is None:
                scoped = entry
        if scoped is None:
            return None, False
        return scoped, True


def _glob_to_re(glob: str) -> re.Pattern[str]:
    return re.compile("(?s:" + re.escape(glob).replace(r"\*", ".*").replace(r"\?", ".") + ")")


def _path_covers(entry: dict, path: str) -> bool:
    raw = entry.get("path", "")
    return bool(raw) and _glob_to_re(raw).fullmatch(path) is not None


def _symbol_covers(entry: dict, matched: str) -> bool:
    symbol = entry.get("symbol")
    if not symbol:
        return True
    return symbol.lower() in matched.lower()


def load_allowlist(path: Path) -> Allowlist:
    if not path.exists():
        raise FileNotFoundError(f"allowlist not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError(f"unsupported allowlist schema_version: {data.get('schema_version')!r}")
    for key in ("approved", "pending"):
        if not isinstance(data.get(key), list):
            raise ValueError(f"allowlist section {key!r} must be a list")
    for entry in data["approved"] + data["pending"]:
        for required in ("rule", "path", "owner", "ticket", "reason"):
            if not entry.get(required):
                raise ValueError(f"allowlist entry missing {required!r}: {entry!r}")
    known = {r.id for r in RULES}
    for entry in data["approved"] + data["pending"]:
        if entry["rule"] not in known:
            raise ValueError(f"allowlist entry names unknown rule {entry['rule']!r}")
        if entry["rule"] in {r.id for r in METHOD_RULES} and entry in data["approved"]:
            raise ValueError(
                f"allowlist 'approved' names method rule {entry['rule']!r}: "
                "method-shaped content is never approvable, it is removed (DIG-1418 rule 3)"
            )
    return Allowlist(data["approved"], data["pending"])


# --------------------------------------------------------------------------
# Scanning
# --------------------------------------------------------------------------


@dataclass
class Finding:
    rule: Rule
    path: str
    lineno: int
    matched: str
    status: str  # "allowlisted" | "pending" | "pending-drift" | "FAIL"
    note: str = ""


def git(*args: str) -> str:
    """Run git and return stdout.

    ``git grep`` has its own exit-code contract: 0 = matched, 1 = **no match**,
    >= 2 = a real error. Only >= 2 is a tool error here. Getting this wrong is
    invisible in this repo - every vendor pattern matches something in the digithings
    history - and turns a clean scan into a tool error, which fails closed with a
    message that reads like the gate is broken.
    """
    proc = subprocess.run(
        [GIT, *args], cwd=REPO, capture_output=True, text=True, errors="replace"
    )
    if proc.returncode == 1 and args and args[0] == "grep":
        return ""
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed ({proc.returncode}): {proc.stderr.strip()}")
    return proc.stdout


def tracked_files() -> list[str]:
    raw = git("ls-files", "-z")
    return [p for p in raw.split("\0") if p]


def read_text(rel: str) -> str | None:
    try:
        blob = (REPO / rel).read_bytes()
    except (FileNotFoundError, IsADirectoryError, PermissionError):
        return None
    if b"\x00" in blob[:BINARY_SNIFF_BYTES]:
        return None
    try:
        return blob.decode("utf-8")
    except UnicodeDecodeError:
        return None


def resolve_base(base_ref: str) -> str:
    """Merge-base of HEAD and base_ref, so the baseline is the fork point."""
    proc = subprocess.run(
        [GIT, "merge-base", "HEAD", base_ref],
        cwd=REPO,
        capture_output=True,
        text=True,
        errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"cannot compute merge-base(HEAD, {base_ref}): {proc.stderr.strip()}. "
            "A shallow or single-commit checkout cannot baseline 'new' occurrences — "
            "fetch enough history (actions/checkout fetch-depth: 0)."
        )
    return proc.stdout.strip()


def baseline_pairs(base: str) -> set[tuple[str, str]]:
    """(path, stripped line) pairs present at the baseline ref, per vendor rule."""
    pairs: set[tuple[str, str]] = set()
    for rule in VENDOR_RULES:
        prefix = f"{base}:"
        for line in git("grep", "-I", "-n", "-E", rule.ere, base, "--").splitlines():
            if not line.startswith(prefix):
                continue
            path, _, body = line[len(prefix) :].split(":", 2)
            pairs.add((path, body.strip()))
    return pairs


def scan(base: str, allowlist: Allowlist) -> tuple[list[Finding], list[str]]:
    findings: list[Finding] = []
    notes: list[str] = []
    baseline = baseline_pairs(base)
    files = tracked_files()

    for rel in files:
        if rel in SELF_PATHS:
            continue
        text = read_text(rel)
        if text is None:
            continue
        lines = text.splitlines()
        method_hits: dict[str, tuple[int, str]] = {}
        for rule in METHOD_RULES:
            hit = _first_match(lines, rule)
            if hit is not None:
                method_hits[rule.id] = hit
        method_hits = _drop_unwitnessed_markers(method_hits)
        vendor_hits: list[tuple[Rule, int, str]] = []
        for rule in VENDOR_RULES:
            for idx, line in enumerate(lines, start=1):
                found = rule.pattern.search(line)
                if found:
                    vendor_hits.append((rule, idx, found.group(0)))

        for rule in METHOD_RULES:
            if rule.id not in method_hits:
                continue
            lineno, matched = method_hits[rule.id]
            entry, drifted = allowlist.resolve_pending(rule.id, rel, matched)
            if entry is not None:
                findings.append(
                    Finding(
                        rule,
                        rel,
                        lineno,
                        matched,
                        "pending-drift" if drifted else "pending",
                        f"{entry['ticket']} ({entry['owner']}): {entry['reason']}"
                        + (DRIFT_NOTE if drifted else ""),
                    )
                )
            else:
                findings.append(Finding(rule, rel, lineno, matched, "FAIL"))

        for rule, lineno, line in vendor_hits:
            matched = rule.pattern.search(lines[lineno - 1]).group(0)  # type: ignore[union-attr]
            if (rel, lines[lineno - 1].strip()) in baseline:
                continue
            entry = allowlist.approved_for(rule.id, rel, matched)
            if entry is not None:
                findings.append(
                    Finding(rule, rel, lineno, matched, "allowlisted",
                            f"{entry['owner']} — {entry['ticket']}: {entry['reason']}")
                )
                continue
            entry, drifted = allowlist.resolve_pending(rule.id, rel, matched)
            if entry is not None:
                findings.append(
                    Finding(
                        rule,
                        rel,
                        lineno,
                        matched,
                        "pending-drift" if drifted else "pending",
                        f"{entry['ticket']} ({entry['owner']}) owes the decision: "
                        f"{entry['reason']}" + (DRIFT_NOTE if drifted else ""),
                    )
                )
            else:
                findings.append(Finding(rule, rel, lineno, matched, "FAIL"))

    # Retirement pass: a pending entry whose content has been removed.
    #
    # This is a *notice*, not a failure. The content that fixes it belongs to
    # another ticket's PR, so failing here would make develop go red on the
    # strength of a merge that is exactly the fix. The notice is what forces the
    # entry to be deleted in the same diff as the content, so the allowlist can
    # never quietly outlive what it excuses.
    for entry in allowlist.pending:
        needle = str(entry.get("match", ""))
        if not needle:
            notes.append(
                f"  UNVERIFIABLE {entry['rule']} {entry['path']} — pending entry has no "
                f"'match' needle, so it can never be retired automatically ({entry['ticket']})."
            )
            continue
        glob = _glob_to_re(entry["path"])
        still_there = False
        for rel in files:
            if rel in SELF_PATHS or not glob.fullmatch(rel):
                continue
            text = read_text(rel)
            if text and needle.lower() in text.lower():
                still_there = True
                break
        if not still_there:
            notes.append(
                f"  RETIRED {entry['rule']} {entry['path']} — the content is gone; delete this "
                f"pending entry in the same diff ({entry['ticket']})."
            )
    return findings, notes


def _drop_unwitnessed_markers(
    method_hits: dict[str, tuple[int, str]],
) -> dict[str, tuple[int, str]]:
    """Keep an M6 marker only when the content it claims to have removed is there.

    Security DIG-1418 rule 3 prescribes the compliant shape as *mechanism named,
    key and steps absent* — a sentence saying the acquisition procedure is not
    published, with nothing to execute. PR #5157 writes exactly that, so a gate
    that fired on the marker alone would fail the approved redaction. M6 is the
    DIG-1434 fixture instead: the marker AND the step it claims to be gone, in
    the same window. So M6 survives only next to another method hit.
    """
    if "M6" not in method_hits:
        return method_hits
    marker_line = method_hits["M6"][0]
    witnessed = any(
        rule_id != "M6" and abs(lineno - marker_line) <= REDACTION_WINDOW
        for rule_id, (lineno, _m) in method_hits.items()
    )
    if not witnessed:
        method_hits = dict(method_hits)
        method_hits.pop("M6")
    return method_hits


def _first_match(lines: list[str], rule: Rule) -> tuple[int, str] | None:
    """First hit for ``rule`` in ``lines``.

    Every method rule is a rule about a *vendor* credential acquisition method,
    not about the shape in the abstract: `localStorage.getItem('theme')` in a
    dashboard is ordinary first-party code, and `devtools` in a security-headers
    note is prose. So a method rule only fires when a vendor reference sits near
    the match: inside the tight line window, or — in prose — anywhere in the
    enclosing markdown section, because a recipe routinely runs longer than a
    four-line window between the vendor's name and the step. M7 is scoped the
    same way: a bare JWT sweep of every tracked file is
    `scripts/check_example_credentials.py`'s job, not this gate's, and the
    canonical RFC-7519 example token in `tests/dsk/test_security.py` is not a
    vendor credential.
    """
    for idx, line in enumerate(lines, start=1):
        found = rule.pattern.search(line)
        if not found:
            continue
        lo = max(0, idx - 3)
        blob = "\n".join(lines[lo : idx + 2])
        if not VENDOR_CONTEXT.search(blob) and not _section_has_vendor(lines, idx):
            continue
        return idx, found.group(0)
    return None


def _section_has_vendor(lines: list[str], idx: int) -> bool:
    """True when the markdown section around line ``idx`` names the vendor.

    Scoped to ``#``-delimited sections on purpose: a file-level test would make
    one vendor mention somewhere license a method hit anywhere in the file, and
    a whole-file window in prose would do the same across an unrelated
    appendix. In a file with no headings this is always False, so code keeps the
    tight window only.
    """
    start = 0
    for pos in range(idx - 1, -1, -1):
        if lines[pos].lstrip().startswith("#"):
            start = pos
            break
    end = len(lines)
    for pos in range(idx, len(lines)):
        if lines[pos].lstrip().startswith("#"):
            end = pos
            break
    if end <= start:
        return False
    return bool(VENDOR_CONTEXT.search("\n".join(lines[start:end])))


# A vendor reference in the window is what makes a method rule a vendor-content
# rule. Deliberately wide (it only ever widens a *report*, never silences one)
# so a rename cannot smuggle the recipe past it.
VENDOR_CONTEXT = re.compile(
    r"prime[ _-]?market|prime-terminal|desk\.prime|pmt_|_pmt\b|\bpmt-|PMT_|PMT_[A-Z]"
    r"|gloomberb|gloom\.sh|GLOOMBERB|__Secure-gloom",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def _gh_escape(text: str) -> str:
    """Escape a value for a GitHub Actions workflow command.

    ``%``, ``\\r`` and ``\\n`` are the documented escapes; an unescaped newline
    would terminate the command early and the rest of the message would be
    printed as plain log output, which is the one place an annotation would
    silently stop being an annotation.
    """
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def annotations(findings: list[Finding], enforce_pending: bool) -> None:
    """Emit a workflow-command annotation for every non-allowlisted finding.

    A report-only finding that only appears in the log is invisible on the PR
    page, which is the whole reason the board accepted it. ``::error`` when
    ``--enforce-pending`` is set (it is blocking then), ``::warning`` otherwise.
    """
    level = "error" if enforce_pending else "warning"
    for f in findings:
        if f.status not in PENDING_STATUSES:
            continue
        title = (
            "PENDING-DRIFT" if f.status == "pending-drift" else "PENDING"
        )
        print(
            f"::{level} title={title} {_gh_escape(f.rule.id)} {_gh_escape(f.rule.name)}::"
            f"{_gh_escape(f.path)}:{f.lineno}: {_gh_escape(f.matched)}"
        )


def report(
    findings: list[Finding], notes: list[str], base: str, enforce_pending: bool = False
) -> None:
    fails = [f for f in findings if f.status == "FAIL"]
    pending = [f for f in findings if f.status == "pending"]
    drift = [f for f in findings if f.status == "pending-drift"]
    allowed = [f for f in findings if f.status == "allowlisted"]
    print(f"vendor-content gate: baseline {base[:12]} (merge-base with main)")
    print(
        f"  {len(fails)} failing, {len(pending)} pending a decision, "
        f"{len(drift)} pending-drift (recorded text no longer matches), "
        f"{len(allowed)} allowlisted"
    )
    if (pending or drift) and not enforce_pending:
        print(
            "  pending entries are REPORT-ONLY (board, 2026-10-09, DIG-2583): they do not fail"
        )
        print(
            "  this check and do not block the PR. --enforce-pending makes every one of them fail."
        )
    for f in sorted(findings, key=lambda x: (x.status != "FAIL", x.path, x.lineno)):
        if f.status in PENDING_STATUSES:
            continue
        print(f"  {f.path}:{f.lineno}  {f.status.upper()}  [{f.rule.id} {f.rule.name}]")
        print(f"      matched: {f.matched!r}")
        if f.note:
            print(f"      {f.note}")
    if pending or drift:
        print("\n  pending — NOT approved, printed so the decision stays visible:")
        for f in sorted(pending + drift, key=lambda x: (x.path, x.lineno)):
            marker = "  PENDING-DRIFT" if f.status == "pending-drift" else ""
            print(
                f"    {f.path}:{f.lineno}  allowlisted: NO  [{f.rule.id} {f.rule.name}]{marker}"
            )
            print(f"        matched: {f.matched!r}")
            print(f"        {f.note}")
    if notes:
        print("\n  housekeeping:")
        for note in notes:
            print(note)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="vendor-content CI gate")
    parser.add_argument("--base-ref", default="origin/main")
    parser.add_argument("--allowlist", default=str(ALLOWLIST_PATH))
    parser.add_argument("--warn", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--enforce-pending",
        action="store_true",
        help="treat pending allowlist findings as failures (off by default: board "
        "decision 2026-10-09, DIG-2583 — pending entries are report-only until "
        "Security rules on them, so they must not block the weekend push)",
    )
    args = parser.parse_args(argv)

    try:
        allowlist = load_allowlist(Path(args.allowlist))
        base = resolve_base(args.base_ref)
        findings, notes = scan(base, allowlist)
    except Exception as exc:  # fail closed on ANY tool error, deliberate bare catch
        print(f"vendor-content gate: FAIL (tool error) — {type(exc).__name__}: {exc}")
        print("  This gate fails closed: a tool error is never reported as clean.")
        return 2

    fails = [f for f in findings if f.status == "FAIL"]
    pending_blocking: list[Finding] = (
        [f for f in findings if f.status in PENDING_STATUSES] if args.enforce_pending else []
    )
    if args.json:
        print(
            json.dumps(
                {
                    "base": base,
                    "enforce_pending": args.enforce_pending,
                    "blocking_count": len(fails) + len(pending_blocking),
                    "fails": [
                        {
                            "rule": f.rule.id,
                            "name": f.rule.name,
                            "path": f.path,
                            "line": f.lineno,
                            "matched": f.matched,
                            "allowlisted": False,
                        }
                        for f in fails
                    ],
                    "pending": [
                        {
                            "rule": f.rule.id,
                            "path": f.path,
                            "line": f.lineno,
                            "matched": f.matched,
                            "allowlisted": False,
                            "drift": f.status == "pending-drift",
                            "note": f.note,
                        }
                        for f in findings
                        if f.status in PENDING_STATUSES
                    ],
                    "allowlisted": [
                        {
                            "rule": f.rule.id,
                            "path": f.path,
                            "line": f.lineno,
                            "matched": f.matched,
                            "allowlisted": True,
                            "note": f.note,
                        }
                        for f in findings
                        if f.status == "allowlisted"
                    ],
                    "notes": notes,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        report(findings, notes, base, enforce_pending=args.enforce_pending)
        annotations(findings, args.enforce_pending)

    blocking = list(fails) + pending_blocking
    if blocking:
        # `--json` output is only parseable while it is the only thing on stdout.
        # The advisory is a human sentence; a consumer calling json.loads(stdout)
        # would fail on exactly the run that has the most to say.
        if not args.json:
            if fails:
                print(
                    "\nA method-shaped hit (M*) is never allowlistable: remove the step.\n"
                    "A vendor-identifier hit (V*) that is new since the merge base with main\n"
                    "needs either removal or an entry in scripts/vendor_content_allowlist.json\n"
                    "naming Security and Counsel as approvers. No nolint, no baseline bypass."
                )
            if pending_blocking:
                print(
                    f"\n--enforce-pending is set: {len(pending_blocking)} pending "
                    "finding(s) are being treated as failures."
                )
        return 0 if args.warn else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())