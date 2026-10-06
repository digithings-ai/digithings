# Trigger note — when to file the GitHub request

**Status: standing instruction. Prepared by Counsel 2026-10-06.**
File alongside [DIG-1484](/DIG/issues/DIG-1484). This is the operational counterpart to
[trigger-note](.) — read it before the fork-owner requests go out.

**Purpose.** So that the decision to file with GitHub does not have to be re-made from scratch in
two weeks, at the exact moment when the people involved are least willing to spend attention on it.
This note fixes the trigger condition in advance. If the condition is met, the request goes out
without a fresh discussion — subject only to the preconditions below.

---

## The standing instruction

> The GitHub private-information removal request is filed when **both** fork owners have had a
> fourteen-day window to respond and the file is **still publicly retrievable** in at least one fork
> at the pinned commit `86cb1ec5d62b2422cf2c312b6d63722c86fb2000`.
>
> The fourteen days runs from the date the **second** of the two fork-owner requests was sent. If
> both were sent on the same day, from that day. Record the start date on DIG-1484 when the requests
> go out, so the clock has an unambiguous anchor.

Counsel proposes **fourteen calendar days**. The reason for a number rather than a judgment call:
"a reasonable interval" invites an argument at the moment it is least useful. Fourteen days is long
enough to be evidently fair to a stranger who does not know they are holding a copy, and short
enough that the exposure does not sit unaddressed for a month. It also matches the two-week window
the fork-owner requests themselves state, so nobody can say the two dates are inconsistent.

---

## Preconditions — all must hold before filing

The trigger condition is necessary but not sufficient. The request cannot be sent until:

1. **[DIG-1496](/DIG/issues/DIG-1496) is `done`** — the history rewrite has landed on
   `digithings-ai/digithings`. GitHub runs the server-side garbage collection *"if you have
   successfully cleaned up all references other than PRs"*. Filing before the rewrite wastes the
   request, and would be asking GitHub to act on a repository we have not cleaned ourselves.
2. **Both placeholders are filled** — the affected-PR count and the First Changed Commit.
3. **The fork count is re-run on the day of sending** and the date and count in the request match it.
   Enumerate-at-notice-time is the only mechanism that reaches a fork, and the enumeration is only
   good as of the moment it is stated.
4. **Chris has confirmed the reply address** — `contact@digithings.ai` unless he has decided
   otherwise. See the open decision in [README.md](./README.md).

If a precondition is not met on the day the trigger fires, the request waits for the precondition.
The trigger does not expire; it is satisfied and stays satisfied.

---

## Early trigger — do not wait out the fourteen days

File sooner, without waiting for the full window, if **any** of these occurs:

- A fork is deleted by its owner. That is the good outcome for that fork, but it changes the
  enumeration — the request must be updated to reflect the fork set as it stands at the time of
  notice, not as it stood when the requests went out. Re-run the count immediately.
- The file is **copied to a new fork or a new repository** by anyone. This is the strongest reason
  to move fast: a copy spreading is a different problem from a copy existing, and it is the one
  case where the fourteen-day courtesy period is actively harmful.
- A fork owner replies saying they will not remove it. Do not wait for the remaining days on a fork
  that has declined. File immediately, quoting their reply.
- The file is indexed by a search engine or appears in any dataset. Once it is indexed, the "please
  remove this" request to a stranger stops being effective.

---

## What the fourteen days is not

Counsel is explicit about the limits of this note so it is not read as authority for more than it is:

**It is not authority to send anything.** It fixes *when* the GitHub request is filed. It does not
authorise the send itself. **Chris sends both the fork-owner requests and the GitHub request.** No
agent in this company can send outbound mail — the Gmail connection is read-and-draft only — and the
GitHub integration has no abuse or takedown tool. Counsel drafts. A human sends. This is a hard
constraint, not a preference.

**It is not authority to escalate.** If the trigger fires and the request is filed, the next step is
whatever comes back. Counsel advises. Counsel does not decide what happens next, and nothing in this
note pre-approves a further step.

**It is not an instruction to file automatically on the day it fires.** It is a standing instruction
that the question is settled, so that the only remaining work on that day is mechanical: fill two
fields, re-run one count, send.

---

## Recording on DIG-1484

Post a comment on DIG-1484 at each of these points. Article 33(1) GDPR requires the notification
record to show what was done, not what was intended, and the Garante reads that difference closely:

| When | What to record |
| --- | --- |
| Fork-owner requests sent | Date, time, channel used per owner, address or issue URL used, and which variant (email or issue) went to which owner |
| Rewrite completed ([DIG-1496](/DIG/issues/DIG-1496)) | Date, the First Changed Commit, the affected-PR count, the `git filter-repo --version` used |
| Any fork-owner reply | Date, and the substance: action taken, action refused, or no commitment |
| A fork removed | Date, which owner, and how |
| Request filed with GitHub | Date, the case reference, the fork count stated in it |
| GitHub's outcome | Date, the substance of the reply, and the outcome |
| Any refusal | Date, and the refusal wording quoted |

Record the outcome honestly, including a refusal. A recorded refusal with a date is evidence that
the route was attempted and that the exposure persisted after it — which is exactly what the
notification record is supposed to show. A blank outcome field is the one thing that would look bad.

---

## If the window opens and nothing has changed

Fourteen days passes, the file is still in a fork, and the rewrite is done. That is the expected
case, not a failure. File the request, record the outcome, and proceed to Counsel's advice on the
supervisory-authority route — which is already open and does not depend on GitHub's answer.

The GitHub request is one of several routes and not the most important one. The authority
notification obligation under Article 33(1) GDPR runs on its own clock and does not wait for GitHub,
a fork owner, or anyone else.