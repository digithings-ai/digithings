#!/usr/bin/env python3
"""What does not count as a review pass (DIG-4631).

Three shapes of review evidence were counted as a review pass on 20 Oct 2026
and let five PRs into ``develop`` without a real review:

1. the PR's own author resolved the review threads;
2. the review was posted seconds after the head push it claims to cover;
3. the review text was copied from another PR.

Every seat posts under the same GitHub login, so a login comparison cannot
separate the author from another seat: the seat has to be read from the
identity marker (``<!-- dt-seat agent=... -->``) or the run/session trailer
(``Paperclip-Agent-Id:`` / ``Session-Id:``) that the writing seat leaves
behind. This module is the one place that reads those markers, so the
local-ci ``review-applied`` producer and the merge queue agree on what a
review pass is.

Shape: pure functions over injected data, plus a small rolling corpus of
recent review texts so a copy can be recognised against another PR.
Stdlib only, and Python 3.9 compatible (the live producer runs on
``/usr/bin/python3``).
"""

from __future__ import annotations

import difflib
import json
import os
import re
import time
from typing import Any

# A review posted this close to the push it claims to cover was not written
# against that push.
PUSH_WINDOW_SECONDS = 60

# Normalised review texts at least this similar count as the same text.
SIMILARITY_THRESHOLD = 0.9

# How long a review text stays in the rolling corpus.
CORPUS_WINDOW_SECONDS = 24 * 3600

# Where the rolling corpus lives. The env override keeps a test or a
# throwaway run out of the shared state file.
CORPUS_PATH_ENV = "DIGITHINGS_REVIEW_CORPUS"
DEFAULT_CORPUS_PATH = os.path.join(
    os.path.expanduser("~"), ".config", "digithings", "review-pass-corpus.json"
)

# ---------------------------------------------------------------------------
# Seat identity: the marker and the trailers a seat leaves behind
# ---------------------------------------------------------------------------

SEAT_FIELD_KINDS = {
    "agent": "seat",
    "seat": "seat",
    "run": "run",
    "session": "session",
}
SEAT_TRAILER_KINDS = {
    "paperclip-agent-id": "seat",
    "paperclip-agent": "seat",
    "paperclip-seat": "seat",
    "paperclip-run-id": "run",
    "session-id": "session",
}
SEAT_MARKER_RE = re.compile(r"<!--\s*dt-seat\b(?P<fields>[^>]*?)\s*-->")
POWER_PACK_MARKER_RE = re.compile(
    r"<!--\s*opencode-power-pack:code-review\b(?P<fields>[^>]*?)\s*-->"
)
MARKER_FIELD_RE = re.compile(r"(?P<key>[A-Za-z_][A-Za-z0-9_.-]*)=(?P<value>\S+)")
SEAT_TRAILER_RE = re.compile(
    r"^[ \t>*_-]*(?P<key>Paperclip-Agent-Id|Paperclip-Agent|Paperclip-Seat|"
    r"Paperclip-Run-Id|Session-Id)[*_`]*[ \t]*:[ \t]*[*_`]*[ \t]*"
    r"(?P<value>[A-Za-z0-9][A-Za-z0-9._:/@-]*)",
    re.I | re.M,
)
PLACEHOLDER_IDS = frozenset({"?", "-", "none", "null", "unknown", "n/a", "tbd"})


def identity_from_text(text):
    """Seat / session / run ids named by ``text``.

    Reads the marker fields and the line-anchored trailers only, never prose.
    Returns ``{kind: frozenset(values)}`` with the kinds ``seat``,
    ``session`` and ``run``.
    """
    found = {}

    def add(kind, value):
        if not kind:
            return
        value = str(value or "").strip().strip("'\";,.`").lower()
        if not value or value in PLACEHOLDER_IDS or value.startswith("$"):
            return
        found.setdefault(kind, set()).add(value)

    for regex in (SEAT_MARKER_RE, POWER_PACK_MARKER_RE):
        for marker in regex.finditer(text or ""):
            for field in MARKER_FIELD_RE.finditer(marker.group("fields")):
                add(SEAT_FIELD_KINDS.get(field.group("key").lower()), field.group("value"))
    for trailer in SEAT_TRAILER_RE.finditer(text or ""):
        add(
            SEAT_TRAILER_KINDS.get(trailer.group("key").lower()),
            trailer.group("value"),
        )
    return {kind: frozenset(values) for kind, values in found.items()}


