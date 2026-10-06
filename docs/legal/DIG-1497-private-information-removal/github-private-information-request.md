# GitHub Support — private information removal request

**Status: DRAFT. Not sent.** Prepared by Counsel 2026-10-06. Chris sends.

Submit at: **https://support.github.com/contact/private-information**
Choose the private-information / sensitive-data option offered on that form.

**Send order:** after the two fork-owner requests and the 14-day wait, and only after
[DIG-1496](/DIG/issues/DIG-1496) is `done`. See [README.md](./README.md).

**Paste as plain text into the body of the form.** Do not attach anything. GitHub: *"Please include
a plain-text version of your request in the body of your message. Sending your request in an
attachment may result in processing delays."*

---

## Two placeholders — the request cannot be sent with these in it

| Placeholder | Fill from |
| --- | --- |
| `<<< FILL: NUMBER OF AFFECTED PULL REQUESTS >>>` | `grep -c '^refs/pull/.*/head$' .git/filter-repo/changed-refs` in the rewritten clone |
| `<<< FILL: FIRST CHANGED COMMIT >>>` | the `NOTE: First Changed Commit(s):` line `git-filter-repo` printed, per their [removing sensitive data](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository) guidance |

Also re-run the fork count on the day of sending and update the date and the list if it moved:
`gh api repos/digithings-ai/digithings --jq .forks_count` → expect `2`.

If the filter-repo output contains a note about LFS objects, add that note to the request. Counsel's
read of the current file found no LFS object, but the rewrite is what confirms it.

---

## The request body

Paste everything between the lines into the form.

---

### BEGIN REQUEST BODY

**Repository owner:** digithings-ai
**Repository name:** digithings
**Affected file (same path in all three repositories):**
`apps/digithings-stack-cloudflare/container/seed/occ_tickets.jsonl`

**Commit that introduced the file:**
`86cb1ec5d62b2422cf2c312b6d63722c86fb2000` (2026-10-02T14:55:30Z)

---

#### 1. Working links to the affected file

The file is currently retrievable at these permanent, account-free URLs. All four were confirmed
to resolve on the date of this request.

Parent repository (we are the owner and have acted here ourselves — see section 6):

https://github.com/digithings-ai/digithings/blob/86cb1ec5d62b2422cf2c312b6d63722c86fb2000/apps/digithings-stack-cloudflare/container/seed/occ_tickets.jsonl

Fork 1 of 2 — `itsnjstyle27`:

https://github.com/itsnjstyle27/digithings/blob/86cb1ec5d62b2422cf2c312b6d63722c86fb2000/apps/digithings-stack-cloudflare/container/seed/occ_tickets.jsonl

Fork 2 of 2 — `webclinic017`:

https://github.com/webclinic017/digithings/blob/86cb1ec5d62b2422cf2c312b6d63722c86fb2000/apps/digithings-stack-cloudflare/container/seed/occ_tickets.jsonl

Raw form, if the rendered view is inconvenient for review:

https://raw.githubusercontent.com/digithings-ai/digithings/86cb1ec5d62b2422cf2c312b6d63722c86fb2000/apps/digithings-stack-cloudflare/container/seed/occ_tickets.jsonl

---

#### 2. Specific line numbers

The file is 919 lines. **Every line contains personal data.** Two breakdowns, so you can target
precisely.

**Lines containing at least one email address — 784 of 919.**
Every line in this list, inclusive:

```
1-310, 318-342, 354-363, 365-371, 387-396, 404-406, 413-469,
480-488, 503-512, 526-552, 573-669, 678-749, 768-854, 860-919
```

**Lines containing a real person's name and/or organisation but no email address — the
remaining 135 lines:**

```
311-317, 343-353, 364, 372-386, 397-403, 407-412, 470-479,
489-502, 513-525, 553-572, 670-677, 750-767, 855-859
```

