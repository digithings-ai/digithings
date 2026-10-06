# DIG-1497 — Private information removal pack

**Status: DRAFT. Nothing in this folder has been sent. Counsel advises only; a human sends.**

Prepared by Counsel, 2026-10-06, for Chris. Companion to [DIG-1484](/DIG/issues/DIG-1484).

Every fact in these drafts was re-derived from the live repository on 2026-10-06, not carried
over from earlier notes. Where an earlier figure was wrong, the corrected figure is used and the
correction is flagged in the draft.

**Two corrections were made to this pack after first draft.** Both are described where they apply:

1. **The "286 distinct customers" figure was wrong.** The file contains 87 customer records and 248
   email addresses. See below.
2. **The premise of the two fork-owner letters was wrong.** The file is **not** in the forks' history
   at all — both forks predate the commit. See *The first drafts of this pack were wrong* below. This
   correction changed what those letters actually ask for.

---

## The one thing to read first

**There is a number correction in this pack.** The brief for this task, and the earlier comments
on DIG-1484, describe the file as containing personal data for "286 distinct customers".

Counsel re-scanned the file. It does not. The counts are:

| Figure | Value |
| --- | --- |
| Lines in the file | 919 |
| Distinct tickets | 185 |
| Rows flagged `internal` | 372 |
| **Distinct customer records** | **87** |
| Distinct customer names | 86 |
| **Distinct email addresses, anywhere in the file** | **248** |
| — of those, in the `metadata.customer` field | 84 |
| — of those, only inside quoted message bodies | 164 |
| Distinct email domains | 101 |
| Distinct organisations | 47 |
| Lines carrying at least one email address | 784 |
| Lines carrying a name and/or organisation but no email address | 135 |

286 is not reachable by any counting method over this file. **Do not use the figure 286** — not in
the GitHub request, not in any reply to a fork owner, and not in the Garante notification. Use 248,
or "87 customer records and 248 identifiable email addresses".

The 248 figure is the stronger number for the security argument anyway, because 164 of those
people are not customers at all. They are colleagues, partners and other contact parties named
inside quoted support correspondence. They are exposed without ever having chosen to deal with us.

Confidence: **CONFIRMED** — re-derived twice from the blob, counts and digests only, no field
values printed, working copy shredded.

---

## What is in this folder

| File | What it is | Who sends it |
| --- | --- | --- |
| [fork-owner-request-itsnjstyle27.md](./fork-owner-request-itsnjstyle27.md) | Courtesy notice, fork owner 1 | Chris |
| [fork-owner-request-webclinic017.md](./fork-owner-request-webclinic017.md) | Courtesy notice, fork owner 2 | Chris |
| [github-private-information-request.md](./github-private-information-request.md) | GitHub Support private-information removal request | Chris |
| [trigger-note.md](./trigger-note.md) | Standing instruction on when the GitHub request is filed | — |

Each fork-owner file carries an email body and, because neither owner has a reachable public email
address, a fallback issue-body variant for use if email cannot be delivered.

---

## ⚠ The first drafts of this pack were wrong. Read this before sending anything.

On 2026-10-06 Counsel cloned both forks and fetched **every ref in each one** — branches, tags,
everything. The commit that introduced the file, `86cb1ec5…`, **is not in either fork.** Both forks
were created *before* the commit was made:

| | Forked | Commit date |
| --- | --- | --- |
| `itsnjstyle27/digithings` | 2026-08-18 | 2026-10-02 |
| `webclinic017/digithings` | 2026-05-29 | 2026-10-02 |

The file still resolves under both forks' URLs because **GitHub serves objects across a fork network
from the parent repository**. The parent still holds the commit, so any fork's name will serve it.

Three things follow, and all three change what these documents say:

1. **There is nothing in either fork to rewrite.** The first drafts asked the owners to run
   `git filter-repo` and included the commands. That was asking for something that cannot help. Those
   sections are deleted.
2. **Deleting a fork would not purge anything.** It would remove one of the three URLs and leave the
   object in our own repository. The first drafts framed fork deletion as the remedy. It is not.
   Both letters now say explicitly that the owner should not delete their work over our mistake.