def merge_identities(*identities):
    """Union of several identities."""
    merged = {}
    for identity in identities:
        for kind, values in (identity or {}).items():
            merged.setdefault(kind, set()).update(values or ())
    return {kind: frozenset(values) for kind, values in merged.items()}


def _commit_texts(pr):
    """Commit message texts of a PR, in either payload shape."""
    texts = []
    for commit in (pr or {}).get("commits") or []:
        if not isinstance(commit, dict):
            continue
        if "messageHeadline" in commit or "messageBody" in commit:
            texts.append(
                "%s\n%s"
                % (commit.get("messageHeadline") or "", commit.get("messageBody") or "")
            )
            continue
        inner = commit.get("commit")
        if isinstance(inner, dict) and inner.get("message"):
            texts.append(str(inner.get("message")))
    return texts


def author_identity(pr):
    """The seat / session / run that authored the PR.

    Reads the PR body and the commit messages, which is where a seat leaves
    its marker or trailer. Returns ``{}`` when the PR names no seat at all.
    """
    texts = [(pr or {}).get("body") or ""]
    texts.extend(_commit_texts(pr))
    return merge_identities(*[identity_from_text(t) for t in texts])


def show_identity(identity):
    """Human-readable identity, for a reason string."""
    parts = []
    for kind in ("seat", "session", "run"):
        values = sorted((identity or {}).get(kind) or ())
        if values:
            parts.append("%s=%s" % (kind, ", ".join(values)))
    return " ".join(parts) if parts else "nothing"


def independence_reason(author, reviewer, require_markers=True):
    """Why a review is not independent of the PR's author, or ``None``.

    With ``require_markers`` on (the strict rule) the arm fails closed:
    without a named seat on both sides the two cannot be told apart, and every
    seat posts under the author's login.

    With ``require_markers`` off the arm only refuses a *proven* self-review
    — one that names the author's own seat, session or run. A missing marker
    no longer refuses, because nothing writes one yet: the strict rule was
    introduced without a producer (DIG-4646), so it refused every same-login
    review in the fleet and emptied the queue. The overlap check is the part
    that is always safe: it refuses a review that names the authoring seat
    itself, whatever the flags say.

    The caller's own gate decides when the strict rule applies; the switch
    lives in the policy (``seat_independence``), not here.
    """
    author = author or {}
    reviewer = reviewer or {}
    # The overlap check runs first and always: it is the one refusal that needs
    # no marker to be present, because the marker that is present proves the
    # review came from the author.
    for kind in ("seat", "session", "run"):
        shared = (author.get(kind) or frozenset()) & (reviewer.get(kind) or frozenset())
        if shared:
            return (
                "the review comes from the authoring %s (%s); a different "
                "reviewer seat has to review it" % (kind, ", ".join(sorted(shared)))
            )
    if not require_markers:
        return None
    if not (author.get("seat") or author.get("session")):
        return (
            "the PR names no authoring seat or session (add a "
            "`<!-- dt-seat agent=... -->` marker or a `Paperclip-Agent-Id:` / "
            "`Session-Id:` trailer to the PR body or commits), so a review "
            "under the author's own login cannot be shown to come from a "
            "different seat"
        )
    if not reviewer:
        return (
            "the review names no reviewer seat (`<!-- dt-seat agent=... -->`), "
            "and every seat posts under the author's login, so it may be the "
            "authoring session's own attestation"
        )
    kind = "seat" if author.get("seat") else "session"
    if not reviewer.get(kind):
        return (
            "the author is named by %s (%s) but the review names no %s (%s), so "
            "the two cannot be told apart"
            % (kind, show_identity(author), kind, show_identity(reviewer))
        )
    return None


