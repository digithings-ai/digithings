# Trigger note — when to file the GitHub request

**Status: standing instruction. Prepared by Counsel 2026-10-06.**
File alongside [DIG-1484](/DIG/issues/DIG-1484). Read it before anything in this folder is sent.

**Purpose.** So that the decision to file with GitHub does not have to be re-made from scratch later,
at the exact moment when everyone involved is least willing to spend attention on it. This note fixes
the trigger in advance. If the condition is met, the request goes out without a fresh discussion —
subject only to the preconditions below.

---

## ⚠ This note was rewritten. The first version was built on a false premise.

The first version made the trigger *"both fork owners have had fourteen days to respond."* That is
gone, for three reasons:

1. **The corrected letters ask for nothing.** Both are courtesy notices. They state plainly that the
   fork owners hold no copy of the data and that there is nothing in their history to remove. The
   letters carry **no deadline**, so there is no window to run, and nothing to escalate on.
2. **Waiting on a stranger cannot move the exposure.** The file lives in our repository. Their
   response changes nothing about whether GitHub's servers still hold the object.
3. **The real dependency was never the fork owners.** It is the rewrite in [DIG-1496](/DIG/issues/DIG-1496).

Any earlier plan that treated "the fork owners did not reply in fourteen days" as grounds to file
against them is withdrawn. It would have been both wrong and unfair.

---

## The standing instruction

> The GitHub private-information removal request is filed when **the history rewrite in
> [DIG-1496](/DIG/issues/DIG-1496) has landed on `digithings-ai/digithings`** and the file is **still
> publicly retrievable** at the pinned commit `86cb1ec5d62b2422cf2c312b6d63722c86fb2000`.
>
> The trigger is a technical state, not a date. It fires when our own refs are clean and the object is
> still live. Record the rewrite completion date on DIG-1484 so the trigger has an unambiguous anchor.

There is no countdown and no waiting period. **A response from a fork owner is neither a precondition
nor a trigger**, in either direction. Their silence changes nothing about what GitHub is holding.

---

## Preconditions — all must hold before filing

1. **[DIG-1496](/DIG/issues/DIG-1496) is `done`.** This is the trigger *and* the precondition, because
   it is both. GitHub's guidance is explicit that garbage collection follows: *"If you have
   successfully cleaned up all references other than PRs, and no forks have references to the sensitive
   data, Support will then: Dereference or delete any affected PRs on GitHub. Run a garbage collection
   on the server to expunge the sensitive data from storage. Remove cached views."* Filing before the
   rewrite would ask GitHub to act on a repository we have not cleaned ourselves, and wastes the one
   request we are entitled to make carefully.
2. **Both placeholders are filled** — the affected-PR count and the First Changed Commit, read from
   the `git filter-repo` output per GitHub's own instructions.
3. **The fork count is re-run on the day of sending**, and the date and count in the request match it.
   *"If at the time that you submitted your notice, you identified all existing forks of that
   repository, we would process a valid claim against all forks in that network at the time we process
   the notice."* Enumerate-at-notice-time is the only mechanism that reaches a fork, and the
   enumeration is only good as of the moment it is stated.
4. **Chris has read the request body once.** He sends it; he should know what is in it.

If a precondition is not met on the day the trigger fires, the request waits. The trigger does not
expire; once satisfied it stays satisfied.

---

## Filing early — the one real exception

If the file is **copied out of the fork network into a new repository, a gist, a dataset, or a mirror**
— that is, if the data stops being a GitHub-internal object and starts being replicated somewhere we
do not control — then waiting is the wrong move, and this becomes a decision for Chris and Counsel
rather than a mechanical step.

That case is materially different from the exposure we have now. The standing trigger does **not**
cover it, and Counsel should be brought in the same day.

It has not happened. Both forks were verified on 2026-10-06 to hold no copy of the data at all.

---

## What this note is not

Counsel is explicit about the limits, so it is not read as authority for more than it is:

**It is not authority to send anything.** It fixes *when* the GitHub request is filed. It does not
authorise the send. **Chris sends the fork-owner notices and the GitHub request.** No agent in this
company can send outbound mail — the Gmail connection is read-and-draft only — and the GitHub
integration has no abuse or takedown tool. Counsel drafts. A human sends. That is a hard constraint,
not a preference.

**It is not authority to escalate against anyone.** The trigger is a step in cleaning up our own
mistake. It is not a basis for action against the fork owners, who have done nothing and hold
nothing. Nothing in this note pre-approves any further step.

**It is not authority to act automatically on the day it fires.** It is a standing instruction that
the *question* is settled, so the only remaining work that day is mechanical: fill two fields, re-run
one count, read it, send.

---

## Recording on DIG-1484

Post a comment on [DIG-1484](/DIG/issues/DIG-1484) at each of these points. Article 33(1) GDPR requires
the notification record to show what was done, not what was intended, and the Garante reads that
difference closely:

| When | What to record |
| --- | --- |
| Fork-owner notices sent | Date, channel used per owner, address or issue URL used, and the variant that went to which owner |
| Rewrite completed ([DIG-1496](/DIG/issues/DIG-1496)) | Date, the First Changed Commit, the affected-PR count, the `git filter-repo --version` used |
| Any fork-owner reply | Date, and the substance — including a reply that only asks a question |
| A fork deleted by its owner | Date, which owner, and how. Then re-run the fork count |
| Request filed with GitHub | Date, the case reference, the fork count stated in it |
| GitHub's outcome | Date, the substance of the reply, and the outcome |
| Any refusal | Date, and the refusal wording quoted |
| Article 33(1) notification filed | Date, and the reference. **Independent of everything above** |

Record the outcome honestly, including a refusal. A recorded refusal with a date is evidence that the
route was attempted and that the exposure persisted after it — which is exactly what the notification
record is supposed to show. A blank outcome field is the one thing that would look bad.

**The Article 33(1) notification is not gated by any of this.** It runs on its own statutory clock —
due **2026-10-08** per [DIG-1486](/DIG/issues/DIG-1486) — and does not wait for GitHub, for the
rewrite, or for anyone to reply to anything.