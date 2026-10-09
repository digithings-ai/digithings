# Code review — PR #5167 `docs/digichat-datatap-aca-runbook`

| | |
|---|---|
| **Reviewer** | fresh-context review subagent (`code-reviewer`); did not author this diff |
| **Subject** | PR #5167, commit `abad44485`, base `develop` = `a0e8f6075` |
| **Head** | `docs/digichat-datatap-aca-runbook` |
| **Verdict** | **changes-requested** |
| **Critical** | 0 |
| **Major** | 3 |
| **Minor** | 5 |
| **Nit** | 2 |
| **Method** | tiered in-session pass (`docs/agents/CODE_REVIEW_POLICY.md` § Refute): read the diff, then exercised `check()` on 26 hand-built fact payloads, mutation-tested the checker against its own test file, and refuted every finding with a command + observed output |

Repo state observed: `18 passed` (`tests/scripts/test_check_digichat_image_binding.py`), `ruff check` + `ruff format --check` clean, `make doc-check` OK (468 files). The worktree was not modified; mutation testing ran on a throwaway copy outside it.

---

## Findings

### M1 — MAJOR — the GHCR correction covers 2 of ~13 places, and the two fixed files now point the reader straight at the eleven unfixed ones

**`apps/digichat/OPERATIONS.md:9-10` · `docs/architecture/digichat-self-hosted-release.md:41,49`**

The PR fixes two stale docs. `git grep -nE "ghcr\.io/digithings-ai/digichat"` on `HEAD` still finds the same false claim in:

| File:line | Claim |
|---|---|
| `docs/digichat/INSTALL.md:29` | `docker pull ghcr.io/digithings-ai/digichat:v2.3.2` — the **operator install command** |
| `docs/digichat/INSTALL.md:35`, `:249` | `GHCR image \| ghcr.io/digithings-ai/digichat:vX.Y.Z` |
| `docs/digichat/RELEASE-SMOKE.md:11,23,24,36` | `docker pull` / `docker run` checklist against GHCR |
| `docs/digichat/RELEASE-SMOKE.md:16` | "`v0.9.3` remains on GHCR for existing clients" (the claim the PR *removed* from the architecture doc, still present in two other copies) |
| `RELEASES.md:80` | "promote publishes `ghcr.io/digithings-ai/digichat:v1.0.0`" |
| `RELEASES.md:82` | "Do not delete `…/digichat:v0.9.3`" |
| `docs/agents/CI_CONVENTIONS.md:39` | `publish-digichat-image.yml` listed with status **Working** — the file does not exist (`ls .github/workflows/publish-digichat-image.yml` → `No such file or directory`) |
| `apps/digithings-web/lib/sharedDocs.ts:99` | public site copy: "digichat itself is already on GHCR" |
| `apps/digithings-web/lib/sharedDocs.ts:140,146` | `docker pull ghcr.io/…:v2.3.2`; "(currently published through `v2.3.2`)" |
| `apps/digithings-web/lib/apiDocs.ts:643` | public site copy: `make up-ghcr-digichat pulls ghcr.io/…` |
| `infra/digichat-release/compose.digichat-release.yml:18` | `image: ghcr.io/digithings-ai/digichat:v${DIGICHAT_VERSION}` — wired to `Makefile:19` `up-ghcr-digichat`, so `make up-ghcr-digichat` pulls an image that cannot resolve |
| `docs/architecture/digichat-self-hosted-release.md:49` | **same file the PR edited**: "**Primary install unit:** pinned GHCR image" under § *Target (what we want operators / clients to use)* — 8 lines below the corrected `:41` |

The self-defeating part is local: `apps/digichat/OPERATIONS.md` now says "**No published image registry exists today**" at `:9` and then links `docs/digichat/RELEASE-SMOKE.md` (`:11`) and `docs/digichat/INSTALL.md` (`:12`), whose very next instruction is `docker pull ghcr.io/digithings-ai/digichat:v2.3.2`. An operator following the corrected doc one bullet down is back at a 401.