# ---------------------------------------------------------------------------
# Rule 1: a thread the PR's own author resolved is not cleared
# ---------------------------------------------------------------------------


def _norm_login(login):
    return str(login or "").strip().lower()


def thread_resolved_by_author(thread, author_login, author_identity=None):
    """True when a resolved thread was resolved by the PR's own author.

    ``thread``: ``{is_resolved, resolved_by, comments:[{author, body}]}``.
    ``author_login``: the PR author's GitHub login. ``author_identity``:
    the author's seat / session / run, as read by :func:`author_identity`.

    Every seat posts under the same login, so a matching login is not
    evidence that the author resolved the thread. The thread's own note is
    read for a seat marker: a note naming a different seat means another
    seat spoke on the thread, so the resolution is not the author's. When
    nothing is known, the answer is the conservative one (the author
    resolved it) and the thread does not count as cleared.
    """
    thread = thread or {}
    resolved = thread.get("is_resolved")
    if resolved is None:
        resolved = thread.get("isResolved")
    if not resolved:
        return False
    resolver = _norm_login(thread.get("resolved_by") or thread.get("resolved_by_login"))
    author = _norm_login(author_login)
    if not resolver or not author:
        # The resolver or the author is unknown, so the resolution cannot be
        # attributed to the author. A thread stays as it was: not evidence
        # about who spoke on it.
        return False
    if resolver != author:
        # A different login resolved the thread: not the author.
        return False
    comments = [c for c in (thread.get("comments") or []) if isinstance(c, dict)]
    note = ""
    if comments:
        note = str(comments[-1].get("body") or comments[-1].get("note") or "")
    resolver_identity = identity_from_text(note)
    author_identity = author_identity or {}
    for kind in ("seat", "session", "run"):
        author_values = author_identity.get(kind) or frozenset()
        resolver_values = resolver_identity.get(kind) or frozenset()
        if author_values and resolver_values and not (author_values & resolver_values):
            # The note names a different seat: the author did not speak here.
            return False
    return True


# ---------------------------------------------------------------------------
# Rule 2: a review posted inside the push window is not a review of that push
# ---------------------------------------------------------------------------


