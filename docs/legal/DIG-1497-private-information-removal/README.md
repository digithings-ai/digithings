# DIG-1497 — Private information removal pack

**Status: DRAFT. Nothing in this folder has been sent. Counsel advises only; a human sends.**

Prepared by Counsel, 2026-10-06, for Chris. Companion to [DIG-1484](/DIG/issues/DIG-1484).

Every fact in these drafts was re-derived from the live repository on 2026-10-06, not carried
over from earlier notes. Where an earlier figure was wrong, the corrected figure is used and the
correction is flagged in the draft.

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
| [fork-owner-request-itsnjstyle27.md](./fork-owner-request-itsnjstyle27.md) | Removal request, fork owner 1 | Chris |
| [fork-owner-request-webclinic017.md](./fork-owner-request-webclinic017.md) | Removal request, fork owner 2 | Chris |
| [github-private-information-request.md](./github-private-information-request.md) | GitHub Support private-information removal request | Chris |
| [trigger-note.md](./trigger-note.md) | Standing instruction on when non-response triggers filing | — |

Each fork-owner file carries an email body and, because neither owner has a reachable public email
address, a fallback issue-body variant for use if email cannot be delivered.

---

## Send order — this is not optional

**1. DIG-1496 completes.** The history rewrite must land first. Two reasons, both hard:

- GitHub Support runs the server-side garbage collection **only if our own refs are already clean**.
  Their documentation says so directly: *"If you have successfully cleaned up all references other
  than PRs, and no forks have references to the sensitive data, Support will then… Run a garbage
  collection on the server to expunge the sensitive data from storage."* Filing before the rewrite
  wastes the request.
- The request needs two numbers the rewrite produces. See below.

**2. The two fork-owner requests go out.** Send these first. GitHub's policy treats this as a
precondition, not a courtesy: *"Ask Nicely First. A great first step before sending us a request to
remove data is to try contacting the user directly… This is not strictly required, but it is
appreciated."*

**3. Wait 14 days**, per the trigger note.

**4. The GitHub request goes out**, with the fork count re-run on the day it is sent.

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
- [ ] Chris has read `trigger-note.md` and agreed the 14-day interval.
- [ ] The request is pasted as **plain text into the body of the web form**, not attached.
      Their form warns: *"Sending your request in an attachment may result in processing delays."*

---

## Two decisions for Chris that Counsel cannot make

**1. Which reply address.** The drafts use `contact@digithings.ai`, because that is the address we
publish at [digithings.ai](https://digithings.ai/) and it is the only one on the site.

The alternative is `dany.stefan@matador.ai`, which appears in the `SECURITY.md` that both forks
inherited from us. **Counsel cannot confirm that mailbox is monitored.** If it is, it is the more
natural channel for a data-removal request and the drafts can be switched with a one-line change.
If it is not, using it means a customer-data request sits unread in an unattended mailbox, and the
14-day clock runs against a request nobody sees. Verify before sending.

**2. Whether the fork-owner requests go by email or by GitHub issue.** Neither `itsnjstyle27` nor
`webclinic017` has a public email address on their GitHub profile, no contact email in either
README, and no `SUPPORT.md` in either fork. So the primary channel cannot actually be delivered as
written. Both files carry both variants. Ask Nicely First explicitly contemplates *"creating an
issue or pull request in the repository"*, and issues are enabled on both forks — but note that our
own `SECURITY.md`, which both forks carry, says *"Do not open a public GitHub issue."* That
instruction is addressed to security reporters, not to us, but it does cut against opening a
public issue as the first move. Counsel's recommendation is in each file.

---

## Counsel's confidence and honest prediction

| Point | Label |
| --- | --- |
| All factual assertions in these drafts | **CONFIRMED** — verified against the live repository 2026-10-06 |
| The framing of the eligibility argument as identity and account-takeover exposure | **CONFIRMED** as the strongest available honest argument |
| GitHub will grant the request | **LIKELY refusal.** Stated as a prediction, not a hedge on the facts |

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