**Verdict: CONFIRMED defect.** `AGENTS.md` § Review coverage cites "it shipped two false public claims to production" as the reason to gate on claims rather than diff size; the public marketing copy at `sharedDocs.ts` / `apiDocs.ts` is that same class and is untouched. Scope note: fixing all thirteen is larger than this PR, but the PR should at minimum either fix them or name them as an explicit follow-up issue — silently fixing 2 of 13 leaves the repo in a state that is *harder* to reason about than before, because the two fixed docs now assert the opposite of their eleven neighbours.

---

### M2 — MAJOR — the correction introduces a new false claim: the GHCR→ACR mirror step did exist

**`docs/architecture/digichat-self-hosted-release.md:45`**

> **No GHCR→ACR mirror step exists** — that was a planned shape, not an implemented one.

The deleted workflow's own header, recoverable at the path the runbook itself gives (`git show f54af7052^:.github/workflows/publish-digichat-image.yml`), says the opposite:

```
#     does — downstream consumers (datatap-web's deploy-digichat-container.yml
#     imports ghcr.io/digithings-ai/digichat:<version> into ACR) can deploy any
#     released version.
```

So the mirror step was implemented — client-side, in `datatap-web`, which the same table row already calls "Client-side (out of repo)". The row it replaced said "a **manual** client ops step (documented in phase plans, not a digithings workflow)", which was *stale but true*. The new wording converts a stale truth into a claim that the step never existed. That also changes the remediation reading: if `datatap-web`'s import workflow still exists, it is a dead workflow pointing at a deleted publisher, which is a live operational fact worth recording rather than denying.

**Verdict: CONFIRMED as contradicted by the repo's own recoverable history** (`git show f54af7052^:…`, quoted above). **Unverified:** whether `datatap-web/deploy-digichat-container.yml` still exists or still runs — it is out of this repo and I have no access. Safe wording: "the mirror step lived in `datatap-web`'s `deploy-digichat-container.yml`, out of repo; its current status is unverified."

---

### M3 — MAJOR — the checker's only documented way to produce facts cannot work, and the runbook documents none

**`scripts/check_digichat_image_binding.py:22-25, 43-45` · `docs/ops/digichat-datatap-aca.md`**

The module docstring asserts a recipe exists and points at it:

```
# The checker is pure. … A caller collects the facts (there is a documented
# recipe in ``docs/ops/digichat-datatap-aca.md``) and pipes them in.
…
    # from the real world (recipe in docs/ops/digichat-datatap-aca.md)
    az acr repository show-tags ... ; docker inspect ... \
      | python3 scripts/check_digichat_image_binding.py --facts -
```

Three separate problems, all verified:

1. **The runbook has no recipe.** `grep -c "docker inspect\|az acr repository show\|image_revision\|image_digest" docs/ops/digichat-datatap-aca.md` → `2` (the two `--facts facts.json` mentions at `:78` and `:201`). Nothing in it ever says how to obtain `image_revision` or `image_digest`. The docstring's cross-reference is dangling.
2. **`;` means the pipe only carries the second command.** `az acr repository show-tags` never emits labels — `show-tags` returns `name`/`digest`/`createdTime`/`tagDetails` — so it cannot supply `image_revision` either way.
3. **`docker inspect` emits a JSON array, not the facts object.** Reproduced:

```
$ echo '[{"Id":"sha256:c570…","RepoTags":["…/digichat:v2.3.2"],"Config":{"Labels":{"org.opencontainers.image.revision":"14639ac0…"}}}]' \
    | python3 scripts/check_digichat_image_binding.py --facts -
error: could not read facts: facts must be a JSON object
exit=2
```

The shape is wrong, and even a corrected shape would need the `.Config.Labels` sub-object flattened plus `image_ref` / `package_version` / `tag` / `tag_commit` added by hand — i.e. facts assembled by an operator typing a sha into a JSON file, at which point exit 0 proves nothing about the image.

This matters more than a doc typo: the checker is deliberately not wired to CI (accepted limitation), so this recipe is the **only** consumer path. As shipped, the gate is unreachable and, if hand-assembled, trivially forgeable.

