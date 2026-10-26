#!/usr/bin/env python3
"""review-applied: local-ci verdict for develop PRs (DIG-3842, Chris 15 Oct 2026).

A required local-ci status check named ``review-applied``, posted on PRs into
develop. It passes only when:

- (a) at least one review pass left comments on the PR. That can be Chris's
  in-session review comment (``AGENT_REVIEW_MARKER``) or a reviewer bot
  (Bugbot, Copilot, CodeRabbit, Claude ``/code-review``, ...). A comment that
  only *quotes* the marker in code, or *names* it in a sentence, is not a
  review pass (DIG-4990); and
- (b) every review thread is resolved, OR is followed by a fix commit (pushed
  after the comment) and a reply on that thread.

It fails with a message naming the unmet condition and the open threads.

Shape: pure ``evaluate()`` over injected data (unit-tested here) plus thin
``gh`` fetchers mirroring ``local_ci.py`` conventions. Stdlib only:
``/usr/bin/python3 -m unittest test_review_applied -v``.
"""

from __future__ import annotations

import os
import re
import sys

# The review-pass filter (DIG-4631) ships next to this file in the host
# checkout and one directory up in the digithings mirror, so both are put
# on the path before it is imported.
_HERE = os.path.dirname(os.path.abspath(__file__))
for _candidate in (os.path.dirname(_HERE), _HERE):
    if _candidate and _candidate not in sys.path:
        sys.path.insert(0, _candidate)

try:  # the rules module is optional: without it the review leg cannot judge
    import review_pass_filter
except ImportError:  # pragma: no cover - the module is missing from the install
    review_pass_filter = None

# Exact context name Chris's runbook adds to develop's required status checks
# alongside ``local-ci``. Never rename: protection matches this string.
APPLIED_CTX = "review-applied"

# In-session review marker: the comment body fragment an in-session review
# posts (same marker scripts/check_review_coverage.py looks for).
AGENT_REVIEW_MARKER = "<!-- in-session-review -->"

# A marker *shown* in a code block or an inline span, or *named* in a sentence,
# is not a marker that was posted. On 26 Oct 2026 nine CI-triage notes that
# described the marker therefore contained it, and any one of them would have
# turned this check green with no review having happened (DIG-4990, the same
# class as #6197). The reader below takes the code out first, then asks whether
# anything but HTML comments is left on the line the marker sits on: a posted
# marker is a line of its own, a quoted or described one is not.
_FENCE_OPEN_RE = re.compile(r"^(?P<fence>`{3,}|~{3,})(?P<info>.*)$")
_FENCE_CLOSE_RE = re.compile(r"^(?P<fence>`{3,}|~{3,})[ \t]*$")
_INLINE_CODE_RE = re.compile(r"(?<!`)(`+)(?!`)(?P<code>.+?)(?<!`)\1(?!`)", re.DOTALL)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def _strip_fenced_blocks(body):
    """The body with fenced code blocks (``` and ~~~) taken out.

    Removed lines become a bare newline, so line numbers and the line-anchored
    readers keep working on the text that is left. Mirrors the reader
    ``scripts/merge_queue.py`` uses, so the two gates agree on what is code.
    """
    kept = []
    fence = ""
    for line in body.splitlines(keepends=True):
        if fence:
            match = _FENCE_CLOSE_RE.match(line.strip())
            if (
                match
                and match.group("fence")[0] == fence[0]
                and len(match.group("fence")) >= len(fence)
            ):
                fence = ""
            kept.append("\n")
            continue
        match = _FENCE_OPEN_RE.match(line.strip())
        if match:
            fence = match.group("fence")
            kept.append("\n")
            continue
        kept.append(line)
    return "".join(kept)


def _strip_code_blocks(body):
    """The body with fenced blocks *and* inline code spans taken out."""
    return _INLINE_CODE_RE.sub(" ", _strip_fenced_blocks(str(body or "")))


def carries_agent_review_marker(body):
    """True when the comment *posts* the in-session marker.

    A marker inside a fence or an inline span is quoted, not posted, and a
    marker inside a sentence or a blockquote is described, not posted. Both are
    how a note *about* a review reads, and neither is a review (DIG-4990). A
    posted marker is on a line of its own; a provenance marker beside it on that
    same line is still that line's only content.
    """
    text = _strip_code_blocks(body)
    if AGENT_REVIEW_MARKER not in text:
        return False
    for line in text.splitlines():
        if AGENT_REVIEW_MARKER not in line:
            continue
        if not _HTML_COMMENT_RE.sub("", line).strip():
            return True
    return False

