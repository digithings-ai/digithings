#!/usr/bin/env python3
"""pr-template: local-ci gate for the standard PR description template
(DIG-3842 scope update, Chris 15 Oct 2026; DCO gate removed the same day).

Pure ``check_template(body)`` over the PR body text, mirroring
``.github/PULL_REQUEST_TEMPLATE.md``. Returns (ok, failures[]) where each
failure names the missing piece. Stdlib only:
``/usr/bin/python3 -m unittest test_pr_template -v``.

Checked sections:
- Linked issue: ``Fixes|Closes|Resolves #<number>`` (a bare ``Fixes #``
  with no number fails), or Paperclip linkage ``Fixes DIG-<number>`` —
  every PR must trace to a backlog issue on the Project board (Paperclip),
  and a Paperclip-tracked leaf legitimately has no GitHub issue number
  (DIG-3845 scope fix: without this the gate false-refuses such PRs).
- Component: at least one checked box.
- Change Type: at least one checked box.
- Summary: non-placeholder prose (HTML comments stripped, >= 20 chars).
- Testing Evidence: fenced block with content beyond the placeholder.
- Human Gate: ``Is human review required?`` answered Yes or No, and not
  answered No while a Human Gate box is checked.

Only the Human Gate findings block a merge. Every other finding is paperwork:
it is reported as a warning and the gate stays green (dev-flow plan P1-2,
29 Oct 2026). Template paperwork was 44% of local-ci reds (150 of 342), and a
red row for a missing summary sentence throws away a CI run without making the
change any safer. The Human Gate is the one section a merge decision depends
on, so it stays blocking: ``split_findings`` draws that line.
"""

from __future__ import annotations

import re

_LINK_RE = re.compile(r"(?i)\b(?:fixes|closes|resolves)\s+#\d+")
_DIG_LINK_RE = re.compile(r"(?i)\b(?:fixes|closes|resolves)\s+DIG-\d+")
_BARE_LINK_RE = re.compile(r"(?i)\b(?:fixes|closes|resolves)\s+#\s*(?:\D|$)")
_CHECKED_RE = re.compile(r"^\s*-\s*\[[xX]\]", re.M)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
# One answer, alone on the line: the template's untouched "Yes / No" is not
# an answer (it used to read as "Yes", so the bare template passed this gate).
_HUMAN_GATE_RE = re.compile(
    r"(?im)^.*is human review required\?\W*(yes|no)\b(?![^\n]*\b(?:yes|no)\b)")
_SUMMARY_MIN = 20
# Finding prefixes that still fail the gate. Everything else is a warning.
BLOCKING_PREFIXES = ("human-gate",)


def _section(body, heading):
    """Text under ``## <heading>`` up to the next ``## `` or EOF."""
    m = re.search(r"(?im)^##\s*%s\s*$" % re.escape(heading), body)
    if not m:
        return None
    rest = body[m.end():]
    n = re.search(r"(?im)^##\s+", rest)
    return rest[:n.start()] if n else rest


def _stripped(text):
    return _COMMENT_RE.sub("", text or "").strip()


def check_template(body):
    """Evaluate a PR body against the standard template.

    Returns (ok, failures). ``failures`` is empty when ok. A missing section
    and an unfilled section both fail; the message says which.
    """
    body = body or ""
    failures = []
    # The template's own comment shows "Fixes #123" as an example; read the
    # body without comments so the example cannot count as a link.
    visible = _stripped(body)

    if _LINK_RE.search(visible) or _DIG_LINK_RE.search(visible):
        pass
    elif _BARE_LINK_RE.search(visible):
        failures.append("linked-issue: 'Fixes #' names no issue number")
    else:
        failures.append("linked-issue: no 'Fixes|Closes|Resolves #<number>' line")

    comp = _section(body, "Component")
    if comp is None or not _CHECKED_RE.search(comp):
        failures.append("component: no checked box")

    ctype = _section(body, "Change Type")
    if ctype is None or not _CHECKED_RE.search(ctype):
        failures.append("change-type: no checked box")

    summary = _section(body, "Summary")
    prose = _stripped(summary) if summary is not None else ""
    prose = re.sub(r"(?m)^---\s*$", "", prose).strip()
    if len(prose) < _SUMMARY_MIN:
        failures.append("summary: no prose (need ~2-4 sentences)")

    testing = _section(body, "Testing Evidence")
    if testing is None:
        failures.append("testing-evidence: section missing")
    else:
        fenced = re.findall(r"```(.*?)```", testing, re.S)
        evidence = " ".join(_stripped(b) for b in fenced).strip()
        if not evidence:
            failures.append("testing-evidence: fenced block is empty")

    gate = _section(body, "Human Gate")
    answer = _HUMAN_GATE_RE.search(_stripped(gate)) if gate is not None else None
    if answer is None:
        failures.append("human-gate: 'Is human review required?' unanswered (Yes/No)")
    elif answer.group(1).lower() == "no" and _CHECKED_RE.search(_stripped(gate)):
        # #6603 and #6601 shipped with a Human Gate box that nothing enforced.
        # A checked box answered "No" is a contradiction, not paperwork.
        failures.append("human-gate: a Human Gate box is checked but the answer is No")

    return (not failures, failures)


def split_findings(failures):
    """Split ``check_template`` findings into (blocking, warnings).

    Blocking findings start with one of BLOCKING_PREFIXES (the Human Gate);
    the rest are warnings that local-ci logs and counts but does not fail on.
    """
    blocking = [f for f in failures or [] if f.startswith(BLOCKING_PREFIXES)]
    warnings = [f for f in failures or [] if not f.startswith(BLOCKING_PREFIXES)]
    return blocking, warnings