**Verdict: CONFIRMED defect** (reproduced, exit 2). Fix: give the runbook a real recipe (e.g. `crane config <ref> | jq .config.Labels` or `skopeo inspect --config`) and have it emit the exact seven keys `check()` reads, with `--format`/`jq` that produce a flat object. Also note §4 Step 1 needs the label of a *remote* digest, which `docker inspect` cannot do without a local `docker pull`.

---

### m4 — MINOR — the rehearsal gate names a commit that does not exist, and §2's recipe is pinned to 2.3.2

**`docs/ops/digichat-datatap-aca.md:87` · `:171`**

```
:87   TAG=digichat-v2.3.2
:171  > Rehearsal gate: … an image exists in the ACR whose
       org.opencontainers.image.revision is the 2.4.0 release commit.
```

There is no 2.4.0 release commit:

```
$ git tag -l 'digichat-v*' | sort -V | tail -3
digichat-v2.3.0
digichat-v2.3.1
digichat-v2.3.2
```

`check()` requires a tag matching `^digichat-v\d+\.\d+\.\d+$` plus a `tag_commit` (`scripts/check_digichat_image_binding.py:64, 141-147`), so a 2.4.0 image has nothing to bind to until release-please cuts the tag. An operator who runs the `:87` recipe against a 2.4.0 image gets `tag digichat-v2.3.2 names version 2.3.2, but the image reports version 2.4.0` — a false FAIL that looks like drift.

**Verdict: CONFIRMED.** False FAIL, not a false PASS, so this is an annoyance rather than a production risk. The gate needs to say "blocked until release-please cuts `digichat-v2.4.0`", and the recipe should take `TAG` as a parameter.

---

### m5 — MINOR — `image_digest` is optional and the runbook's gate reads as if it is not

**`scripts/check_digichat_image_binding.py:170-171` · `docs/ops/digichat-datatap-aca.md:200-201`**

```
:200-201  - [ ] binding check passes for the exact digest being promoted:
                python3 scripts/check_digichat_image_binding.py --facts facts.json → exit 0;
```

A payload with no digest at all returns exit 0:

```
$ … {"image_digest": null} …
PASS | no digest | probs=[] | unknown=['no image digest supplied; binding checked, immutability not']
```

Nothing in `check()` relates `image_ref` or `image_digest` to the revision it validated — the facts are taken on trust by design (accepted). But the runbook's prerequisite sentence reads as though the check covers the digest being promoted, which it does not: a facts file assembled for image A validates image A's *inputs*, and `--image …@$DIGEST` promotes whatever `$DIGEST` is. The note the checker prints is the right safeguard; the runbook prose discards it.

**Verdict: CONFIRMED** as a runbook-overstates-the-gate defect. The checker behaviour is documented and correct; either reword the prerequisite to "binding check passes for the facts collected **from that digest** (record them alongside it)" or require `image_digest` on the promoted path.

---

### m6 — MINOR — the runbook contradicts itself on `embed-tenants`, and misquotes the field name

**`docs/ops/digichat-datatap-aca.md:124` vs `:138`**

```
:124  | initDigichatConfigAtStartup | fails closed — … | none — `embed-tenants` is set via `secretRef` |
:138  Both ACAs declare exactly two secrets … and **both are inline-valued** (`secretRef: null`).
```

`secretRef` set vs `secretRef: null` are opposites, 14 lines apart, in the same document. This is load-bearing: §4's entire `--secrets` footgun argument ("cannot be round-tripped", "must be re-supplied out of band") is built on the inline-value reading, and the *risk* row in §3 is built on the `secretRef` reading. An operator who believes `:124` will expect a Key Vault secret to inspect and will not look for the inline value.

Additionally `:138` says `az containerapp show` "returns no usable value, only `hasValue:false`", but Step 0's `jq` projects `.properties.template.secrets[].secretRef` (`:155`), which is `null` for an inline secret. `hasValue` is a field of `az containerapp secret show`, not of `show`.

**Verdict: CONFIRMED as an internal contradiction** (both lines in the diff, quoted above). **Unverified:** the actual ACA state — I have no Azure access, so I cannot say which of the two lines is true. Given `:138` explains the redaction behaviour in detail, `secretRef` (`:124`) is the likely error.

---

