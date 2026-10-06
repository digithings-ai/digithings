# Removal request — fork owner `webclinic017`

**Status: DRAFT. Not sent.** Prepared by Counsel 2026-10-06. Chris sends.

Repository: [webclinic017/digithings](https://github.com/webclinic017/digithings)
Display name: WebClinic
Forked: 2026-05-29 · last push 2026-05-25 · default branch `develop`

**Send order:** after [DIG-1496](/DIG/issues/DIG-1496) is `done`, and before the GitHub request.
See [README.md](./README.md).

Note on dates: this fork was created 2026-05-29 but the last push was 2026-05-25, which is before the
fork date. That is normal — GitHub records the fork point from the parent at the moment of forking,
and the displayed push timestamp reflects the fork commit itself rather than a later push of new
work. The relevant fact for this request is that the fork predates the exposure commit
(2026-10-02) only if the parent had it at fork time, which it did not — the file arrived in the
parent afterwards and reached this fork when its branch was rebased or re-pulled. Counsel confirms
the blob **is** currently retrievable in this fork at the pinned commit; that is the fact the
request rests on, and it is verified, not inferred from dates.

---

## Channel problem — read first

Same as the other fork owner, verified rather than assumed:

- No email on the GitHub profile.
- No contact email in the `README` on the fork's `develop` branch.
- No `SUPPORT.md`, no `.github/SUPPORT.md`.

Routes, in Counsel's order of preference:

**Route A — an address Chris already holds.** Use the email body below. Send from
`contact@digithings.ai`.

**Route B — a GitHub issue on the fork.** Issues are enabled. GitHub's policy names this route:
*"or you could get in touch by creating an issue or pull request in the repository."*

The same tension applies: the fork carries **our** `SECURITY.md`, which says *"Do not open a public
GitHub issue."* That is addressed to security reporters, not to us. But a public issue is a
timestamped public record that a customer-data incident was asserted. Last resort only.

**Do not use both channels for the same owner.**

---

## Option A — email body (preferred)

**From:** `contact@digithings.ai`
**To:** *address Chris holds for this fork owner*
**Reply-to:** `contact@digithings.ai`
**Subject:** Request to remove customer data from your digithings fork

---

Hello,

I am writing on behalf of Digi Ecosystem, which maintains the digithings-ai/digithings repository
that your fork is derived from.

We are doing a security and privacy review of our own public repository, and we found a mistake on
our side. We want to tell you about it and ask for your help fixing it.

**What we found.** Our repository at digithings-ai/digithings contains a support-data file at:

    apps/digithings-stack-cloudflare/container/seed/occ_tickets.jsonl

It was added on 2 October 2026 in commit `86cb1ec5d62b2422cf2c312b6d63722c86fb2000`. When we built a
multilingual ticket-search feature we put a snapshot of our support data into the repository as test
input. That data was never meant to be public. It is a copy of real support tickets, and it
contains the names, email addresses and organisations of people who contacted us, along with the
text of what they wrote to us and what our staff replied. It covers roughly 87 customer records and
248 email addresses across 185 tickets, including 135 people named in the correspondence who are
not customers of ours at all. We are telling you this because the exposure is ours and we are
fixing it. We are not asking you for anything except help with the copy in your repository.

Your fork is derived from that repository and the file is present in your fork's history. It is
still reachable today at this permanent link, which does not require an account to open:

    https://github.com/webclinic017/digithings/blob/86cb1ec5d62b2422cf2c312b6d63722c86fb2000/apps/digithings-stack-cloudflare/container/seed/occ_tickets.jsonl

**What we would like you to do.** Either of these fixes it completely, and the first one is easier:

1. **Delete your fork.** Nothing else is needed. This is the cleanest outcome and we are happy for
   you to take this route.

2. **Rewrite your history** to drop that file, then push with `--force`. Full instructions are at
   the end of this message.

If you take the second route there is one part people miss, and it matters: **rewriting your history
does not remove the file from GitHub's servers.** The old objects stay in GitHub's storage until
GitHub itself runs a cleanup. After you push the rewrite you also need to ask GitHub Support to run
a garbage collection for your repository, using their own
"Removing sensitive data from a repository" form:
https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository

**What we are not asking for.** We are not asking you to stop using the code, to close an issue, to
revert anything else, or to delete the repository. The rest of the project is MIT-licensed and we
have no issue with you keeping and using all of it. We only want this one file gone. If deleting
your fork would be awkward for any reason, say so and we will work around it.

**How we handled it on our side.** We have already rewritten the history of digithings-ai/digithings
to remove the file, and we have asked GitHub to purge it from their storage. We are also notifying
our data protection authority, because we are the controller of this personal data and the correct
step is to report it.

**Timing.** Would you be able to do this within the next two weeks? We have set that as our own
deadline, and if we do not hear back by then we will have to ask GitHub to act against the fork
directly. We would much rather deal with you than with GitHub. Nothing about this message is a legal
claim, a copyright notice or a demand — it is a request, and a sincere one, because the exposure
came from our mistake.

If anything here is unclear, or you think we have the wrong idea about something, please just reply
and say so. Chris Stefan is the point of contact at this address and will answer directly.

Thank you for reading this.

Chris Stefan
Digi Ecosystem
contact@digithings.ai

---

### Instructions to clean the history (attached to the email above)

Run from a fresh mirror clone, in a new directory.

```bash
# 1. Fresh mirror clone
git clone --mirror https://github.com/webclinic017/digithings.git
cd digithings.git

# 2. Check the version. --sensitive-data-removal needs 2.47 or later.
git filter-repo --version

# 3. Drop the file from every commit that contains it
git filter-repo \
  --path apps/digithings-stack-cloudflare/container/seed/occ_tickets.jsonl \
  --invert-paths \
  --sensitive-data-removal

# 4. Push the rewritten history
git push --force --mirror origin
```

If step 2 reports a version below 2.47, stop and install a newer `git-filter-repo`
(`pip install git-filter-repo`, or `brew install git-filter-repo`) before continuing.

After step 4, **contact GitHub Support** with the repository name, the number of affected pull
requests, and the *First Changed Commit(s)* that step 3 prints. Support runs the garbage collection
that actually expunges the data from storage.

---

## Option B — GitHub issue body (fallback only)

Post as a new issue on [webclinic017/digithings](https://github.com/webclinic017/digithings/issues).
Title: `Request from the upstream owner: customer data in your fork history`

Keep it short. The long explanation belongs in the email.

---

Hello — I maintain digithings-ai/digithings, the repository your fork is derived from. I am the CTO
of that project and I am the person filing this.

We found a mistake on our side. A file of real customer support data was committed to our public
repository in commit `86cb1ec5d62b2422cf2c312b6d63722c86fb2000`, at:

    apps/digithings-stack-cloudflare/container/seed/occ_tickets.jsonl

It is visible at this permanent link in your fork:

    https://github.com/webclinic017/digithings/blob/86cb1ec5d62b2422cf2c312b6d63722c86fb2000/apps/digithings-stack-cloudflare/container/seed/occ_tickets.jsonl

It contains the names, email addresses, organisations and support correspondence of real people. It
should never have been public. We have already rewritten our own history to remove it and we are
notifying our data protection authority.

**Would you please either delete your fork, or rewrite your history to drop that file?** Deleting
the fork is the simplest route and we are happy with it — the code is MIT-licensed and you are
welcome to keep using all of it.

If you rewrite instead, note that this alone does not remove the data from GitHub's servers; you
will also need to ask GitHub Support to garbage-collect the repository, per
https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository
Command-line instructions are in this comment.

I would rather resolve this with you than have to go to GitHub. If we have not heard back in two
weeks we will have to take that step. If you would rather talk about it, contact me at
contact@digithings.ai — I will answer directly.

This is a request, not a legal notice. There is no copyright claim here and none is intended.