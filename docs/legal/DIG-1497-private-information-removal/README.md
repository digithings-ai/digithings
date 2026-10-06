# DIG-1497 — Private information removal pack

**Status: DRAFT. Nothing in this folder has been sent. Counsel advises only; a human sends.**

> ### Chris's decisions, 2026-10-06 — read these before reading anything else
>
> | Question | Decision |
> | --- | --- |
> | Reply address | **`contact@digithings.ai`** — confirmed |
> | How to reach the two fork owners | **Do not contact them at all** |
> | The corrected text | **Approved as written** |
>
> **Consequence: the two fork-owner notices in this folder are withdrawn and must not be sent.** They
> are kept unchanged as the record Art. 33(1) section 6 asks for. The GitHub request discloses the
> decision truthfully rather than claiming a contact that never happened. See *Decisions taken* below.


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
| [fork-owner-request-itsnjstyle27.md](./fork-owner-request-itsnjstyle27.md) | **WITHDRAWN** — retained as a record, not to be sent | nobody |
| [fork-owner-request-webclinic017.md](./fork-owner-request-webclinic017.md) | **WITHDRAWN** — retained as a record, not to be sent | nobody |
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

**The two fork-owner notices are withdrawn and are not sent.** Chris decided on 2026-10-06 not to
contact either fork owner. Section 5 of the GitHub request says so plainly rather than claiming a
contact that did not happen. See *Decisions taken* below.

**The GitHub request is the only thing in this folder that goes anywhere**, and it waits for the
rewrite.

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

## The values that do not exist yet

The GitHub request contains four placeholders. None can be filled by Counsel — all four are produced
by the rewrite, which has not run.

| Placeholder | Where it comes from |
| --- | --- |
| `<<< FILL: NUMBER OF AFFECTED PULL REQUESTS >>>` | `grep -c '^refs/pull/.*/head$' .git/filter-repo/changed-refs` in the rewritten clone |
| `<<< FILL: FIRST CHANGED COMMIT >>>` | the `NOTE: First Changed Commit(s):` line that `git-filter-repo` prints on completion |
| `<<< FILL: DATE OF REWRITE PUSH, YYYY-MM-DD >>>` | the date of the force-push in DIG-1496 §7 — added by the section 6 amendment |
| `<<< FILL: THE PULL REQUEST REFERENCES THAT STILL HOLD 86cb1ec5d >>>` | the `refs/pull/*` refs still resolving to `86cb1ec5d` after the push — added by the section 6 amendment |

The last two were added by the section 6 amendment Chris approved on 2026-10-06 at 21:08Z. The
amendment removed one sentence that would have been false at send time — *"the file removed from all
reachable history"* — and replaced it with the narrower, accurate claim plus the evidence for it.
See [t0-preflight.md](./t0-preflight.md) §5.

DIG-1496 is assigned to DevOps and is currently `blocked`. Until it is `done`, those four strings
stay as they are. **A request with a placeholder still in it must not be sent.**

---

## Pre-send checklist

Run through this immediately before any send. It takes about two minutes.

**For the GitHub request:**

- [ ] DIG-1496 is `done`, and the rewrite has been pushed to `digithings-ai/digithings`.
- [ ] All four placeholders in `github-private-information-request.md` are replaced with real values.
      `grep -n 'FILL' github-private-information-request.md` returns nothing.
- [ ] `git filter-repo --version` in the rewritten clone is **2.47 or later**. Below that,
      `--sensitive-data-removal` does not exist and the rewrite is not the rewrite GitHub documents.
- [ ] If the filter-repo output shows a note about LFS objects, that note is included in the request.
- [ ] Section 6's list of the pull request refs that still hold `86cb1ec5d` is filled with **ref
      names**, not with the count alone. Support can dereference a named ref; it cannot dereference
      "9 merged-PR refs".
- [ ] A one-byte range request against `86cb1ec5d` still returns **206**. If it returns **404**, stop:
      do not send this text. See [t0-preflight.md](./t0-preflight.md) §4 for the short alternative
      confirmation notice that branch needs.
- [ ] Fork count re-run **on the day of sending**, and the date and count in the request match it:
      `gh api repos/digithings-ai/digithings --jq .forks_count` → expect `2`.
- [ ] The paginated fork list re-run the same day and still returns exactly `itsnjstyle27` and
      `webclinic017`. If a third fork has appeared, the enumeration must be updated before sending.
      Enumerate-at-notice-time is the only mechanism that reaches a fork.
- [ ] The drafting-note box at the top of section 6 is deleted — it is not part of the request.
- [ ] The "Four placeholders" table at the top of the request file is deleted. It sits above
      `BEGIN REQUEST BODY`, so leaving it puts a drafting note in front of the form.
- [ ] Nothing in the request claims we contacted a fork owner. Section 5 must read as written: no
      contact was made, no channel existed, and there was nothing for an owner to do. No placeholder
      survives in section 5.
- [ ] The request is pasted as **plain text into the body of the web form**, not attached.
      Their form warns: *"Sending your request in an attachment may result in processing delays."*

**There is no second checklist.** The fork-owner notices are withdrawn and are not sent.

---

## The reply address — decided

**`contact@digithings.ai`.** Chris confirmed this on 2026-10-06. The investigation into the alternative is kept below, because the reasoning is the useful part. It is published at [digithings.ai](https://digithings.ai/) and is the
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

## Decisions taken — Chris, 2026-10-06

| Question | Decision |
| --- | --- |
| Reply address | **`contact@digithings.ai`.** Confirmed. |
| How to reach the two fork owners | **Do not contact them at all.** |
| The corrected text | **Approved as written.** |

Counsel's reasoning on the second decision, so the record shows it was reasoned and not merely
obeyed. **All of it cuts the same way: the decision is sound.**

**Legally, it costs nothing.** GitHub's policy says of the contact-first step: *"This is not strictly
required, but it is appreciated."* Declining it does not weaken eligibility, and nothing in the
request depends on having contacted them.

**Factually, there was nothing to ask.** Both forks predate the commit and neither contains the file
in its own object store. Neither owner holds a copy. There is no file in their history to rewrite and
nothing for them to delete, so a notice could not have requested any action — it would have been a
courtesy, and a courtesy notice about our own mistake is a thing to be asked of a stranger, not a
thing they are obliged to carry.

**It removes a contradiction with our own published instruction.** The `SECURITY.md` both forks
inherit says *"Do not open a public GitHub issue."* A public issue was the only remaining channel.
Choosing not to write at all is the option that does not cut against our own file.

**The cost, stated rather than hidden.** The request can no longer say *"we tried to reach them and
were rebuffed."* It says *"we did not write to them, and here is why."* That is weaker rhetoric and it
is the truth. A support agent reading it learns that we investigated carefully and declined to write
— not that we were ignored. Counsel prefers the true version. Inventing the stronger one would be the
easiest available way to get this request dismissed for bad faith, and it would put a false statement
in front of a company we may have to deal with again.

The withdrawn notices are retained, unaltered, in this folder. Art. 33(1) section 6 asks the register
to show the difference between what was done and what was proposed; deleting them would erase the
second half of that.

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