### m7 — MINOR — the Dockerfile guard test cannot detect the label landing on the wrong stage, or not existing

**`tests/scripts/test_check_digichat_image_binding.py:222-227`**

```python
text = _DOCKERFILE.read_text()
assert "org.opencontainers.image.revision" in text
assert "ARG DIGICHAT_REVISION" in text
```

Two mutants, both run against the PR's own test file on a copy outside the worktree:

| Mutant | Result |
|---|---|
| move the whole `ARG DIGICHAT_REVISION` / `ARG DIGICHAT_SOURCE_URL` / `LABEL` block from the `runner` stage into the `builder` stage | **18 passed** |
| comment out every line of the block, keeping the two literal strings | **18 passed** |

So the test pins that two substrings occur *somewhere* in the file, not that the label is on the final image.

**The production code itself is correct** — I checked by reading: `apps/digichat/Dockerfile:36` opens the final `runner` stage, `:55` and `:63-64` declare `DIGICHAT_VERSION` / `DIGICHAT_REVISION` / `DIGICHAT_SOURCE_URL` inside it, and `:65-67` is the `LABEL`, so all three variables are in scope and the annotation lands on the shipped image. No secret is exposed: the two new `ARG`s are a sha and a public URL, and `test_dockerfile_does_not_bake_embed_tenants` (`:229-237`) already guards the one value that would have been a problem. Build-verification is an accepted limitation and is not re-reported here.

**Verdict: CONFIRMED test-quality defect, not a code defect.** A cheap fix: assert the `LABEL` appears after the last `FROM` line, e.g. `assert text.rindex("org.opencontainers.image.revision") > text.rindex("FROM ")`.

---

### m8 — MINOR — five `check()` branches have no test; two tests pass for the wrong reason

**`tests/scripts/test_check_digichat_image_binding.py` · `scripts/check_digichat_image_binding.py`**

