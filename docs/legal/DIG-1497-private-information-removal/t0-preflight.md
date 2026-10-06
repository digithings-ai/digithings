# t0 pre-flight — GitHub private-information request

**Status: working notes, not part of the request.** Prepared by Counsel 2026-10-06 for
[DIG-1529](/DIG/issues/DIG-1529). Nothing here goes into the form body.

The request itself is [github-private-information-request.md](./github-private-information-request.md).
Its five placeholders cannot be filled until [DIG-1496](/DIG/issues/DIG-1496) lands. This file holds
everything that is **already knowable**, so that the t0 pass is mechanical instead of researched
under time pressure.

---

## 1. Baseline, verified 2026-10-06 (t−1)

Checked directly. Not derived from anything.

| Check | Command | Result |
| --- | --- | --- |
| Fork count | `gh api repos/digithings-ai/digithings --jq .forks_count` | **2** |
| Fork list | `gh api repos/digithings-ai/digithings/forks --paginate` | `itsnjstyle27`, `webclinic017` — no third fork |
| `main` tip | `gh api repos/digithings-ai/digithings/commits/main --jq .sha` | `da88fa715e32a737572950ec46d0c0d6096614ac` — **unchanged, nothing pushed** |
| Blob at pinned commit, ours | `curl -r 0-0 …/digithings-ai/digithings/86cb1ec5d…` | **206** |
| Blob at pinned commit, `itsnjstyle27` | same, fork path | **206** |
| Blob at pinned commit, `webclinic017` | same, fork path | **206** |

**The section 5 enumeration is confirmed accurate as written.** Both fork rows — creation dates
2026-08-18 and 2026-05-29, last pushes 2026-08-18 and 2026-05-25, default branch `develop` — match
the live API. The only edit section 5 needs at t0 is the enumeration date.

**The trigger has not fired.** `main` is still `da88fa715e32…`, which is the pre-rewrite tip named in
DIG-1496 §7.

---

## 2. The two DIG-1496 values, and the figure to send

From DevOps' plan comment on DIG-1496 (2026-10-06T19:41Z), §7. Recorded verbatim.

**First Changed Commit(s)** — three SHAs, as `filter-repo` printed them:

```
e34a8c8566b662e322b8432649600a72cfc2fa85
f53566cefaaaa74348646a905717f3be1e75ece9
c503c739c77bb65e1727fb502f3f8b87c1457a87
```

With their replacements, for our own record only:

| Old (First Changed Commit) | New | Date | Subject |
| --- | --- | --- | --- |
| `e34a8c8566b662e322b8432649600a72cfc2fa85` | `f7172a7856233b0185daf02afcdccf8812bdb623` | 2026-03-12 | Fix typo in project name in README |
| `f53566cefaaaa74348646a905717f3be1e75ece9` | `3ee52971099bf5ed310670a3d567040d3c68cce5` | 2026-04-18 | Merge pull request #35 from digithings-ai/task/34-phase-0-setup |
| `c503c739c77bb65e1727fb502f3f8b87c1457a87` | `2937f565949b37ebc6e13bc1a8f910b0559baa69` | 2026-04-18 | feat(ci): gitleaks secrets-scan workflow (#68) |

**None of these is `86cb1ec5d`, and that is correct.** `86cb1ec5d` is where the sensitive *content*
arrived. These three are where the *path* first existed, which is what GitHub's field asks for. Send
the three old SHAs. Do not send `86cb1ec5d` in this field, and do not add a fourth line.

**Number of affected pull requests: 3,389.**

> **Reconciliation, so nobody re-opens this.** The same DIG-1496 §7 also reports `refs/pull` census
> **3,483**. That is not a contradiction and not a second candidate figure. 3,483 is every `refs/pull`
> ref rewritten; **3,389 is the subset matching `^refs/pull/.*/head$`**, which is what
> `grep -c '^refs/pull/.*/head$' .git/filter-repo/changed-refs` counts and what the form field asks
> for. The remaining **94** are `refs/pull/N/merge` refs, which correspond one-for-one with the 94 open
> PRs. **Send 3,389.** Confidence **CONFIRMED** — the arithmetic closes: 3,389 + 94 = 3,483.

**Re-derive at t0 anyway.** One command, from the rewritten clone:

```
grep -c '^refs/pull/.*/head$' .git/filter-repo/changed-refs
```

If it does not print `3389`, the plan changed after 19:41Z and the plan's value is stale. Use the
command's output, never the plan's number. Same rule for the three SHAs: read them from
`.git/filter-repo/first-changed-commits`, not from this file.

---

## 3. The t0 fill operations, in order

Against `github-private-information-request.md`.

1. **§5 fork enumeration date** — line 201.
   `<<< FILL: DATE OF SEND, YYYY-MM-DD >>>` → the date Chris submits the form. Same date as §1's
   re-check, so the enumeration and the date cannot disagree.
2. **§6 affected-PR count** — line 272.
   `<<< FILL: NUMBER OF AFFECTED PULL REQUESTS >>>` → `3,389`
3. **§6 First Changed Commit(s)** — line 273.
   `<<< FILL: FIRST CHANGED COMMIT >>>` → the three SHAs, as a list.
4. **§6 LFS** — line 274.
   `<<< FILL: "no LFS objects were involved", or paste the LFS note … >>>` → take the filter-repo
   output's own LFS line. If it printed none, the substitute text is exactly:
   `no LFS objects were involved`
5. **Delete the drafting-note box** at the top of §6. It is fenced with `> **⚠ DRAFTING NOTE` and is
   not part of the request. It is not deletable before t0, because it is what stops the request being
   sent early.
6. **Apply the §6 amendment in §5 of this file**, once Chris approves it. See §5 below — this is the
   one step that is *not* a mechanical substitution.
7. **Placeholder table at the top of the file** (lines 22–23) — delete the whole
   "Two placeholders" section. It is scaffolding for Counsel, and it is above the `BEGIN REQUEST
   BODY` fence. Leaving it in would put a drafting note in front of the form.

**Then grep, and expect zero hits:**

```
grep -n 'FILL\|DRAFTING NOTE\|BEGIN REQUEST BODY\|END REQUEST BODY' github-private-information-request.md
```

Anything left is a defect. Then hand the text to Chris. **Counsel does not send.**

---

## 4. Contingency: what if the pinned commit is already 404 at t0?

DIG-1529 step 5 says: verify the file is still retrievable; if it is not, do not file. That rule was
written before DIG-1496 §6 established that **206 is the expected result at t0** — see §5. So a 404 at
t0 means something other than our own push happened: a natural GC, or GitHub Support already
dereferenced the PR refs.

In that case **do not send this text.** Section 6 would assert a removal that Support performed, and
it would ask them to do work they had already done. Write a short confirmation notice instead:

- state that the data is no longer retrievable, with the timestamp and the 404 you observed;
- ask only for **confirmation that the garbage collection ran** and that **cached views were
  cleared**, because a 404 on `raw.githubusercontent.com` proves reachability loss, not storage
  expiry;
- keep section 10's GDPR paragraph, because the supervisory-authority clock does not stop.

Log which branch was taken on DIG-1484 either way.

---

## 5. §6 amendment — required before sending, pending Chris's approval

**DRAFT. Not applied to the request.** DIG-1497 was human-approved on 2026-10-06. Section 6 is
approved text, so Counsel cannot change it alone.

### Why the amendment is necessary

DIG-1496 §6, posted 19:41Z — after the approval — establishes that **our push alone will not produce
the 404**:

> Nine merged-PR refs hold the blob. GitHub owns `refs/pull/*`, marks them read-only, and refuses our
> force-push. **After our push, the raw range request against `86cb1ec5d` will still return 206**,
> because the old commit is still reachable through those 9 PR refs.

Against that, section 6 of the request opens:

> We did not wait for this request to start on our side. The parent repository has been rewritten and
> **the file removed from all reachable history.**

**That sentence will be false at t0, and it is demonstrably false, not arguably false** — the blob
returns 206. The section contradicts itself three paragraphs later, where it correctly says only
*"Our own references are clean."*

The overstatement is not cosmetic. This is the assertion that establishes GitHub's stated
precondition — *"if you have successfully cleaned up all references other than PRs"* — for the
server-side work this request exists to obtain. Asserting more cleanup than we performed invites
Support to treat the precondition as unmet, and it is precisely the kind of unverified remediation
claim that Art. 33(1) §6 record-keeping exists to catch. The defensible position is to state the
narrow claim, which is true and sufficient.

**Confidence LIKELY that the amended wording is accurate at t0**, conditional on DevOps' §6 finding
holding. It becomes CONFIRMED on the t0 range request, which will show 206 either way.

### Draft replacement for the opening of §6

Replace:

> We did not wait for this request to start on our side. The parent repository has been rewritten and
> the file removed from all reachable history.
>
> - History rewritten with `git-filter-repo` using `--sensitive-data-removal`, so the rewrite is
>   recorded in the way your documentation requires.
> - Pushed with force to `digithings-ai/digithings`.

With:

> We did not wait for this request to start on our side. On **<<< FILL: DATE OF REWRITE PUSH, YYYY-MM-DD >>>**
> we rewrote the parent repository's history and force-pushed our own references.
>
> - History rewritten with `git-filter-repo` using `--sensitive-data-removal`, so the rewrite is
>   recorded in the way your documentation requires.
> - Pushed with force to `digithings-ai/digithings`.
> - **Every reference we control is clean.** No branch, tag, or backup reference in
>   `digithings-ai/digithings` reaches `86cb1ec5d` any more.
>
> I want to be precise about the edge of that statement, because your documentation turns on it. **The
> old commit is still reachable through pull request references that your platform owns and that we
> cannot modify.** `refs/pull/*` is read-only to us, so our mirror push could not reach them. I
> checked this rather than assuming it: a one-byte range request against the pinned commit returns
> **206, not 404**. The file is still retrievable, and I am not claiming otherwise.
>
> <<< FILL: THE PULL REQUEST REFERENCES THAT STILL HOLD 86cb1ec5d >>>

### Second, smaller edit

The sentence *"Our own references are clean, which is the precondition your documentation sets for the
server-side work"* is **correct and stays.** It is the right claim. The paragraph after it, asking for
the three server-side steps, also stays unchanged — the request still needs all three, and section 6
now explains why.

### New input needed from DevOps at t0

`<<< FILL: THE PULL REQUEST REFERENCES THAT STILL HOLD 86cb1ec5d >>>` — the names of the pull request
refs that hold the commit, from `.git/filter-repo/changed-refs` filtered to those still resolving after
the push. Naming them is what lets Support dereference exactly those, and it is the difference
between a ticket they have to investigate and one they can action. **Requested from DevOps on
DIG-1496, 2026-10-06.**

---

## 6. Out of scope, closed

- **Cloudflare.** Per the Security cross-check on this issue (2026-10-06T21:02Z): the ~83
  payload-carrying images sit in Cloudflare's account-integrated registry, ref shape
  `registry.cloudflare.com/<ACCOUNT_ID>/<IMAGE>:<TAG>`, with no public pull URL and no public exposure
  path. **No registry takedown is required and none is requested here.** Registry access was never a
  disclosure vector. Deleting the old stack images is housekeeping for DIG-1611 and needs Chris's
  account access. `shared-v16` was a Durable Object id, not a registry tag, and has no bearing on any
  placeholder.
- **The two fork owners.** Not contacted, by Chris's decision of 2026-10-06. Section 5 already
  discloses that truthfully. Do not add anything to section 5 about contacting them.
- **DMCA.** Not claimed. It asserts copyright over third-party forks.
- **Figure 286.** Retracted. The correct figures are 87 customer records and 248 email addresses, and
  they are what the request already uses.

---

## 7. Boundaries

**Counsel does not send.** No agent in this company can: the Gmail connection is read-and-draft only,
and the GitHub MCP has no abuse or takedown tool. The text goes to Chris at
https://support.github.com/contact/private-information, plain text in the body of the form, no
attachment. Chris's approval covers the text, not the sending, and the approval of 2026-10-06 predates
the §6 amendment in §5 above.

**Prediction, unchanged: LIKELY (refusal).** The file holds no credentials, so GitHub's own trigger —
that the risk cannot be mitigated by rotating them — is not literally met. The §6 amendment does not
change that, and is not intended to: it makes us more accurate, not more likely to win. It is still
worth filing, because the fork enumeration is the only mechanism that reaches the fork network and the
record matters for Art. 33(1) §6 whatever the outcome.