# Reviewer-bot logins, bare and [bot]-suffixed (REST often returns the suffix,
# `gh pr view --json` the bare login). github-advanced-security posts CodeQL
# findings as review threads and counts as a review pass.
REVIEW_BOTS = frozenset(
    {
        "coderabbitai",
        "coderabbitai[bot]",
        "cursor[bot]",
        "cursor",
        "copilot",
        "copilot[bot]",
        "github-copilot[bot]",
        "claude",
        "claude[bot]",
        "github-advanced-security",
        "github-advanced-security[bot]",
        "bugbot",
    }
)

# Bot check-run names that count as a completed review pass when concluded
# ``success``. A ``neutral``/``skipped`` conclusion is a usage-limit skip,
# not a review (same rule check_review_coverage.py applies to Bugbot).
REVIEW_BOT_CHECKS = frozenset(
    {
        "cursor bugbot",
        "coderabbit",
        "claude /code-review",
        "claude/code-review",
        "copilot",
    }
)


def _norm_login(login):
    return str(login or "").strip().lower()


def is_reviewer_bot(login):
    """True when the login is a recognised reviewer bot (either suffix form)."""
    return _norm_login(login) in REVIEW_BOTS


def bot_check_passed(check_runs):
    """True when any review-bot check run concluded ``success``.

    ``check_runs``: iterable of {name, conclusion}. Conclusion compare is
    exact: ``neutral`` (usage-limit skip) and ``skipped`` do NOT count.
    """
    for c in check_runs or []:
        if not isinstance(c, dict):
            continue
        if str(c.get("name") or "").strip().lower() in REVIEW_BOT_CHECKS:
            if c.get("conclusion") == "success":
                return True
    return False


def has_review_pass(review_passes, check_runs=()):
    """Condition (a): at least one review pass left comments.

    ``review_passes``: iterable of {kind, author, has_comments} where kind is
    one of ``in-session`` | ``bot`` | ``human``. A pass counts when it left
    comments AND its author is a recognised reviewer: the in-session marker
    (kind ``in-session``), a reviewer-bot login, or a human APPROVED review
    (kind ``human`` covers approvals; COMMENTED-only human reviews do not).
    A successful reviewer-bot check run also counts.
    """
    for p in review_passes or []:
        if not isinstance(p, dict) or not p.get("has_comments"):
            continue
        kind = str(p.get("kind") or "")
        if kind == "in-session":
            return True
        if kind == "bot" and is_reviewer_bot(p.get("author")):
            return True
        if kind == "human":
            return True
    return bot_check_passed(check_runs)


def _thread_first_at(thread):
    comments = thread.get("comments") or []
    times = [c.get("created_at") for c in comments if isinstance(c, dict) and c.get("created_at")]
    return min(times) if times else None


def _thread_has_reply(thread, reviewer_logins=()):
    """True when a non-reviewer replied on the thread after the first comment.

    ``reviewer_logins``: logins whose comments do NOT count as replies (the
    reviewing bot following up on its own thread). Empty means any second
    commenter counts.
    """
    comments = [c for c in (thread.get("comments") or []) if isinstance(c, dict)]
    if len(comments) < 2:
        return False
    first_author = _norm_login(comments[0].get("author"))
    strangers = {_norm_login(login) for login in (reviewer_logins or ())}
    strangers.add(first_author)
    return any(
        _norm_login(c.get("author")) not in strangers and c.get("created_at")
        for c in comments[1:]
    )


def _fix_after(thread_first_at, fix_commit_ats):
    """True when a fix commit was pushed after the thread's first comment."""
    if not thread_first_at:
        return False
    return any(
        ts and ts > thread_first_at for ts in (fix_commit_ats or [])
    )


def thread_cleared(thread, fix_commit_ats, reviewer_logins=()):
    """Condition (b) per thread: resolved, or fix-commit-after-comment AND a reply.

    A thread the PR's own author resolved does not count as cleared
    (DIG-4631). Every seat posts under the same GitHub login, so the
    resolution is checked against the author's seat, not against the login.
    """
    if review_pass_filter is None:
        # The rules cannot be applied, so a thread is not cleared.
        return False
    if thread.get("author_resolved"):
        return False
    if thread.get("is_resolved"):
        return True
    return _fix_after(_thread_first_at(thread), fix_commit_ats) and _thread_has_reply(
        thread, reviewer_logins
    )


