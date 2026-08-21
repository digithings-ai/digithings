---
description: Review a PR in-session when Cursor Bugbot is unavailable — post findings as a comment and clear the review-coverage gate honestly.
---

Invoke as: `/review <pr-number>`

If no PR number is given, ask for it before proceeding.

## When to use this

When a machine review is wanted and **no review bot has left an artifact yet**.
Check first:

```bash
gh pr view <N> --json statusCheckRollup,reviews,comments \
  -q '{bugbot:(.statusCheckRollup[]?|select((.name//"")=="Cursor Bugbot")|.conclusion), coderabbit:(.statusCheckRollup[]?|select((.name//"")=="CodeRabbit")|.conclusion)}'
```

- Bugbot `SUCCESS`, CodeRabbit `SUCCESS`, or a submitted CodeRabbit/Claude review → a real review already exists. Stop; address those findings instead of starting a second loop.
- Bugbot `NEUTRAL`, CodeRabbit rate-limit / skip / failure, or nothing posted → proceed.

Prefer a review bot when it works. `/review` is the clean-context fallback so the
gate still sees an artifact when the bots did not finish.

## Why an in-session review counts

Every line in this repository is written by a coding agent, so "an agent reviewed
it" is not weaker in kind than Bugbot, which is also an agent. What matters is that
the reviewer **did not write the code** and that its findings are **on the record**.

So this review must be run by a subagent with **fresh context**, given the diff and
told to find problems — not by the session that wrote the change re-reading its own
work. A self-review by the author is worth close to nothing and must not be
labelled as one.

## How to run it

1. **Get the diff.** `gh pr diff <N>`. Note the base: task PRs target `develop`.

2. **Fan out over independent lenses**, each in its own subagent with no knowledge
   of how the code came to be written. These lenses have no subagent file to pin a
   model — dispatch each explicitly with `model: opus` (per CLAUDE.md's Model &
   subagent policy: review/security/architecture judgment is the opus tier).
   Leaving `model` unset means each lens silently inherits whatever the orchestrating
   session is running, which is the exact risk this repo already documents and
   guards against for fixed subagents — it just isn't fixed here because this
   command dispatches ad hoc rather than through a pinned `agents/sources/subagents/`
   file. Use the lenses that fit the diff:
   - **correctness** — wrong output, unhandled state, off-by-one, async ordering
   - **claim accuracy** — every factual assertion about this repo checked against
     the source. This lens has caught more real defects here than any other: a
     "Low Risk" 3-line copy PR shipped two false public claims to production
   - **regression** — removed or renamed exports still imported somewhere; a CSS
     selector other pages depend on
   - **security** — auth, keys, scopes, injection, anything under `digikey/`
   - **CI/deploy** — will it build; does a named workflow actually do what a
     comment says

3. **Verify before reporting.** Every finding needs a command that was actually
   run and its output. Put each surviving finding through a refuter told to
   *disprove* it, defaulting to refuted when unsure. Drop what does not survive —
   a plausible-but-wrong finding costs more than silence.

4. **Post the findings**, even when there are none. The comment MUST open with this
   exact marker or the gate will refuse the label:

   ```
   <!-- in-session-review -->
   ```

   Then: what was checked, the confirmed findings most-severe-first with
   `file:line` and the evidence, and what was checked and found clean. If nothing
   survived verification, say so plainly and do not pad.

   ```bash
   gh pr comment <N> --body-file /path/to/findings.md
   ```

5. **Label it** so `ci-review-coverage.yml` can see it:

   ```bash
   gh pr edit <N> --add-label "reviewed:agent"
   ```

   The label alone does **not** clear the gate — `scripts/check_review_coverage.py`
   looks for a comment carrying the marker and refuses the label without one. That
   is deliberate: it makes the claim cost a real review instead of a click.

6. **Fix what you found**, or say why not. A review that reports and walks away has
   done half a job. If a finding is real and cheap, fix it on the same branch before
   merge — that is the whole reason review belongs at the task PR rather than at the
   promotion. After the fixes land, the PR is green. If the follow-up was large,
   run another review loop rather than treating the original pass as covering it.

## What not to do

- Do not label `reviewed:agent` without the findings comment.
- Do not use `risk:low` to mean "an agent looked at it" — that label means the
  change did not warrant review at all, and conflating them destroys the signal.
- Do not use `reviewed:owner` on the maintainer's behalf. That label asserts *they*
  read it, and only they can claim it.