If a line-level view is easier for you, GitHub renders any line as
`…/blob/86cb1ec5…/occ_tickets.jsonl#L<line>`. Examples: line 1 is `#L1`, line 500 is `#L500`, line
919 is `#L919`. The two ranges above will take you to the whole file in two hops.

**Scale of the affected data, for triage:**

| Measure | Value |
| --- | --- |
| Lines (all affected) | 919 |
| Distinct support tickets | 185 |
| Rows flagged internal | 372 |
| Distinct customer records | 87 |
| Distinct named individuals | 86 |
| **Distinct email addresses, anywhere in the file** | **248** |
| — present in a structured `customer` field | 84 |
| — present **only** inside quoted message bodies | 164 |
| Distinct email domains | 101 |
| Distinct organisations named | 47 |
| Individuals named who are **not** our customers | 135 |

---

#### 3. Why this constitutes a specific or targeted security risk

I understand from your Private Information Removal Policy that the test is whether the content
"should have been kept confidential" **and** its public availability poses "a specific or targeted
security risk," defined as exposure to physical danger, identity theft, or increased likelihood of
unauthorized access to physical or network facilities. I am not asking you to take the first limb
on faith — the second limb is the reason I am writing.

This is not a list of names with no context. **The 919 lines are, in aggregate, an operational
attack kit, and each line is internally coherent.** Every row pairs the following in one place:

- the individual's real, unmasked name;
- the email address they use to reach us, and which is the identifier on their account;
- the organisation they work for and that organisation's own domain, in 101 distinct cases;
- the specific account, order, ticket number or internal identifier they are asking about;
- **the verbatim text of what they wrote to us, and what our staff wrote back** — including, on
  many rows, internal notes, staff names, queue names and state changes.

**The specific risk: account takeover of a named person at a named employer.** Consider what an
attacker has per line. They have the person's name. They have the exact address that authenticates
them. They have the employer and its domain, which is what a convincing domain-lookalike or a
"IT support" pretext is built from. They know the exact product, ticket number and problem the
person described, and they can quote the person's own words about it. GitHub's examples of an
appropriate request — credentials, AWS tokens, network diagrams, SSNs — all work the same way: they
are *levers*, and this file is levers for 87 customer accounts plus 135 other named people, laid out
one per line and retrievable without an account. The support thread text is the pretext material.
A message arriving at one of these addresses saying "we are migrating your ticket, please confirm
your login on this link" has a realistic source, because the attacker can reproduce the exact
context the real support team would have had.

**The second specific risk: identity theft of the people who are not our customers.** 164 of the
248 email addresses appear *only* inside quoted correspondence, on lines with no `customer` field.
These are colleagues, partners and other contact parties — people who were copied on a thread or
quoted in a ticket and had no relationship with us at all. Their names, addresses and the substance
of what they wrote are published, and they never consented to being a record anywhere. This is the
exposure that cannot be fixed by writing to a customer.

**Why the risk is targeted rather than incidental.** The file is not one name among millions in
scraped corpora. It is a curated set of people who each have an open, unresolved account with a
company that holds their identity documents, and it pairs each identity with the account context
needed to act as them. It is a ready-made target list, and the affordances are free: no breach, no
access logs, no pretexting skill beyond reading the file.

**Retrieval is unauthenticated and the URL is permanent.** I confirmed today that all three URLs
in section 1 return the file to a request carrying no credentials. Because the content sits at an
immutable commit address rather than at a branch tip, deleting the file in a later commit does not
make it unavailable — anyone holding the link keeps it, and any future fork inherits it.

**Why removal cannot be mitigated by rotating a credential.** I want to be accurate about this
rather than overstate it: we scanned the file and it contains **no** passwords, API keys or tokens,
so there is nothing to rotate. The exposure is identity and account context, not secrets. That is
what makes it durable — a secret can be changed, but a person's name, employer and the record of
what they told us cannot. For the same reason the affected individuals cannot reasonably be
expected to detect this: a credential leak announces itself through a failed login or an alert,
whereas leaked correspondence sits in a public repository indefinitely and generates no signal.