def evaluate(review_passes, threads, fix_commit_ats=(), check_runs=(), reviewer_logins=(),
             verdict_blocks=(), verdict_error=None):
    """Verdict for one PR head.

    Returns (ok, message, open_thread_ids). ``message`` names the unmet
    condition and the open threads; it is what local-ci posts as the status
    description (truncated to 139 chars by the caller).

    ``verdict_blocks``: output of ``blocking_verdicts`` (change requests that
    nothing since has cleared). Any entry fails the check before the pass and
    thread conditions are read: #5863 passed with a recorded pass and 0 threads
    while its latest review said "Verdict: CHANGES".

    ``verdict_error``: set when the verdicts could not be read at all. An
    unreadable record is not a clearance, so the check fails closed with that
    reason - and it does not claim that changes were requested (DIG-4646).
    """
    threads = [t for t in (threads or []) if isinstance(t, dict)]
    if verdict_error:
        return (
            False,
            "review-applied: could not read the review verdicts: %s" % verdict_error,
            [str(t.get("id") or "?") for t in threads if not t.get("is_resolved")],
        )
    blocks = [b for b in (verdict_blocks or []) if b]
    if blocks:
        return (
            False,
            "review-applied: changes requested, not cleared: %s" % "; ".join(blocks[:3]),
            [str(t.get("id") or "?") for t in threads if not t.get("is_resolved")],
        )
    if not has_review_pass(review_passes, check_runs):
        return (
            False,
            "review-applied: no review pass left comments "
            "(need an in-session review comment or a reviewer-bot pass)",
            [str(t.get("id") or "?") for t in threads if not t.get("is_resolved")],
        )
    open_ids = [
        str(t.get("id") or "?")
        for t in threads
        if not thread_cleared(t, fix_commit_ats, reviewer_logins)
    ]
    if open_ids:
        return (
            False,
            "review-applied: %d unresolved thread(s) with no fix commit + reply: %s"
            % (len(open_ids), ", ".join(open_ids[:5])),
            open_ids,
        )
    n = len(threads)
    return (
        True,
        "review-applied: review pass recorded, all %d thread(s) resolved or answered" % n,
        [],
    )


# ---------------------------------------------------------------------------
# Each reviewer's latest verdict (after #5863)
#
# A reviewer's latest verdict blocks when it is CHANGES_REQUESTED, until the
# same reviewer posts a later APPROVED or COMMENTED review, or the review is
# dismissed (GitHub then reports it with state DISMISSED). Bots count like
# humans. Formal reviews and in-session review comments (the marker) are read
# in one time order; an in-session comment's verdict is its ``Review verdict:``
# line, read by the shared parser in ``scripts/review_pass_filter.py`` so this
# producer and the merge queue read the fleet's verdicts the same way
# (DIG-4646).

_REVIEW_STATES = frozenset({"APPROVED", "CHANGES_REQUESTED", "COMMENTED", "DISMISSED"})


def reviewer_key(login):
    """One key per reviewer: case-folded, ``[bot]`` suffix dropped."""
    key = _norm_login(login)
    return key[: -len("[bot]")] if key.endswith("[bot]") else key


def in_session_state(body):
    """CHANGES_REQUESTED / APPROVED / COMMENTED from an in-session review body.

    The verdict line is read by the shared parser in
    ``scripts/review_pass_filter.py``. The QA lane writes "Review verdict:
    changes requested - #5994 @ `abc`", so a parser anchored on the bare word
    "verdict" read every real verdict as no verdict at all (DIG-4646).
    """
    if review_pass_filter is None:
        # The parser is missing, so no verdict can be read. Fail closed: the
        # body is not a verdict.
        return "COMMENTED"
    return review_pass_filter.in_session_verdict_state(body)


# The opencode-power-pack code-review marker carries ``verdict=`` as a field
# (same marker scripts/merge_queue.py reads); only its fields are trusted.
_PP_MARKER_RE = re.compile(r"<!--\s*opencode-power-pack:code-review\b(?P<fields>[^>]*?)\s*-->")
_PP_FIELD_RE = re.compile(r"(?P<key>[A-Za-z_][A-Za-z0-9_.-]*)=(?P<value>\S+)")
_PP_BLOCKING = frozenset({"changes_requested", "changes_needed"})
_PP_APPROVING = frozenset({"approved", "approve"})