def parse_ts(value):
    """Epoch seconds for an ISO-8601 timestamp, or ``None``."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        from datetime import datetime

        parsed = datetime.fromisoformat(text)
    except (ImportError, ValueError):
        return None
    try:
        if parsed.tzinfo is None:
            return parsed.timestamp()
        return parsed.timestamp()
    except (OverflowError, OSError, ValueError):
        return None


def review_too_close_to_push(submitted_at, push_at, window=PUSH_WINDOW_SECONDS):
    """True when a review was posted within ``window`` of the push.

    ``submitted_at`` is when the review was posted, ``push_at`` when the
    commit it covers was pushed. Either direction counts: a review written
    seconds before the push was written against an earlier tree.
    """
    submitted = parse_ts(submitted_at)
    pushed = parse_ts(push_at)
    if submitted is None or pushed is None:
        return False
    return abs(submitted - pushed) <= window


# ---------------------------------------------------------------------------
# Rule 3: a review copied from another PR is not a review
# ---------------------------------------------------------------------------

_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_URL_RE = re.compile(r"https?://\S+")
_AT_SHA_RE = re.compile(r"@[0-9a-f]{7,40}")
_SHA_RE = re.compile(r"\b[0-9a-f]{7,40}\b")
_DIGITS_RE = re.compile(r"\d+")
_PUNCT_RE = re.compile(r"[^a-z0-9\s]+")


def normalise_review_text(body):
    """Review text with the markers, the SHAs and the noise removed."""
    text = _HTML_COMMENT_RE.sub(" ", str(body or ""))
    text = _URL_RE.sub(" ", text)
    text = _AT_SHA_RE.sub(" ", text)
    text = _SHA_RE.sub(" ", text)
    text = text.lower()
    text = _DIGITS_RE.sub(" ", text)
    text = _PUNCT_RE.sub(" ", text)
    return " ".join(text.split())


def review_similarity(left, right):
    """Similarity of two normalised review texts, 0.0 to 1.0."""
    left = str(left or "")
    right = str(right or "")
    if not left or not right:
        return 0.0
    return difflib.SequenceMatcher(None, left, right).ratio()


def duplicate_reviews(
    normalised,
    pr_number,
    entries,
    threshold=SIMILARITY_THRESHOLD,
    window=CORPUS_WINDOW_SECONDS,
    now=None,
):
    """Corpus entries that carry (near-)the same text on another PR."""
    matches = []
    now = time.time() if now is None else now
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        other_pr = entry.get("pr")
        try:
            other_pr = int(other_pr)
        except (TypeError, ValueError):
            continue
        if pr_number is not None and other_pr == int(pr_number):
            continue
        at = entry.get("at")
        try:
            at = float(at)
        except (TypeError, ValueError):
            at = None
        if window and at is not None and (now - at) > window:
            continue
        other = entry.get("norm") or ""
        if not other:
            continue
        ratio = review_similarity(normalised, other)
        if ratio >= threshold:
            matches.append({"pr": other_pr, "at": at, "ratio": round(ratio, 4)})
    return matches


# ---------------------------------------------------------------------------
# The rolling corpus of recent review texts
# ---------------------------------------------------------------------------


def corpus_path(path=None):
    """Where the rolling corpus lives."""
    if path:
        return path
    override = os.environ.get(CORPUS_PATH_ENV)
    if override:
        return override
    return DEFAULT_CORPUS_PATH


def load_corpus(path=None, window=CORPUS_WINDOW_SECONDS, now=None):
    """Corpus entries inside the window. A missing or broken file is empty."""
    now = time.time() if now is None else now
    try:
        with open(corpus_path(path), "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    entries = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        at = parse_ts(entry.get("at"))
        if at is None:
            continue
        if window and (now - at) > window:
            continue
        entry = dict(entry)
        entry["at"] = at
        entries.append(entry)
    return entries


def save_corpus(entries, path=None):
    """Write the corpus atomically. Returns False when it could not be written."""
    target = corpus_path(path)
    folder = os.path.dirname(target)
    if folder and not os.path.isdir(folder):
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError:
            return False
    temporary = "%s.tmp" % target
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(entries, handle)
        os.replace(temporary, target)
    except OSError:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        return False
    return True


def corpus_entries(pr_number, texts, login=None, now=None):
    """Corpus entries for one PR's review texts, without writing them.

    ``texts``: iterable of ``(at, body)``; ``at`` is an ISO-8601 timestamp
    or epoch seconds. The corpus keeps the normalised text, so a later
    comparison is a similarity check and not a re-read of the review.
    """
    now = time.time() if now is None else now
    out: list[dict[str, Any]] = []
    for at, body in texts or []:
        normalised = normalise_review_text(body)
        if not normalised:
            continue
        stamp = parse_ts(at)
        out.append(
            {
                "pr": int(pr_number or 0),
                "at": float(stamp if stamp is not None else now),
                "norm": normalised,
                "login": login or "",
            }
        )
    return out


def record_reviews(pr_number, texts, path=None, window=CORPUS_WINDOW_SECONDS, now=None, login=None):
    """Add review texts of one PR to the corpus and return the corpus.

    ``texts``: iterable of ``(at, body)``. The corpus keeps the normalised
    text, so a later comparison is a similarity check and not a re-read of
    the review.
    """
    now = time.time() if now is None else now
    entries = load_corpus(path, window, now=now)
    known = set()
    for entry in entries:
        known.add((entry.get("pr"), entry.get("norm")))
    for entry in corpus_entries(pr_number, texts, login=login, now=now):
        key = (entry.get("pr"), entry.get("norm"))
        if key in known:
            continue
        known.add(key)
        entries.append(entry)
    save_corpus(entries, path)
    return entries
