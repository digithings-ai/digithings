#!/usr/bin/env python3
"""review-applied: local-ci verdict for develop PRs (DIG-3842, Chris 15 Oct 2026).

A required local-ci status check named ``review-applied``, posted on PRs into
develop. It passes only when:

- (a) at least one review pass left comments on the PR. That can be Chris's
  in-session review comment (``AGENT_REVIEW_MARKER``) or a reviewer bot
  (Bugbot, Copilot, CodeRabbit, Claude ``/code-review``, ...); and
- (b) every review thread is resolved, OR is followed by a fix commit (pushed
  after the comment) and a reply on that thread.

It fails with a message naming the unmet condition and the open threads.

Shape: pure ``evaluate()`` over injected data (unit-tested here) plus thin
``gh`` fetchers mirroring ``local_ci.py`` conventions. Stdlib only:
``/usr/bin/python3 -m unittest test_review_applied -v``.
"""

from __future__ import annotations

# Exact context name Chris's runbook adds to develop's required status checks
# alongside ``local-ci``. Never rename: protection matches this string.
APPLIED_CTX = "review-applied"

# In-session review marker: the comment body fragment an in-session review
# posts (same marker scripts/check_review_coverage.py looks for).
AGENT_REVIEW_MARKER = "<!-- in-session-review -->"

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
    """Condition (b) per thread: resolved, or fix-commit-after-comment AND a reply."""
    if thread.get("is_resolved"):
        return True
    return _fix_after(_thread_first_at(thread), fix_commit_ats) and _thread_has_reply(
        thread, reviewer_logins
    )


def evaluate(review_passes, threads, fix_commit_ats=(), check_runs=(), reviewer_logins=()):
    """Verdict for one PR head.

    Returns (ok, message, open_thread_ids). ``message`` names the unmet
    condition and the open threads; it is what local-ci posts as the status
    description (truncated to 139 chars by the caller).
    """
    threads = [t for t in (threads or []) if isinstance(t, dict)]
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
# Fetchers (thin gh wrappers; kept import-free of local_ci so tests stay pure)


def fetch_threads_graphql(pr_number, repo, run_gh):
    """Review threads via GraphQL: [{id, is_resolved, comments:[{author, created_at}]}].

    ``run_gh``: callable(argv)->parsed-json-or-None, injected for tests.
    """
    q = (
        "query($o:String!,$r:String!,$n:Int!){repository(owner:$o,name:$r){"
        "pullRequest(number:$n){reviewThreads(first:100){nodes{id isResolved "
        "comments(first:20){nodes{createdAt author{login} body "
        "commit{oid committedDate}}}}}}}}"
    )
    o, _, r = repo.partition("/")
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
            comments.append({"author": author, "created_at": c.get("createdAt")})
        out.append(
            {"id": t.get("id"), "is_resolved": bool(t.get("isResolved")),
             "comments": comments}
        )
    return out


def fetch_review_passes(pr_number, repo, run_gh, run_rest):
    """Review passes from REST reviews + issue comments (in-session marker).

    Returns [{kind, author, has_comments}]. ``run_gh`` parses GraphQL-ish argv,
    ``run_rest`` fetches a REST path and returns parsed JSON (both injected).
    """
    passes = []
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
            passes.append({"kind": "human", "author": login, "has_comments": True})
        elif body.strip() and is_reviewer_bot(login):
            passes.append({"kind": "bot", "author": login, "has_comments": True})
    comments = run_rest("repos/%s/issues/%d/comments" % (repo, pr_number)) or []
    for c in comments:
        if not isinstance(c, dict):
            continue
        if AGENT_REVIEW_MARKER in (c.get("body") or ""):
            try:
                login = (c.get("user") or {}).get("login")
            except AttributeError:
                login = None
            passes.append({"kind": "in-session", "author": login, "has_comments": True})
            break
    return passes


def reviewer_logins_for(review_passes):
    """Logins whose thread comments are the reviewer's own (not replies)."""
    return {
        _norm_login(p.get("author"))
        for p in (review_passes or [])
        if isinstance(p, dict) and p.get("kind") == "bot" and p.get("author")
    }