def marker_state(body):
    """CHANGES_REQUESTED / APPROVED from a power-pack marker's ``verdict=``,
    or None when the comment carries no readable marker verdict.

    A marker inside a fence or an inline span is a quoted example, not a posted
    verdict (DIG-4990), so the body is read with its code taken out.
    """
    for m in _PP_MARKER_RE.finditer(_strip_code_blocks(body)):
        fields = {f.group("key").lower(): f.group("value")
                  for f in _PP_FIELD_RE.finditer(m.group("fields"))}
        v = fields.get("verdict", "").strip().strip("'\";").lower().replace("-", "_")
        if v in _PP_BLOCKING:
            return "CHANGES_REQUESTED"
        if v in _PP_APPROVING:
            return "APPROVED"
    return None


def comment_state(body):
    """Verdict state of an issue comment, or None when it is not a review verdict."""
    state = marker_state(body)
    if state is not None:
        return state
    if carries_agent_review_marker(body):
        return in_session_state(body)
    return None


def _login_of(row):
    for k in ("user", "author"):
        v = row.get(k)
        if isinstance(v, dict) and v.get("login"):
            return v.get("login")
    return None


def verdict_identity(body, author=None):
    """The seat (else the session) a verdict names; ("", "") when it names neither.

    The shared rules in ``scripts/review_pass_filter.py`` read the identity, so
    this producer and the merge queue judge the same verdict the same way
    (DIG-4646).
    """
    if review_pass_filter is None:
        return ("", "")
    return review_pass_filter.verdict_identity(body, author)


def review_events(reviews, comments):
    """[(at, seq, reviewer, identity, state, where)] for every readable verdict, oldest first.

    ``reviews``: REST pull reviews ({user, state, submitted_at, body, id}).
    ``comments``: REST issue comments; only marker comments are verdicts.
    ``seq`` keeps GitHub's order for rows that carry no timestamp.
    ``identity``: the seat (else the session) the verdict names, ("", "") when
    it names neither - it decides what clears a change request.
    """
    events = []
    seq = 0
    for r in reviews or []:
        seq += 1
        if not isinstance(r, dict):
            continue
        state = str(r.get("state") or "").upper()
        body = str(r.get("body") or "")
        if state == "COMMENTED":
            state = comment_state(body) or state
        if state not in _REVIEW_STATES:
            continue  # PENDING: not submitted, not a verdict
        at = str(r.get("submitted_at") or r.get("submittedAt") or "")
        events.append((at, seq, reviewer_key(_login_of(r)),
                       verdict_identity(body, r.get("user") or r.get("author")),
                       state, "review %s" % (r.get("id") or seq)))
    for c in comments or []:
        seq += 1
        if not isinstance(c, dict):
            continue
        body = str(c.get("body") or "")
        state = comment_state(body)
        if state is None:
            continue
        at = str(c.get("created_at") or c.get("createdAt") or "")
        events.append((at, seq, reviewer_key(_login_of(c)),
                       verdict_identity(body, c.get("user") or c.get("author")),
                       state, "in-session comment %s" % (c.get("id") or seq)))
    events.sort(key=lambda e: (e[0], e[1]))
    return events


def blocking_verdicts(reviews, comments):
    """One short message per change request that nothing since has cleared.

    The rules are the shared ones in ``scripts/review_pass_filter.py``: a change
    request is cleared by the same identity (the same seat or session), by a
    dismissal of that review, or - for a request that names no seat - by a later
    verdict that names a seat. The merge queue applies the same rules, so the
    producer and the queue agree on what is still blocking (DIG-4646).
    """
    events = review_events(reviews, comments)
    if review_pass_filter is None:
        # Without the shared rules, fall back to the reviewer's latest verdict.
        latest = {}
        for at, _seq, reviewer, _identity, state, where in events:
            latest[reviewer] = (state, where, at)
        return [
            "%s (%s%s)" % (reviewer or "?", where, " at " + at if at else "")
            for reviewer, (state, where, at) in sorted(latest.items())
            if state == "CHANGES_REQUESTED"
        ]
    return [
        "%s (%s%s)" % (login or "?", where, " at " + at if at else "")
        for login, _identity, where, at
        in review_pass_filter.outstanding_change_requests(events)
    ]