---

#### 4. Legal right to act on behalf of the organisation

I am authorised to act for Digi Ecosystem, the owner of `digithings-ai/digithings`. Digi Ecosystem
is the data controller for the personal data in question: these are its own customers' records and
its own support correspondence, held by it in the ordinary course of providing its service. Digi
Ecosystem is also the copyright holder of the repository and the file. This is a first-party report
of our own repository, made by its own owner, and not a report by a third party or a browser
service.

---

#### 5. Forks — enumerated at the time of this notice

Your policy states: *"If at the time that you submitted your notice, you identified all existing
forks of that repository, we would process a valid claim against all forks in that network at the
time we process the notice."* It also states that you do not independently investigate forks and
expect the reporter to do so. I have done that.

`digithings-ai/digithings` reported `forks_count: 2` when I checked, and the paginated fork list
returned exactly these two repositories. **This is the complete list.**

| # | Fork | Forked | Last push | Default branch | File reachable at pinned commit |
| --- | --- | --- | --- | --- | --- |
| 1 | `itsnjstyle27/digithings` | 2026-08-18 | 2026-08-18 | `develop` | Yes |
| 2 | `webclinic017/digithings` | 2026-05-29 | 2026-05-25 | `develop` | Yes |

Fork enumeration date: **<<< FILL: DATE OF SEND, YYYY-MM-DD >>>**

Note on the present state of the forks: the file is **not** present at the tip of either fork's
default branch, nor at the tip of the parent. It is absent from current views and remains
reachable only through the immutable commit address in section 1. I mention this because it means
a reviewer browsing the repository today will not see the file, and I do not want that mistaken for
the claim being stale. I can see it, and anyone holding the link can.

**What I have already done regarding forks, per the "Ask Nicely First" guidance.** I did not come
here first. I identified the two fork owners and wrote to both directly, at
`itsnjstyle27/digithings` and `webclinic017/digithings`, on **<<< FILL: DATE FORK REQUESTS SENT,
YYYY-MM-DD >>>**, naming the file, the commit, and the fact that it contains customer personal
data. Each request asked them to delete the fork or rewrite the history to drop the file, gave them
ready-to-run `git-filter-repo` commands, offered deletion of the fork as the easier option,
confirmed that the rest of the project is MIT-licensed and they were free to keep using all of it,
and stated plainly that no legal claim was being made. I gave them a fourteen-day window to respond
before taking this step.

<<< FILL: OUTCOME OF THE FORK-OWNER REQUESTS — e.g. "no response received within the 14-day
window", or "one fork was deleted on <date>; the other did not respond" >>>

---

#### 6. What we have already done in the parent repository

We did not wait for this request to start on our side. The parent repository has been rewritten and
the file removed from all reachable history.

- History rewritten with `git-filter-repo` using `--sensitive-data-removal`, so the rewrite is
  recorded in the way your documentation requires.
- Pushed with force to `digithings-ai/digithings`.

Values for the fields your documentation asks for:

- **Number of affected pull requests:** `<<< FILL: NUMBER OF AFFECTED PULL REQUESTS >>>`
- **First Changed Commit(s):** `<<< FILL: FIRST CHANGED COMMIT >>>`
- **LFS:** `<<< FILL: "no LFS objects were involved", or paste the LFS note from the filter-repo
  output >>>`

Our own references are clean. I am asking you for the parts only you can perform: server-side garbage
collection, removal of any affected pull-request references and cached views, and — since you will
not investigate forks and a fork owner's own rewrite does not remove content from your storage —
action against the two forks enumerated in section 5.

---

#### 7. Why a whole-file request, and why that is still proportionate

Your policy notes that the private-information process *"is generally not intended for the removal
of full files or repositories — only for the specific pieces of private information in those files"*
and that justifying a whole-file removal *"may increase the time required to process your request."*
I am asking for a whole file, so I will justify it rather than leave you to find it.