3. **The letters are courtesy notices, not demands.** They tell the truth, ask for nothing, carry no
   deadline, and make no legal claim. That is the only honest version available.

**The fix is [DIG-1496](/DIG/issues/DIG-1496) alone.** Rewrite the parent, and the object dies in the
network — including under both fork URLs, which then start returning 404 on their own.

---

## Send order

**The two fork-owner notices can go out at any time, including today.** They do not depend on the
rewrite, because they no longer claim anything about it. Send them first if Chris has an address —
GitHub's policy treats contacting the user first as a real step, not a formality: *"Ask Nicely
First. A great first step before sending us a request to remove data is to try contacting the user
directly… This is not strictly required, but it is appreciated."*

**The GitHub request waits for the rewrite.** Two hard reasons:

- GitHub Support runs the server-side garbage collection **only if our own refs are already clean**:
  *"If you have successfully cleaned up all references other than PRs, and no forks have references to
  the sensitive data, Support will then… Run a garbage collection on the server to expunge the
  sensitive data from storage."* Filing before the rewrite wastes the request.
- The request needs two numbers the rewrite produces. See below.

There is **no 14-day wait.** The first version of the trigger note made filing depend on fork owners
failing to reply in a fortnight. They are being asked to do nothing, they hold nothing, and their
silence is not a fact about our exposure. That trigger is withdrawn. The real trigger is the rewrite —
see [trigger-note.md](./trigger-note.md).

---

## The two values that do not exist yet

The GitHub request contains two placeholders. They cannot be filled by Counsel — they are produced
by the rewrite, which has not run.

| Placeholder | Where it comes from |
| --- | --- |
| `<<< FILL: NUMBER OF AFFECTED PULL REQUESTS >>>` | `grep -c '^refs/pull/.*/head$' .git/filter-repo/changed-refs` in the rewritten clone |
| `<<< FILL: FIRST CHANGED COMMIT >>>` | the `NOTE: First Changed Commit(s):` line that `git-filter-repo` prints on completion |

DIG-1496 is assigned to DevOps and is currently `todo`. Until it is `done`, those two strings stay
as they are. **A request with a placeholder still in it must not be sent.**

---

## Pre-send checklist

Run through this immediately before any send. It takes about two minutes.

**For the GitHub request:**

- [ ] DIG-1496 is `done`, and the rewrite has been pushed to `digithings-ai/digithings`.
- [ ] Both placeholders in `github-private-information-request.md` are replaced with real values.
- [ ] `git filter-repo --version` in the rewritten clone is **2.47 or later**. Below that,
      `--sensitive-data-removal` does not exist and the rewrite is not the rewrite GitHub documents.
- [ ] If the filter-repo output shows a note about LFS objects, that note is included in the request.
- [ ] Fork count re-run **on the day of sending**, and the date and count in the request match it:
      `gh api repos/digithings-ai/digithings --jq .forks_count` → expect `2`.
- [ ] The paginated fork list re-run the same day and still returns exactly `itsnjstyle27` and
      `webclinic017`. If a third fork has appeared, the enumeration must be updated before sending.
      Enumerate-at-notice-time is the only mechanism that reaches a fork.
- [ ] The drafting-note box at the top of section 6 is deleted — it is not part of the request.
- [ ] The conditional paragraph in section 5 about opening a public issue is either completed or
      deleted. Sending it half-finished would claim a step that was not taken.
- [ ] The request is pasted as **plain text into the body of the web form**, not attached.
      Their form warns: *"Sending your request in an attachment may result in processing delays."*

**For the fork-owner notices:**

- [ ] Chris is sending the version that matches the actual state: Option A before the rewrite,
      Option A-after once it is done.
- [ ] Exactly one channel per owner. Not both.

---

## The reply address — Counsel's recommendation, not a choice