def fetch_verdict_inputs(pr_number, repo, run_rest):
    """(reviews, comments) for ``blocking_verdicts``, or None when either read
    fails: an unreadable record is not a clearance (fail closed)."""
    reviews = run_rest("repos/%s/pulls/%d/reviews?per_page=100" % (repo, pr_number))
    comments = run_rest("repos/%s/issues/%d/comments?per_page=100" % (repo, pr_number))
    if not isinstance(reviews, list) or not isinstance(comments, list):
        return None
    return reviews, comments


# ---------------------------------------------------------------------------
# What a review pass is not (DIG-4631)
#
# A review does not count when it was posted inside the push window of the
# commit it covers, or when its text is a copy of a review on another PR.
# The rolling corpus of recent review texts is what makes the second
# checkable; the push window needs the commit's push time.

_PR_CONTEXT = {}


def _pr_context(pr_number, repo, run_gh, run_rest=None):
    """Author login, author seat and the push time of every commit.

    Read once per process: the threads and the passes need the same facts.
    """
    key = (repo, pr_number)
    if key in _PR_CONTEXT:
        return _PR_CONTEXT[key]
    context = {"login": None, "body": "", "identity": {}, "push_times": {}}
    data = None
    if run_rest is not None:
        try:
            data = run_rest("repos/%s/pulls/%d" % (repo, pr_number))
        except Exception:
            data = None
    if not isinstance(data, dict) and run_gh is not None:
        try:
            data = run_gh(["api", "repos/%s/pulls/%d" % (repo, pr_number)])
        except Exception:
            data = None
    if isinstance(data, dict):
        context["login"] = (
            (data.get("user") or {}).get("login")
            or (data.get("author") or {}).get("login")
        )
        context["body"] = data.get("body") or ""
        commits = data.get("commits")
        if not isinstance(commits, list):
            # The pull endpoint returns a count in `commits`; the list lives on
            # the /commits sub-resource.
            commits = []
            try:
                listed = run_gh(
                    ["api", "repos/%s/pulls/%d/commits" % (repo, pr_number)]
                )
            except Exception:
                listed = None
            if isinstance(listed, list):
                commits = listed
        for commit in commits:
            if not isinstance(commit, dict):
                continue
            sha = commit.get("sha")
            inner = commit.get("commit")
            inner = inner if isinstance(inner, dict) else {}
            at = (inner.get("committer") or {}).get("date") or commit.get("committedDate")
            if sha and at:
                context["push_times"][sha] = at
        if review_pass_filter is not None:
            # The pull payload carries `commits` as a count, not as the list of
            # commits, so the list that was just read is handed over instead
            # of the raw payload: reading the count crashed the producer on
            # every PR (DIG-4646).
            context["identity"] = review_pass_filter.author_identity(
                dict(data, commits=commits)
            )
    _PR_CONTEXT[key] = context
    return context


def _head_push_at(context):
    """Push time of the newest commit of the PR."""
    times = [t for t in (context.get("push_times") or {}).values() if t]
    if not times:
        return None
    return max(times, key=lambda t: review_pass_filter.parse_ts(t) or 0)


def _filter_passes(passes, pr_number, context):
    """Split the review passes into the ones that count and the ones that do not."""
    if review_pass_filter is None:
        # The rules cannot be applied, so no pass is accepted.
        return [], list(passes)
    kept, dropped = [], []
    corpus = review_pass_filter.load_corpus()
    for candidate in passes:
        commit_id = candidate.get("commit_id")
        if commit_id:
            push_at = (context.get("push_times") or {}).get(commit_id)
        else:
            # A comment carries no commit: it speaks about the head.
            push_at = _head_push_at(context)
        if review_pass_filter.review_too_close_to_push(candidate.get("at"), push_at):
            dropped.append(dict(candidate, reason="posted inside the push window"))
            continue
        normalised = review_pass_filter.normalise_review_text(candidate.get("body"))
        copies = review_pass_filter.duplicate_reviews(normalised, pr_number, corpus)
        if copies:
            dropped.append(dict(candidate, reason="copied from another PR"))
            continue
        kept.append(candidate)
    return kept, dropped


