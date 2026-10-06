# Fork owner request — `itsnjstyle27`

> ## ⛔ NOT TO BE SENT — withdrawn by decision
>
> **Chris decided on 2026-10-06 not to contact this fork owner. Do not send this letter, by any
> channel, to anyone.** Neither it nor the version for the other owner is part of the incident
> response.
>
> It is kept here unchanged because Art. 33(1) section 6 asks for the record to show the difference
> between what was done and what was proposed. Nothing in this document has been sent to anyone.
>
> The only document in this folder that goes anywhere is
> [github-private-information-request.md](./github-private-information-request.md), and only after
> [DIG-1496](/DIG/issues/DIG-1496) completes and Chris sends it.

**Repository:** https://github.com/itsnjstyle27/digithings
**Display name:** Neerav Mishra
**Forked:** 2026-08-18 · last push 2026-08-18 · default branch `develop`
**Send order:** **none. Withdrawn — see the notice above.**

**Status: WITHDRAWN. Not sent, and not to be sent.** Drafted by Counsel 2026-10-06; withdrawn by Chris the same day.

---

## Read this first — the first draft of this letter was wrong

The first version of this letter told Neerav that the customer-data file was **in his fork's history**, and asked him to rewrite his history to remove it or delete the fork.

**Both claims are false, and Counsel verified this on 2026-10-06.**

| Test | Result |
| --- | --- |
| `git fetch https://github.com/itsnjstyle27/digithings '+refs/*:refs/allr/*'` | Only 2 refs exist: `heads/Neerav`, `heads/develop` |
| Is commit `86cb1ec5…` present after fetching **every** ref in the fork? | **No. Not present.** |
| `git fetch https://github.com/itsnjstyle27/digithings 86cb1ec5d62b2422cf2c312b6d63722c86fb2000` | Succeeds — the blob resolves at that SHA |
| Is the raw URL live today? | Yes — HTTP 206 on a 1-byte range request |
| Fork date vs commit date | Forked **2026-08-18**; commit dated **2026-10-02** |

The mechanism is GitHub's fork network. An object held by the parent repository resolves under any fork's URL, whether or not that fork ever had the commit. So the URL is live because **we** still have the commit — not because he has anything to clean.

Two consequences follow, and they change the letter completely:

1. **There is nothing in his history to rewrite.** Asking him to run `git filter-repo` would delete nothing. A previous draft included those instructions. They are gone.
2. **Deleting the fork removes only that one URL.** It does not purge the object, because the object is ours. Asking a stranger to destroy his repository for that is not proportionate, and this letter no longer frames it as the remedy.

The honest letter is a **courtesy notice**: tell him what resolves under his URL, tell him the fix is on our side, and give him a genuinely optional way to make the URL stop sooner. That is what Option A below says.

---

## Channel problem — read first

Three verified negatives, as of 2026-10-06:

- No email address on his GitHub profile.
- No contact address in his fork's `README` (which exists only on `develop`, and carries no address).
- No `SUPPORT.md` or `.github/SUPPORT.md` in the fork.

GitHub's own Private Information Removal Policy says, under *"Ask Nicely First"*: *"They may have listed contact information on their public profile page or in the repository's README or Support file, or you could get in touch by creating an issue or pull request in the repository."* All three of those channels are available to us **except** the first two, which do not exist.

One of them does contain an address: both forks carry our own `SECURITY.md`, which lists **`dany.stefan@matador.ai`** and instructs reporters **not** to open a public issue. That address is ours, not his, so it is not a route *to* him — and using a public issue as the channel would contradict the instruction in our own file.

**Routes, in order:**

- **Route A (preferred).** An address Chris already holds for Neerav, from outside GitHub. Nothing published tells us one exists; Counsel could not find one and will not invent one. If Chris has one, use Option A.
- **Route B (fallback).** Open a GitHub issue on the fork using Option B. This is the channel GitHub's policy contemplates. It is public and permanent.

**Do not do both.** One contact, one message.

---

## Option A — WITHDRAWN, do not send

```
From:    contact@digithings.ai
To:      [address Chris holds for Neerav]
Reply-to: contact@digithings.ai
Subject: A data file of ours is reachable through your fork's URL — nothing for you to clean up
```

---

Hello Neerav,

We are doing a security and privacy review of our own public repository and we found a mistake on our side. I want to tell you about it, and to be clear that it is not a problem you created.

**What we found**

Our repository `digithings-ai/digithings` included a file of support-ticket exports:

```
apps/digithings-stack-cloudflare/container/seed/occ_tickets.jsonl
```

It was added on 2 October 2026 in commit `86cb1ec5d62b2422cf2c312b6d63722c86fb2000`. It contains roughly 87 customer records and 248 email addresses across 185 tickets — including 135 people named inside the correspondence who are not customers of ours at all.