**Use `contact@digithings.ai`.** It is published at [digithings.ai](https://digithings.ai/) and is the
only address on the site.

The alternative was `dany.stefan@matador.ai`, from the `SECURITY.md` both forks inherited from us.
Counsel investigated whether it is monitored, as instructed, and **could not establish that it is.
Confidence: UNKNOWN.** What was checked:

- It appears exactly once in the repository, at `SECURITY.md:211`, as an unreferenced literal. No
  code, config, secret or CI job routes mail to it.
- It has been published continuously since 2026-04-18 and never edited — only the subject tag changed
  once, on 2026-10-01.
- No agent instruction, org config or Paperclip record anywhere names it — or any mailbox — as monitored.
- `matador.ai` MX points at Google Workspace; `digithings.ai` MX points at Proton Mail. Both deliver.

Six months of deliberate publication in a security-disclosure section, alongside a 72-hour
acknowledgement commitment, is real evidence of intent. **It is not evidence that anyone reads it.**
That distinction decides this: an unread mailbox does not complain, so a request sent there would
fail silently while the exposure continued. Counsel is not willing to recommend a channel whose
monitoring status cannot be shown, and says so plainly rather than offering it as a coin-flip.

Switching later is a one-line change if Chris knows the mailbox is live.

---

## The remaining decision for Chris

**How to reach each fork owner, since neither has a reachable address.** Verified 2026-10-06:
no email on either GitHub profile, no contact address in either README, no `SUPPORT.md` in either fork.
Both forks have issues enabled, and Ask Nicely First explicitly contemplates *"creating an issue or
pull request in the repository"* — but our own `SECURITY.md`, which both forks carry, says *"Do not
open a public GitHub issue."* That instruction is addressed to security reporters rather than to us,
but it does cut against opening a public issue as the first move.

Both files carry both variants. Counsel's preference is Option A if Chris holds any address from
outside GitHub; otherwise Option B, once, with no deadline language.

If no channel can be found at all, **record that fact.** It strengthens the GitHub request: it then
shows the "ask nicely" step was genuinely taken and the reason it produced nothing was that no
contact route existed — not that it was skipped.

---

## Counsel's confidence and honest prediction

| Point | Label |
| --- | --- |
| All factual assertions in these drafts | **CONFIRMED** — verified against the live repository 2026-10-06 |
| That neither fork holds a copy of the data | **CONFIRMED** — every ref in both forks fetched; commit absent from both |
| The framing of the eligibility argument as identity and account-takeover exposure | **CONFIRMED** as the strongest available honest argument |
| GitHub will grant the request | **LIKELY refusal.** Stated as a prediction, not a hedge on the facts |

A note on the second row, because it is the correction that mattered. It was established not by
reading GitHub's documentation but by cloning both forks and fetching everything in them. The
documentation is compatible with both readings — GitHub does not promise that a fork URL resolves
only what the fork itself contains — so the empirical test was the only way to settle it.

Predicting refusal is the honest position and it does not weaken the request. The file contains no
credentials, so the literal trigger in GitHub's own documentation — that the risk *"can't be
mitigated by rotating affected credentials"* — is not met, and there is nothing to rotate. The
request is still worth filing: the identity-and-account-takeover argument is the strongest one
available, GitHub processes the request either way, and an unanswered request is itself a record
for the Garante file. What Counsel will not do is write a request that overstates the facts to
chase a better odds of success. That would be the wrong trade.

---

## Two things Counsel deliberately did not do

**No DMCA notice.** A DMCA takedown asserts copyright infringement. It asserts rights over the
forks' copies, which are not ours to assert — the forks are third-party repositories. The claim is
not available to us and filing it would be a false assertion. It is out.

**GDPR is not the lead.** Two reasons. GitHub routes privacy-only complaints elsewhere: *"Privacy
complaints. If you wish to access, transfer, change, or delete your personal information on GitHub,
please contact us via our Privacy contact form."* And their eligibility test is not privacy at all —
it is a *"specific or targeted security risk"*, defined as *"exposure to physical danger, identity
theft, or increased likelihood of unauthorized access to physical or network facilities"*, with
credentials, AWS tokens, network diagrams and SSNs as the worked examples.

Leading with GDPR walks into a form that will redirect the request. GDPR appears once, clearly
subordinate, only in the GitHub request, and only to record that a supervisory-authority process is
open. It is never the eligibility theory.

One honest weakness Counsel records rather than hides: the request asks for a **whole file**, and
GitHub warns that this *"may increase the time required to process your request"*. The request
deals with that head-on rather than leaving it to be discovered — see the section in the GitHub
draft titled *Why a whole-file request, and why that is still proportionate*.