def _record_corpus(pr_number, passes, context):
    """Keep the review texts of this PR so a later copy can be recognised."""
    texts = [(p.get("at"), p.get("body") or "") for p in passes if p.get("body")]
    if texts:
        review_pass_filter.record_reviews(
            pr_number, texts, login=context.get("login")
        )


# ---------------------------------------------------------------------------
# Fetchers (thin gh wrappers; kept import-free of local_ci so tests stay pure)


def fetch_threads_graphql(pr_number, repo, run_gh):
    """Review threads via GraphQL: [{id, is_resolved, comments:[{author, created_at}]}].

    ``run_gh``: callable(argv)->parsed-json-or-None, injected for tests.
    """
    q = (
        "query($o:String!,$r:String!,$n:Int!){repository(owner:$o,name:$r){"
        "pullRequest(number:$n){reviewThreads(first:100){nodes{id isResolved "
        "resolvedBy{login} "
        "comments(first:20){nodes{createdAt author{login} body "
        "commit{oid committedDate}}}}}}}}"
    )
    o, _, r = repo.partition("/")
    context = _pr_context(pr_number, repo, run_gh)
    data = run_gh(
        ["api", "graphql", "-f", "query=" + q, "-f", "o=" + o, "-f", "r=" + r,
         "-F", "n=%d" % pr_number]
    )
    try:
        nodes = data["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
    except (TypeError, KeyError, IndexError):
        return None
    out = []
    for t in nodes or []:
        comments = []
        try:
            raw = t["comments"]["nodes"] or []
        except (TypeError, KeyError):
            raw = []
        for c in raw:
            try:
                author = (c.get("author") or {}).get("login")
            except AttributeError:
                author = None
            comments.append({"author": author, "created_at": c.get("createdAt"),
                             "body": c.get("body") or ""})
        thread = {
            "id": t.get("id"),
            "is_resolved": bool(t.get("isResolved")),
            "resolved_by": (t.get("resolvedBy") or {}).get("login"),
            "comments": comments,
        }
        thread["author_resolved"] = review_pass_filter.thread_resolved_by_author(
            thread, context.get("login"), context.get("identity") or {}
        )
        out.append(thread)
    return out


def fetch_review_passes(pr_number, repo, run_gh, run_rest):
    """Review passes from REST reviews + issue comments (in-session marker).

    Returns [{kind, author, has_comments}]. ``run_gh`` parses GraphQL-ish argv,
    ``run_rest`` fetches a REST path and returns parsed JSON (both injected).

    A pass that was posted inside the push window of the commit it covers,
    or whose text is a copy of a review on another PR, is not a review pass
    (DIG-4631) and is dropped here.
    """
    context = _pr_context(pr_number, repo, run_gh, run_rest)
    candidates = []
    reviews = run_rest("repos/%s/pulls/%d/reviews" % (repo, pr_number)) or []
    for r in reviews:
        if not isinstance(r, dict):
            continue
        body = r.get("body") or ""
        state = r.get("state")
        try:
            login = (r.get("user") or {}).get("login")
        except AttributeError:
            login = None
        if state == "APPROVED":
            candidates.append({"kind": "human", "author": login,
                               "has_comments": True, "at": r.get("submitted_at"),
                               "commit_id": r.get("commit_id"), "body": body})
        elif body.strip() and is_reviewer_bot(login):
            candidates.append({"kind": "bot", "author": login,
                               "has_comments": True, "at": r.get("submitted_at"),
                               "commit_id": r.get("commit_id"), "body": body})
    comments = run_rest("repos/%s/issues/%d/comments" % (repo, pr_number)) or []
    for c in comments:
        if not isinstance(c, dict):
            continue
        if carries_agent_review_marker(c.get("body") or ""):
            try:
                login = (c.get("user") or {}).get("login")
            except AttributeError:
                login = None
            candidates.append({"kind": "in-session", "author": login,
                               "has_comments": True, "at": c.get("created_at"),
                               "commit_id": None, "body": c.get("body") or ""})
    kept, _dropped = _filter_passes(candidates, pr_number, context)
    _record_corpus(pr_number, kept, context)
    return kept


def reviewer_logins_for(review_passes):
    """Logins whose thread comments are the reviewer's own (not replies)."""
    return {
        _norm_login(p.get("author"))
        for p in (review_passes or [])
        if isinstance(p, dict) and p.get("kind") == "bot" and p.get("author")
    }