Mutation results (all mutants run against the PR's own test file; "survived" = the test suite cannot see the change):

| Mutant | Suite |
|---|---|
| delete `unknown.append("no image digest supplied; …")` (`:170-171`) | **18 passed — survived** |
| delete `problems.append(f"missing required fact: {name}")` (`:114-116`) | **18 passed — survived** |
| delete the bad-tag-regex branch (`:121-122`) | **18 passed — survived** |
| delete the `tag_commit … is not a commit sha` branch (`:146-147`) | **18 passed — survived** |
| delete `elif not SHA_RE.match(image_revision.lower())` (`:156-157`) | **18 passed — survived** |
| `_clean`: return `"x"` instead of `None` for an empty string (`:93`) | **18 passed — survived** |
| remove the `_sha_eq(...)` equality comparison (`:161`) | 2 failed — **killed** |
| remove the tag-version comparison (`:125`) | 1 failed — killed |
| remove the version-vs-`package.json` comparison (`:131`) | 2 failed — killed |

Read together:

- **`REQUIRED_FACTS` is never exercised.** No test omits `version`, `package_version`, `tag` or `image_ref` — including the empty-facts case. `image_ref` in particular is required and unasserted, so a future refactor dropping it from the tuple would be invisible.
- **The `unknown` list is never asserted anywhere.** The whole "a weaker check ran, say so" mechanism the docstring sells (`:26-27`) can be deleted without a single test failing.
- **Two tests pass for the wrong reason.** `test_empty_revision_annotation_fails` (`:115-119`) asserts only `ok is False`; with `_clean` returning a non-empty sentinel for `""` it still passes, because the failure then comes from the *shape* branch, not the missing-annotation branch its docstring claims to pin. `test_malformed_revision_fails` (`:148-151`) likewise still passes with the shape branch deleted. Both should assert the message, as their neighbours already do (`assert any("org.opencontainers.image.revision" in p …)` at `:112`).

**Verdict: CONFIRMED.** The suite's real strength is the equality comparison; the branches the module docstring explicitly calls out as the point of the script ("fail closed on missing facts") are the untested ones. Note this is a coverage gap, not a verdict bug — I could not construct an input that makes `check()` return the wrong `ok` (see below).

---

### m9 — NIT — `_sha_eq`'s length guard is dead code

**`scripts/check_digichat_image_binding.py:95-98`**

```python
width = min(len(a), len(b))
return width >= 7 and a[:width].lower() == b[:width].lower()
```

Both call sites (`:160-161`) already gate on `SHA_RE = ^[0-9a-f]{7,40}$`, so `width` can never be `< 7` there; removing the guard entirely leaves 18/18 green. Related: the `{7,40}` cap would reject a 64-char revision if this repo ever moves to git's sha256 object format — a future false FAIL, not a false PASS. Suggest deleting the guard, or (better) moving the abbreviation policy in one place.

**Verdict: confirmed, non-blocking.** Abbreviated-sha matching itself is correct — I checked the direction that matters: `image_revision` shorter than `tag_commit` matches on the shorter width (correct), `tag_commit` shorter than `image_revision` matches likewise, case differences match (`.lower()`), and a 6-char revision is rejected. A crafted 7-char revision that merely *looks* like a prefix of a different commit fails.

---

### m10 — NIT — rollback revision number is right only in one reading

**`docs/ops/digichat-datatap-aca.md:234` vs `:28`/`:103`**

```
:28    | prod revision | digichat--0000007, created 2026-09-21, still the only revision |
:234   This mints a further revision (digichat--0000009) rather than reactivating --0000007.
```

Prod has exactly one revision, so the *next* promote mints `--0000008`. `--0000009` is correct only if read strictly in Step 2 → Step 3 order (promote = `--0000008`, rollback = `--0000009`). Since Step 3 is written to stand alone, say which it assumes.

**Verdict: confirmed ambiguous, non-blocking.**

---

## Verified vs not verified

**Verified against the repo**

- `digichat-v2.3.2` → `14639ac0ca9947beeb62d6b1971ebd69e3554be1`, `chore(digichat): release 2.3.2 (#4464)`, 2026-09-21 — matches the runbook `:70` and the test's `V232_COMMIT`.
- Drift is exactly **67** commits: `git rev-list --count digichat-v2.3.2..origin/develop -- apps/digichat` → `67`. (Whole-tree count is 761; the runbook scopes it to `apps/digichat`, correctly.)
- `develop` `package.json` version `2.4.0`; `digichat-v2.3.2:apps/digichat/package.json` version `2.3.2` — the §2 caller pitfall is real and correctly diagnosed.
- `f54af7052` = `chore(gha): strict-essentials cut + pause CF→disabled traps (#4919)`, 2026-10-01; `git show f54af7052^:.github/workflows/publish-digichat-image.yml` resolves; the workflow is absent from `HEAD`; `git grep -E 'eastus2|containerApps|jollygrass' origin/develop` → exit 1, **0 hits**, as claimed at `:54`.
- `healthz` route added by `916c4b5d5` (2026-09-28) and absent from the `digichat-v2.3.2` tree (`git ls-tree digichat-v2.3.2 apps/digichat/src/app/` → no `healthz`), so `:113`/`:262` hold.
- All four initializers exist in `apps/digichat/src/instrumentation.ts:9,14,19,23`; `license_status` is emitted by the **develop** health route (`:76`) and is **absent** from the `digichat-v2.3.2` tree — consistent with `:106` not claiming it for the running builds and `:187` claiming it only for a 2.4.0 image. Checked and refuted as a suspected defect.
- No `DigiChat`/`DigiThings` casing violations in any changed file; `make doc-check` OK.
- `az containerapp update --image` semantics, and the "never pass `--secrets`" advice, are correct.

**Not verified (no access)**

- Every Azure claim: the ACR tag ladder and its 15/15 split, both digests, all `az containerapp show` / `revision list` output, `activeRevisionsMode: Single`, "no probes", the `secretRef` state behind m6, `activeRevisionsMode` rollout risk, the `44cfda92-…` principal.
- Whether the v2.3.3 image exists in git (`git tag -l` shows no `digichat-v2.3.3`, so the dev rollback target at `:193` is an untagged hand-built image — consistent with the hand-build story, but unverifiable here).
- Whether `datatap-web`'s mirror workflow still exists (M2).
- Docker build (accepted limitation).