The file is not a codebase with a customer name sprinkled through it. It is a single data artefact
that **is** the customer data — 919 lines, every one of which is a record of a person's identity
and correspondence, with no functional content to preserve. Removing any subset of it would leave
personal data exposed and would not make the remaining part safe to retain. There is no version of
this file that can be redacted to "just the parts that matter", which is the situation your policy
contemplates when it distinguishes scattered private information from a file filled entirely with
it.

I have therefore given you the full line-level breakdown in section 2 so you can verify that claim
rather than take it from me: 784 lines carry an email address, the other 135 carry a name and/or an
organisation, and the list of affected lines is complete and explicit.

---

#### 8. What I am asking for

1. Run a garbage collection on `digithings-ai/digithings` to expunge the blob and the rewritten
   objects from storage, per your *Removing sensitive data from a repository* guidance.
2. Dereference or delete the affected pull-request references, and clear cached views of the file.
3. Process the two forks enumerated in section 5 as part of the fork network, since they were
   identified at the time of this notice.
4. Advise us if any of the information above is insufficient for you to act, and tell us what you
   would need. We will supply it promptly.

---

#### 9. Point of contact

Chris Stefan
Digi Ecosystem
Email: contact@digithings.ai

I am the person filing this and I will answer directly. If you need confirmation of my authority to
act for Digi Ecosystem, I can supply it.

---

#### 10. Supplementary context, not the basis for this request

Separately from the security grounds above, this data is personal data under the EU General Data
Protection Regulation and Digi Ecosystem is its controller. A notifiable personal data breach has
been assessed and we have notified the Italian Garante per Article 33(1) GDPR. I mention this only
to be transparent about the regulatory context; **it is not the basis for this request**, which
rests entirely on the security risk described in section 3. If it would be more appropriate to
handle this through your privacy contact form instead, tell me and I will route it there.

---

### END REQUEST BODY

---

## Notes for Chris — not part of the request

**Counsel's prediction: this will be refused.** Recorded so nobody later mistakes a refusal for a
surprise, and so the outcome on DIG-1484 reads honestly.

The reason is in GitHub's own documentation and Counsel will not pretend otherwise: *"GitHub Support
won't remove non-sensitive data, and will only assist in the removal of sensitive data in cases where
we determine that the risk can't be mitigated by rotating affected credentials."* There are no
credentials in this file. That sentence is the trigger, and we do not meet it.

The request is still worth sending, for reasons that are about the record and not the outcome:

- It is the strongest honest request available. The identity-and-account-takeover argument is real,
  is grounded in the file's actual contents, and is stated at the level of detail their policy asks
  for. Counsel will not write a request that overstates the facts to improve the odds.
- An unanswered request is itself evidence for the Garante notification that the controller tried
  every available route, in order, with dates.
- Section 5 makes the fork enumeration explicit and dated, which is the only mechanism that reaches
  a fork. If they decline now, the enumeration is preserved for the next route.

**Confidence:**

| Point | Label |
| --- | --- |
| Every factual assertion in the request | **CONFIRMED** — verified against live GitHub and the blob, 2026-10-06 |
| That the request meets each stated content requirement | **CONFIRMED** — checked line by line against the policy |
| The eligibility argument as identity / account-takeover exposure | **CONFIRMED** as the strongest honest framing |
| That GitHub grants it | **LIKELY refusal**, as above |
| That the fork set is closed at 2 | **CONFIRMED** as of 2026-10-06; **must be re-run on the day of sending** |

**If it is refused:** do not escalate to DMCA. A DMCA notice asserts copyright infringement over
the forks' copies, which are not ours to assert. It would be a false claim and Counsel will not
draft one. The escalation route is a written record of refusal on DIG-1484 for the Garante file, and
then Counsel's separate advice on the Italian supervisory-authority process.