Because your repository is a fork of ours, this file is currently reachable through your URL as well:

```
https://github.com/itsnjstyle27/digithings/blob/86cb1ec5d62b2422cf2c312b6d63722c86fb2000/apps/digithings-stack-cloudflare/container/seed/occ_tickets.jsonl
```

**The part that matters for you: your repository does not contain that file.**

We checked this directly. Your fork has two branches, `Neerav` and `develop`, and after fetching every ref in it, the commit that introduced the file is not present. Your fork was created on 18 August 2026; the commit is dated 2 October 2026. There is nothing in your history to remove, and **I am not asking you to remove anything.**

The URL above resolves only because GitHub serves objects across a fork network from the parent repository. As long as we still hold the commit, that URL resolves for everyone — through our repository and through yours.

**What we are doing about it**

The fix is entirely on our side. We are rewriting the history of our own repository to purge the file, and once that is done and GitHub has collected the unreferenced objects from their servers, the URL will stop working for everyone, including us. We are also required to report this to our data protection authority, and we will.

**If you want the URL to stop sooner, you have one option — and it is entirely optional**

Deleting your fork makes that URL stop resolving immediately, because the parent is ours and we are purging it separately. **Please do not do this on our account.** It would mean discarding your work, and your work is not the problem. If you would rather keep the fork, keeping it is a perfectly good answer, and nothing will be held against it.

There is nothing to rewrite in your history, so there is no history-rewriting step for you to run. If anything in this message is unclear, or you want to know more about what was in the file before you decide anything, just reply and ask.

**Timing**

There is no deadline here. Nothing about this message is a legal claim, a copyright notice, or a demand — it is a courtesy notice, and a sincere one, because this exposure came from our mistake and not from anything you did. We would simply rather you heard it from us than noticed it yourself.

**Who to reply to**

Reply to this address. Chris Stefan is the point of contact here and will answer directly.

Thank you for reading it.

Chris Stefan
Digi Ecosystem
contact@digithings.ai

---

## Option A-after — WITHDRAWN, do not send (post-rewrite wording)

**Only use this version if the rewrite has actually finished and GitHub's garbage collection has run.** Otherwise a reader can check the URL and find it still live, and we will have lost their trust for no gain.

Identical to Option A except that the section **"What we are doing about it"** is replaced with:

> **What we have already done about it**
>
> We have rewritten the history of our repository to purge this file. That work is finished. We have separately asked GitHub to remove the now-unreferenced objects from their storage, and to expire cached copies of the file.
>
> If you kept your fork, the URL above may still resolve for a short while, because GitHub collects unreferenced objects on its own schedule. We will write to you again when the link stops working.

## If the rewrite is genuinely in flight when Chris sends — WITHDRAWN, do not send

Option A is written so that it stays true throughout a rewrite, because it never claims the rewrite is finished. **Use Option A unchanged.** If you want to acknowledge the work in progress, add one sentence to the end of the *"What we are doing about it"* section:

> The rewrite is under way now. We will confirm to you when it completes.

That sentence is the only one that is not safe to add while [DIG-1496](/DIG/issues/DIG-1496) is still `todo`. Do not write "we have asked GitHub to purge it from their storage" at any point before the GitHub request in `github-private-information-request.md` has actually been filed — at the moment these letters go out, we have not asked GitHub anything.

---

## Option B — WITHDRAWN, do not send

Use this only if Chris holds no address for Neerav. It is public and permanent. Do not also send Option A.

**Title:** Customer data from `digithings-ai/digithings` resolves through this fork's URL — no action required

**Body:**

Hello Neerav,

We are reviewing our own public repository and found a mistake on our side. A file of support-ticket exports that should never have been published is reachable through this fork's URL:

```
https://github.com/itsnjstyle27/digithings/blob/86cb1ec5d62b2422cf2c312b6d63722c86fb2000/apps/digithings-stack-cloudflare/container/seed/occ_tickets.jsonl
```

It contains real names, email addresses and verbatim customer correspondence — roughly 87 customer records and 248 email addresses across 185 tickets.

**Your repository does not contain this file.** We fetched every ref in this fork and the commit that introduced it is not present here; your fork predates the commit. The link resolves only because GitHub serves objects across a fork network from the parent repository, `digithings-ai/digithings`. There is nothing in your history to remove and **we are not asking you to remove anything.**

We are rewriting our own history to purge the file. Once that is done and GitHub collects the unreferenced objects, the link will stop working for everyone.

If you would prefer the link to stop resolving sooner, deleting the fork will do it — but that is entirely your call, and we would not ask you to discard your work over our mistake.

No deadline, no demand, nothing owed by you. Reply here or write to contact@digithings.ai if anything is unclear.

Chris Stefan
Digi Ecosystem