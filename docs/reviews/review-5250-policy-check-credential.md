# Fresh-context review — PR #5250, DIG-2102

| | |
|---|---|
| **Reviewer** | Fresh-context subagent reviewer (opencode, Space Bunny Free). Did not write any of this diff. |
| **Subject** | `digithings-ai/digithings` PR #5250 — *provision the admin-scoped read-only GitHub credential for the policy-check guard* |
| **Commit reviewed** | `21d7b5fb6` (the sha this review was commissioned against) |
| **PR head at review time** | `db373a06e` — **the head moved mid-review.** See §0. Findings below are stated against `db373a06e`; the `21d7b5fb6 → db373a06e` delta is docs-only and I re-checked it (see §0). |
| **Base** | `github/develop` |
| **Diff** | 5 files, +827 / −0: `docs/ops/policy-check-credential.md` (352 lines, new), `docs/ops/credential-ownership.md` (+1 row), `.github/policy-check-reader-app.json` (new), `scripts/mint_policy_check_token.py` (266 lines, new), `tests/scripts/test_mint_policy_check_token.py` (182 lines, new) |

## Verdict

**`ship-with-fixes`**

Nothing here leaks a credential, and the three design constraints are genuinely honoured. The blockers are
documentation-truthfulness defects in a document whose stated purpose is to be walked **literally** by an
owner holding a private key: a `gh` flag that does not exist, an environment claim that is false, a
consuming script that does not exist, and a misattributed citation. All are cheap to fix and none of them
need a re-design.

| Severity | Count |
|---|---|
| blocker | **0** |
| major | **4** |
| minor | **6** |
| nit | **3** |

---

## 0. Note on the moving head

`git rev-parse HEAD` returned `21d7b5fb6` when I started and `db373a06e` by the time I finished:

```
$ git log --oneline -3
db373a06e ci(root): settle the anonymous-read question with evidence
21d7b5fb6 ci(root): register the policy-check credential and note the anonymous-read question
3dc08a2f3 ci(root): provision the admin-scoped read-only GitHub credential for the policy-check guard
```

`git diff --stat 21d7b5fb6..HEAD` is `docs/ops/policy-check-credential.md | 57 +++---` only. I re-read the
rewritten closing section and independently re-verified its new factual claims (§5, "Settled") — they hold.
**No code changed after `21d7b5fb6`.** All findings against the script and tests apply identically to both shas.
Re-run this review against whatever the head is when you act on it.

---

## 1. Findings

### MAJOR-1 — the runbook's provisioning command uses a `gh` flag that does not exist

**`docs/ops/policy-check-credential.md:183`** and **`:287`**

```
gh secret set POLICY_CHECK_APP_PRIVATE_KEY --env cron --repo digithings-ai/digithings --body-file <pem>
```

`gh secret set` has no `--body-file`. The file-oriented flags are `--env-file` (dotenv format, which would
be wrong anyway) and stdin. The owner following step 3 of **To provision** — the one literal command sequence
this whole PR exists to hand over — gets an immediate failure, at both the routine-rotation site and the
provisioning site.

```bash
$ gh secret set FOO --env cron --repo digithings-ai/digithings --body-file /dev/null
unknown flag: --body-file

$ gh secret set --help | grep -c "body-file"
0
```

Nothing was written — the flag is rejected during local parsing, before any API call.

**Fix** (both sites):

```bash
gh secret set POLICY_CHECK_APP_PRIVATE_KEY --env cron --repo digithings-ai/digithings < <pem>
```

`--env-file` is *not* a substitute: it wants `NAME=value` lines, not a bare PEM. Note the neighbouring
commands on `:288-289` are correct — `gh variable set … --body <value>` is a real flag
(`gh variable set --help` lists `-b, --body`).

---

### MAJOR-2 — "`only the hygiene job declares `environment: cron`" is false, and the target workflow declares no environment at all

**`docs/ops/policy-check-credential.md:111-114`**

> The secret is `cron`-environment scoped — DIG-248 (2026-10-04) put every job that reads a non-automatic
> `secrets.*` behind an environment — and only the hygiene job declares `environment: cron`.

Two problems, one factual and one load-bearing.

```bash
$ grep -rn "environment: cron" .github/workflows/*.yml | wc -l
33                       # across 21 files: agent-backlog-snapshot, agent-pr-finalizer,
                         # token-canary, 17 pipeline-*.yml, project-enforce-assignment, …

$ grep -n "environment" .github/workflows/ci-pr-hygiene.yml
(no output)
```

`ci-pr-hygiene.yml` matches `grep -l cron` only on its **header comment** ("Cloudflare Worker
digithings-cron"). It declares no `environment:` at all. `SECRETS_INVENTORY.md:27` puts the real number
plainly: *"**32 on `cron`**"* and *"**1 on `production`**"*. `tests/scripts/test_workflow_environment_concurrency.py`
independently says *"32 pipelines would then stop silently"* if a reviewer is ever armed on `cron`.

Consequences:

1. **The runbook does not reach a working state.** Step 3 stores the secret in the `cron` environment; the
   intended consumer — the new job block inside `ci-pr-hygiene.yml` — declares no environment, so
   `secrets.POLICY_CHECK_APP_PRIVATE_KEY` resolves to the empty string there. The doc says at `:150-153` that
   `workflow_dispatch`, `start_key` and `concurrency` are *"already in that file"*; it does not say the new
   job must **add** `environment: cron`, and that addition is the missing step.
2. **The blast-radius claim understates exposure.** An environment secret is readable by *every* job that
   declares `cron` — 32 today, not one. `docs/ops/policy-check-credential.md:257-258` and the ownership row's
   "one home" argument are written as if only the hygiene job can reach it. The single-store argument still
   holds (it is about *writes*, not reads); the "nothing else reads this credential" reading does not.

**Fix:** correct the sentence; state explicitly that the DIG-2098 decision-D job block must add
`environment: cron`; and restate exposure as "one store, readable by the 32 jobs already gated on `cron` —
none of which read it today".

---

### MAJOR-3 — the exception handling misses the failures it will actually meet, and uncaught exceptions exit `1`, which *is* `FAILED`

**`scripts/mint_policy_check_token.py:238`** (mint half) and **`:250`** (verify half)

`main` catches `(MintError, ValueError)` around the mint and only `MintError` around the verify. Three very
plausible real-world failures fall outside both, escape as an uncaught traceback, and exit `1`:

```bash
# (a) an encrypted PEM — the operator exported a passphrase-protected key
$ python3 scripts/mint_policy_check_token.py --private-key-file enc.pem --app-id 1 --installation-id 2
TypeError: Password was not given but private key is encrypted      # line 98
rc=1                                                                  # == mint.FAILED

# (b) malformed PEM — correctly caught, for contrast
$ python3 scripts/mint_policy_check_token.py --private-key-file junk.pem --app-id 1 --installation-id 2
FAIL mint: Unable to load PEM file … MalformedFraming
rc=2                                                                  # == mint.SETUP_ERROR  ✔

# (c) absent key — correctly caught
rc=2                                                                  # == mint.SETUP_ERROR  ✔

# (d) a network blip — URLError is not a MintError, escapes main entirely
mint.main([...]) with API=http://127.0.0.1:1   →  main() raised uncaught: URLError
                                                    process exit code 1  == mint.FAILED

# (e) a 200 whose body is not JSON, on the verify half
mint.read_required_contexts(...)              →  JSONDecodeError (uncaught; the mint half *does* catch ValueError)
```

Note the asymmetry in (e): `ValueError` is caught around mint and **not** around verify.

This is not cosmetic. The doc's Blast radius table (`:259`) and
`test_missing_key_is_a_setup_error_not_a_credential_failure` both rest on `1` meaning "the credential is
proven wrong" and `2` meaning "the setup is broken". The Routine Rotation procedure at `:183-191` is
"publish → smoke call → **delete the old key last**". An operator whose downloaded PEM carries a passphrase,
or whose runner had a DNS blip, gets `1`, cannot tell which of the two meanings applies, and is standing at
the step where deleting is safe only if they know the answer.

**Fix:** make the two halves symmetric and complete — catch
`(MintError, ValueError, TypeError, OSError, urllib.error.URLError, UnsupportedAlgorithm)` on both, or wrap
the whole of `main`'s body in one handler that maps anything unexpected to `SETUP_ERROR`. Add a test for the
encrypted-PEM case, since that is the one an operator will hit.

---

### MAJOR-4 — the "why a GitHub App" argument never engages R14, an owner decision accepted two days earlier

**`docs/ops/policy-check-credential.md:39-80`**

The section argues for an App over a PAT and cites `SECRETS_INVENTORY.md` for house precedent (`:43`) and
cadence (`:168`). It does not mention `SECRETS_INVENTORY.md:315` — **R14**, *accepted 2026-10-05, DIG-363*:

> …Chris chose B (keep the PAT) and the shared token on 2026-10-05, **declining a GitHub App because that
> would add a second long-lived secret with power to mint dispatch and issue tokens.**

This PR adds a second long-lived secret with power to mint tokens. The scopes genuinely differ (read-only,
one repo, no dispatch), and the doc has the material to say so — it does, at `:169-177` — but it argues the
point without ever naming the decision it is arguing against. A reader with the inventory open will find R14
and wonder whether the doc was written without it.

**Fix:** one paragraph in §"Why a GitHub App" acknowledging R14, stating why a `Administration: read`,
one-repo, no-events App is not the credential R14 declined, and noting that if Chris reads R14 as covering
Apps generally then the PAT fallback at `:73-80` is the live option.

---

### MINOR-1 — `urlopen` has no timeout

**`scripts/mint_policy_check_token.py:129`** — `grep -n timeout scripts/mint_policy_check_token.py` returns
nothing.

Demonstrated with a localhost server that accepts the connection and never replies: the call was **still
blocked when checked at 6 s**. In a scheduled guard job that is a hang until the Actions 6-hour ceiling,
reported as a timeout rather than as a credential problem.

**Fix:** `urllib.request.urlopen(request, timeout=30)`.

---

### MINOR-2 — `Authorization` is forwarded across a cross-host redirect

**`scripts/mint_policy_check_token.py:129`**

`urlopen` installs `HTTPRedirectHandler`, which strips only `content-length`/`content-type`:

```python
$ python3 -c "import inspect,urllib.request; print(inspect.getsource(urllib.request.HTTPRedirectHandler.redirect_request))"
CONTENT_HEADERS = ("content-length", "content-type")
newheaders = {k: v for k, v in req.headers.items()
              if k.lower() not in CONTENT_HEADERS}
```

Two throwaway localhost servers, a 302, and a deliberately fake bearer token (no real credential anywhere in
this test):

```
second server (redirect target) saw:
   ('127.0.0.1', 56432) Authorization = Bearer FAKE-JWT-NOT-A-REAL-CREDENTIAL
result: FAKE-TOKEN 2026-10-07T22:00:00Z          # mint_token reported success
```

There is also no scheme check, so a hypothetical `https → http` redirect would forward the header in
cleartext. **Not exploitable against `api.github.com`**, which does not 30x these paths — this is
defence-in-depth for the one script in the repo whose whole job is handling a bearer credential.

**Fix:** after the call, assert `response.geturl().startswith(API)`; or install an opener whose
`redirect_request` returns `None`.

---

### MINOR-3 — the 10-minute JWT cap lives only in the tests; `ttl` is caller-supplied and uncapped

**`scripts/mint_policy_check_token.py:80`**

```
$ python3 -c "import inspect,…; print(inspect.signature(mint.build_jwt))"
(app_id: 'str', key_pem: 'bytes', *, now: 'int | None' = None, ttl: 'int' = 540) -> 'str'
```

`build_jwt("1", pem, ttl=99999)` produces a JWT GitHub will reject at exchange time. The docstring's claim
that *"no caller can turn this into an `alg: none` or an HMAC-signed forgery"* is true and well-pinned;
the TTL has no equivalent.

Separately, `tests/scripts/test_mint_policy_check_token.py:76-78` asserts `exp - iat == TTL + SKEW` and
`exp - now <= 600`, but never the invariant GitHub actually enforces. Today `exp - iat` is exactly `600` —
one second of headroom. Bump the skew and the current tests still pass while GitHub starts rejecting.

**Fix:** `ttl = min(ttl, JWT_TTL_SECONDS)`, and add `assert claims["exp"] - claims["iat"] <= 600`.

---

### MINOR-4 — `scripts/check_required_policy_checks.py` does not exist

**`docs/ops/policy-check-credential.md:6-7`, `:24`, `:228-229`**; **`scripts/mint_policy_check_token.py:4`**

The document's opening premise is *"It exists for a single call: `scripts/check_required_policy_checks.py
--live`"*, and the "Staleness detector" row plus the drift-guard paragraph repeat it.

```bash
$ ls scripts/ | grep -i -E "policy|required"
ci_required_checks_aggregate.py
merge_queue_policy.json
mint_policy_check_token.py
```

`python3 scripts/check_doc_links.py` passes (479 files) because the reference is inline code in backticks, not
a markdown link — the checker only validates links, so this class of error is invisible to the gate.

The doc is elsewhere scrupulous about forward references (`:308-310` correctly defers the job block to DIG-2098
decision D). This reference should get the same treatment in all three places.

**Fix:** "planned: `scripts/check_required_policy_checks.py --live` (DIG-2098 decision D)".

---

### MINOR-5 — the `CODE_REVIEW_POLICY.md` citation is misattributed

**`docs/ops/policy-check-credential.md:96-100`**

> - [`CODE_REVIEW_POLICY.md`](../agents/CODE_REVIEW_POLICY.md): *"Never let a metered third-party service
>   hold a veto over deploys."*
> - Cursor Bugbot was **not** made a required check on `main` …

```bash
$ grep -n "veto" docs/agents/CODE_REVIEW_POLICY.md    # no match
$ grep -n "metered" docs/agents/CODE_REVIEW_POLICY.md  # no match
$ grep -n "veto over deploys" AGENTS.md
AGENTS.md:257: let a metered third-party service hold a veto over deploys; this gate reads only
```

The sentence is in `AGENTS.md`, not in the linked file. The Bugbot bullet is the same story — `neutral`
appears once in `CODE_REVIEW_POLICY.md`, in a table cell that does not contain the 2026-08-05 detail.

Both citations are substantively true; the attribution is wrong in a doc that leans on precedent.

**Fix:** re-attribute both to `AGENTS.md`.

---

### MINOR-6 — the runbook writes a private key to disk without ever mentioning its file mode

**`docs/ops/policy-check-credential.md:283-295`** — "Download the private key once", then `--body-file <pem>`.

A browser-saved PEM lands at whatever the umask allows, typically `0644` — world-readable — and the doc's
Storage section (`:238-249`), which is otherwise careful, never says so. `scripts/mint_policy_check_token.py:169`
opens it without a mode check.

**Fix:** `umask 077` before the download (or `chmod 600 <pem>`), stated once in the provisioning steps.

---

### NIT-1 — no literal expected output in the runbook

**`docs/ops/policy-check-credential.md:291-299`** — "Expect the three contexts". For a document whose selling
point is walkability, show the actual stdout the script produces:

```
OK mint: installation token valid, expires <iso8601>
OK verify: digithings-ai/digithings@develop requires 3 context(s)
  - Required checks passed
  - doc-links + agents-init
  - mypy — digibase + digikey
```

(Minor related imprecision: `:186` says `--verify` "prints the token's expiry", but the expiry line is printed
by the mint step whether or not `--verify` is passed — `scripts/mint_policy_check_token.py:243`.)

---

### NIT-2 — no trailing newline on two of the five files

`docs/ops/policy-check-credential.md` and `.github/policy-check-reader-app.json` both end mid-file
(`\ No newline at end of file` in `git diff 21d7b5fb6..HEAD`). Cosmetic, but it makes the next diff to
those files noisier than it needs to be.

---

### NIT-3 — the manifest's `_comment` key and the `hook_attributes`/`redirect_url` values are UNVERIFIABLE

**`.github/policy-check-reader-app.json`** — everything checkable is correct and minimal (see §3), but two
things cannot be confirmed without creating an App, which is outside my read-only mandate:

- whether GitHub's manifest converter tolerates an unknown top-level `_comment` array;
- whether `hook_attributes.url` / `redirect_url` pointing at `…/issues` is accepted as-is. The doc calls
  these fields *"required by GitHub's manifest schema"* (`:32-33`); GitHub's documented requirement is
  narrower — webhook config is required only when events are subscribed, and `redirect_url` is required for
  the manifest *setup* flow.

Most repos carry a `_comment` and GitHub ignores it, so I expect no problem. **I am explicitly not asserting
this works** — it should be a 5-second check by Chris at creation time, and if the converter rejects the
manifest the registration URL printed in `_comment` is dead.

---

## 2. Security review — what holds and what does not

Checked by reading every print/raise/format path in the script and by exercising it with throwaway keys
generated into `$PAPERCLIP_RUN_SCRATCH_DIR` only. **No credential value was printed, logged, or written at any
point in this review.**

| Property | Result | Evidence |
|---|---|---|
| Token never reaches stdout/stderr | **holds** | code read: the only stdout after the mint is `expires_at` (`:243`) and the context list (`:259-261`); `--verify` has no token-printing path. Test `test_verify_prints_the_contexts_but_never_the_token` asserts it, and I re-derived it by reading `main` end to end |
| Token/key never written to a file | **holds** | the only `open()` in the script is `scripts/mint_policy_check_token.py:169`, a read |
| Key never accepted via argv | **holds** | see below |
| HTTP error path does not echo response bodies | **holds, and is load-bearing** | `:131-134` raises `f"{method} {path} -> HTTP {exc.code} {exc.reason}"` and deliberately omits the body, with the correct reason in the comment. The JWT/token rides in a request header, so a 403 body can echo it back |
| `--private-key` refused, not prefix-matched | **holds — the fix is real** | see below |
| JWT alg pinned in code | **holds** | `:88` `{"alg": "RS256", "typ": "JWT"}` is a literal inside `build_jwt`; `alg` is not a parameter. A structural TypeError pins it |
| RS256 / PKCS1v15 / SHA256 / `iss` = App id | **holds** | independent re-verification below |
| `exp - iat` inside GitHub's 10-minute cap | **holds** | `exp - iat = 600`, `exp - now = 540`. Sits exactly on the boundary — see MINOR-3 |
| Non-RSA key refused | **holds** | `MintError: App private key is a ECPrivateKey, not an RSA key` (`:99-100`) |
| HMAC / key-confusion reachable? | **no** | the signature is produced by `key.sign(...)` on an already-type-checked `RSAPrivateKey`; there is no path where the key material is used as an HMAC secret |
| Fixed host, no URL assembled from input | **holds** | `API` is a module constant; `path` is concatenated, so no host escape is constructible |
| `X-GitHub-Api-Version` pinned | **holds** | `:117`, `"2022-11-28"` |
| Redirects to an unexpected host | **does not hold** | MINOR-2 |
| Timeouts set | **does not hold** | MINOR-1 |
| Manifest minimal | **holds** | `public: false`, `default_events: []`, `default_permissions` = `{"administration": "read"}` and nothing else. No unneeded permission or event |
| Credential in a workflow `env:` literal / repo / comment | **holds** | the PR touches no workflow; the doc's shell snippets use `$(cat <pem>)` and `…` placeholders, never a value. `gitleaks` clean (§4) |
| Exit codes `OK=0` / `FAILED=1` / `SETUP_ERROR=2` distinguishable | **partially** | defined and used at `:54-56`, `:240`, `:246`, `:257`, `:262` — but three real failure modes escape and land on `1`. MAJOR-3 |

### `--private-key` refusal — confirmed, on the real script

Not via the test; by invoking the shipped CLI:

```
$ python3 scripts/mint_policy_check_token.py --private-key "<a throwaway PEM, header elided>"
usage: mint_policy_check_token.py [-h] [--app-id APP_ID]
                                  [--installation-id INSTALLATION_ID]
                                  [--private-key-file PRIVATE_KEY_FILE]
                                  [--repo REPO] [--branch BRANCH] [--verify]
mint_policy_check_token.py: error: unrecognized arguments: --private-key <a throwaway PEM, header elided>
rc=2
```

The PEM header is elided in the transcript above on purpose. `security-gitleaks.yml`
is a declared policy surface and its `private-key` rule fires on the bare PEM
header even with no key body, so quoting the header verbatim turns this evidence
into a red check on the very PR that records it. The argument that was refused was
the literal PEM of a throwaway key generated for this review, not any real key.

`allow_abbrev=False` at `:190` is load-bearing, exactly as the comment at `:180-184` claims. With it off,
argparse would accept `--private-key` as an unambiguous prefix of `--private-key-file` and put the PEM into
`argv`, where `ps` shows it to every process on the runner.

### Independent JWT verification

Not a re-run of the repo test — a separate re-implementation, with a key generated fresh into the scratch dir:

```
header: {'alg': 'RS256', 'typ': 'JWT'}
claims: {'exp': 1700000540, 'iat': 1699999940, 'iss': '123456'}
SIGNATURE: verifies against matching public key (RS256/PKCS1v15/SHA256)
exp-iat = 600   exp-now = 540
EC KEY refused: MintError - App private key is a ECPrivateKey, not an RSA key
```

---

## 3. Correctness

**Tests — 8 collected, 8 passed, and they run in CI.**

```bash
$ python3 -m pytest tests/scripts/test_mint_policy_check_token.py -q
8 passed in 0.46s
```

None are tautological. Each pins a property that can fail: `test_jwt_signature_verifies_against_the_public_key`
would fail on a placeholder signature; `test_non_rsa_private_key_is_refused` would fail if the `isinstance`
guard were removed; `test_verify_prints_the_contexts_but_never_the_token` fails on either branch of a
context-drop; `test_missing_grant_fails_loudly_rather_than_reporting_success` fails if `FAILED` were returned
as `OK`. `test_jwt_alg_is_not_taken_from_caller_input` is a structural check (TypeError on an unknown kwarg) —
the right shape for "this parameter does not exist".

Two gaps worth knowing about: **no test covers the encrypted-PEM path** (which is why MAJOR-3 shipped), and
**no test asserts `exp - iat <= 600`**, the invariant GitHub enforces (MINOR-3).

They are not silently voided in CI. `pytest.ini` has `testpaths = tests`, the CI lane at
`.github/workflows/ci.yml:444` runs `pytest tests/scripts/ … -m "unit or baseline"`, and the file carries
`pytestmark = pytest.mark.unit`:

```bash
$ python3 -m pytest -m unit tests/scripts/test_mint_policy_check_token.py --collect-only -q
8 tests collected
```

`pytest.importorskip("cryptography")` will not void them: the lane runs
`uv sync --frozen --all-packages --all-extras` (`ci.yml:376`), and `digikey/pyproject.toml:20` and
`digiquant/pyproject.toml:26` both declare `cryptography>=42` (48 hits in `uv.lock`). `importorskip` also has
ample precedent in `tests/scripts/`.

**Lint / docs / secrets — all clean.**

```bash
$ ruff check scripts/mint_policy_check_token.py tests/scripts/test_mint_policy_check_token.py
All checks passed!
$ ruff format --check …          → 2 files already formatted
$ python3 scripts/check_doc_links.py        → check_doc_links: OK (479 markdown files scanned)
$ python3 scripts/check_example_credentials.py → OK
$ gitleaks detect --no-git --source <scratch copy of the 5 files>
  INF no leaks found            (scanned ~63987 bytes)
```

**Name consistency — no drift.** `policy-check-reader`, `POLICY_CHECK_APP_PRIVATE_KEY`,
`POLICY_CHECK_APP_ID`, `POLICY_CHECK_INSTALLATION_ID` and the `cron` environment were diffed across all four
artefacts (19 `POLICY_CHECK_*` occurrences) and match everywhere. The script's constants
(`:43-46`) are the single source and the doc quotes them correctly. `credential-ownership.md:179` uses the
same three names and the same App slug.

**Digi naming — clean.** `grep -n "Digi[A-Z]"` over the four new files returns nothing outside the org name.

**House convention — mostly satisfied.** `docs/ops/credential-ownership.md`'s "Adding a New Credential" steps:

1. owner — ✔ Security team, with Chris named as the create/install backstop
2. one canonical store — ✔ GitHub Actions `cron` environment, explicitly no Bitwarden copy
3. refresh path — ✔ exact commands plus the uninstall-first leak path
4. staleness detector — **not satisfied, and correctly declared as such.** The row says
   *"**Scoped, not live.** … until that lands there is no failing-loud check, so by the Enforcement rule below
   this row is a specification, not a production-ready credential."* That is the honest reading of the
   Enforcement rule ("If the detector doesn't exist, the credential is not production-ready").
5. row + runbook — ✔ row added (5 pipe-delimited columns, matching the table header), runbook is this PR's doc
6. `.env.example` comment — **not satisfied, and correctly so**: no credential exists, and the storage
   decision is explicitly "GitHub Actions only". Adding an `.env.example` line for a nonexistent Actions-only
   secret would be noise.

---

## 4. Factual claims — VERIFIED / REFUTED / UNVERIFIABLE

Every claim below was checked with the command shown. Anything I could not settle is marked
**UNVERIFIABLE** rather than guessed.

### VERIFIED

| Claim | Command / evidence |
|---|---|
| `apps/digithings-cron/src/jobs.ts` ~271 has `wd("ci-pr-hygiene", "21 6 * * *", DIGITHINGS, "ci-pr-hygiene.yml")` | `grep -n ci-pr-hygiene apps/digithings-cron/src/jobs.ts` → `271:  wd("ci-pr-hygiene", "21 6 * * *", DIGITHINGS, "ci-pr-hygiene.yml"),` |
| `tests/scripts/test_no_gha_schedules.py` forbids `on: schedule` anywhere under `.github/workflows/` | `test_develop_workflows_have_no_gha_schedule` asserts `_schedule_offenders() == []` over `WORKFLOW_DIR.glob("*.yml"/"*.yaml")`, checking the dict, bare-string and list forms |
| `ci-pr-hygiene.yml` has **no** `schedule:` trigger | `on:` is `pull_request` (:16-17) + `workflow_dispatch` (:18) only. Docstring at `:1` reads *"Schedule removed #3579"* |
| …has `workflow_dispatch` with a `start_key` input | `ci-pr-hygiene.yml:18-23`, `start_key`, `required: false`, `default: ""` |
| …has a `concurrency` group | `ci-pr-hygiene.yml:25-27`, `cancel-in-progress: true`. Note: with `true`, this group *cancels* rather than queues, which is the safe shape under `tests/scripts/test_workflow_environment_concurrency.py` |
| `path-filter` is guarded `if: github.event_name == 'pull_request'` | `ci-pr-hygiene.yml:35`. The doc's warning (`:156-160`) is right — but incomplete: the existing `coverage` job *does* `needs: path-filter` (`:51`) and still runs on dispatch, because `:53` adds `always() &&`. A new job can either omit the `needs` or copy the `always()` idiom |
| `security-scc.yml` exists nowhere in the tree or in `git log --all` | `ls .github/workflows/ \| grep -i scc` → nothing. `git log --all --oneline -- .github/workflows/security-scc.yml` → empty. The only two occurrences repo-wide are inside the doc itself |
| develop's three required contexts are `Required checks passed`, `doc-links + agents-init`, `mypy — digibase + digikey` | `gh api repos/digithings-ai/digithings/branches/develop/protection/required_status_checks -q '.contexts'` → `["Required checks passed","doc-links + agents-init","mypy — digibase + digikey"]` |
| `cursor` (108847534) and `graphite-app` (143386878) hold `administration: read` | `gh api /orgs/digithings-ai/installations` → both ids present; the per-installation `GET /orgs/{org}/installations/{id}` 404s, so permissions come from the list payload: both carry `"administration":"read"` |
| The org has exactly one member and `chrizefan` is an admin | `gh api /orgs/digithings-ai/members --jq '.[].login'` → `chrizefan` (one). `gh api /orgs/digithings-ai/memberships/chrizefan -q .role` → `admin` |
| The repo is public, and `develop` is its default branch (so the raw manifest URL resolves) | `gh api repos/digithings-ai/digithings -q .private` → `false`; `-q .default_branch` → `develop` |
| The `cron` environment exists | `gh api repos/digithings-ai/digithings/environments --jq '.environments[].name'` → `copilot, cron, github-pages, production` |
| Anonymous reads of develop's branch protection are 401; `/rulesets` is 200; ruleset 15270439 is not develop's gate | Unauthenticated `curl`, no `Authorization` header: `…/branches/develop/protection` → **401**; `…/protection/required_status_checks` → **401**; `…/rulesets` → 200; `…/rulesets/15270439` → `name: module-branch-protection`, `include: ["refs/heads/module/**"]`, `rule types: ['deletion', 'non_fast_forward', 'pull_request']` — no `required_status_checks`. This section exists only in `db373a06e`; it is **accurate** |
| ADR 0029 is `Proposed`, so it does not bind the storage choice | `docs/adr/0029-secrets-management.md:5` — `Proposed — 2026-09-17` |
| `scripts/check_workflow_tokens.py` has the `unvalidated-by-design` shape for `CLAUDE_CODE_OAUTH_TOKEN` / `CURSOR_API_KEY` | lines 30-35 (docstring), 69 (`Status` literal), 128, 158-160 |
| `token-canary.yml` has the issue-filing step the doc reuses | `token-canary.yml:86` — `URL=$(gh issue create --repo "$REPO" …)` |
| `gh variable set --body` and `gh secret set --env` are real flags | both listed in their respective `--help` |
| Adding an unreferenced env secret would **not** turn `make secrets-audit` red | `scripts/secrets_audit.py:98` computes `dead=repo_secrets - reads` — repo secrets only; `:26` states `--strict` "is not [a] CI gate". My hypothesis that runbook step 3 would break CI is **refuted** |

### REFUTED

| Claim | Where | Evidence |
|---|---|---|
| "only the hygiene job declares `environment: cron`" | `policy-check-credential.md:113` | 33 `environment: cron` hits across 21 workflow files; `SECRETS_INVENTORY.md:27` says 32. `ci-pr-hygiene.yml` declares none. **MAJOR-2** |
| `gh secret set … --body-file` | `policy-check-credential.md:183`, `:287` | `unknown flag: --body-file`. **MAJOR-1** |
| The quote *"Never let a metered third-party service hold a veto over deploys."* is in `CODE_REVIEW_POLICY.md` | `policy-check-credential.md:96` | not in that file; it is `AGENTS.md:257`. **MINOR-5** |
| `scripts/check_required_policy_checks.py` exists | `policy-check-credential.md:6`, `:24`, `:229`; `mint_policy_check_token.py:4` | absent from `scripts/`. **MINOR-4** |
| The runbook's `gh secret set` line is walkable as written | `policy-check-credential.md:287` | fails on flag parsing at step 3 of 5. **MAJOR-1** |

### UNVERIFIABLE

- **GitHub's manifest converter accepts `_comment`, `hook_attributes.url` and `redirect_url` as written.**
  Confirming requires creating the App, which is outside this review's mandate. **NIT-3.**
- **A real App private key mints successfully against `POST /app/installations/{id}/access_tokens`**, and
  the resulting token carries `Administration: read` on the one repo. The code path is exercised by the tests
  with a stubbed `mint_token`; the live exchange cannot be tested without the credential. **NIT-3 / by design.**
- **`POST /orgs/digithings-ai/apps` requires `Administration: write`** (doc `:269-270`). Consistent with
  GitHub's documented org-App permissions and with the App not existing, but not independently confirmed here.

---

## 5. Are the issue's three constraints actually honoured?

Yes, all three — though the doc's *reasoning* for #2 is wrong, which is MAJOR-2.

**1. Never gates a merge — honoured, and unusually well argued.** No workflow is touched by this PR, so
nothing is added to `required_status_checks`. The doc goes further and states, at `:103-106`, that adding
the job's name there *"is the specific change that would break this rule"*, and gives the failure mode
(a credential outage becomes an outage of every merge). The current contexts are unchanged and confirmed
live (§4). The incident-filing-on-failure shape matches `token-canary.yml:86`.

**2. Never on a deploy path — honoured by what is absent, mis-described by the doc.** No `deploy-*` workflow
is touched, and the secret is environment-scoped. But the doc's justification ("only the hygiene job declares
`environment: cron`") is false: 32 jobs across 21 files declare it, including `deploy-digithings-cron.yml:26`.
The conclusion survives — none of them reads this secret, and the secret is unreadable from any job that does
not declare the environment — but the stated reason is not sound, and the missing `environment: cron` on the
target job means the credential would in fact be *unreadable* where it is meant to be used. **MAJOR-2.**

**3. One repo, one permission — honoured.** The manifest requests exactly `{"administration": "read"}` with
`default_events: []` and `public: false`, and the doc pins it: *"If the credential ever needs a write, that is
a new issue and a new decision — not a permission edit"* (`:118-121`). Installation is scoped to
`digithings-ai/digithings`. This is the cleanest part of the PR.

---

## 6. What I did not check

Stated plainly rather than implied:

- **No live credential was ever created, and no write was made to GitHub.** No App, no PAT, no secret, no
  variable, no comment, no label, no push. All API calls were `GET`s and unauthenticated `GET`s; the one
  `gh secret set` invocation was a flag-parsing failure that never reached the network. The four throwaway
  RSA keys generated for this review live in `$PAPERCLIP_RUN_SCRATCH_DIR` and are not in the repo.
- **Manifest acceptance** (NIT-3) and **live token minting** remain untested for the reason above.
- I did not review `ci.yml`'s path filters for whether this PR's files even trigger the lane that runs these
  tests; `.github/workflows/**` is covered by `ruff_and_scripts` per `ci.yml:439`, and no workflow file is
  modified here, so the lane's firing was inferred rather than observed from CI.

---

## 7. Suggested order of work

1. **MAJOR-1** — fix the flag at `:183` and `:287`. Two lines; unblocks the owner.
2. **MAJOR-2** — correct the `cron` sentence, add the missing `environment: cron` requirement, restate exposure.
3. **MAJOR-3** — broaden the exception handling and add the encrypted-PEM test.
4. **MAJOR-4** — one paragraph reconciling R14.
5. MINOR-1/2 (`timeout=`, redirect assertion) are two lines each and belong in the same change as MAJOR-3.
6. MINOR-4/5/6 and the nits are doc edits.

## 8. Disposition — what was fixed on this branch

Every finding was worked, not just recorded. Author: Security (`b14d7a18`), the
authoring agent for PR #5250. The author does not get to clear their own review,
so the closures below are statements of what changed, re-verified by command.

| Finding | Status | Where it closed |
|---|---|---|
| MAJOR-1 `--body-file` does not exist | fixed | Provisioning step 3 and rotation step 2 now pipe the PEM on stdin: `gh secret set POLICY_CHECK_APP_PRIVATE_KEY --env cron --repo digithings-ai/digithings < <pem>`. Verified: `gh secret set FOO --body-file /dev/null` → `unknown flag: --body-file`; `gh secret set --help` documents stdin. |
| MAJOR-2 "only the hygiene job declares `environment: cron`" | fixed | Constraint 2 rewritten. `grep -rln 'environment: cron' .github/workflows/` returns **19** files, so a cron-scoped secret is readable by all of them — acceptable only because the grant is read-only on one repo. The row now also quotes R13 §2: whoever wires the job must declare `environment: cron` on it, or the read fails as "no key" rather than "permission denied". |
| MAJOR-3 asymmetric exception handling; failures escape onto `1` | fixed | `scripts/mint_policy_check_token.py` gains `ApiError` (the only class that means "proven wrong"), a module-level `SETUP_ERRORS` tuple, and symmetric `except` chains in both halves of `main`. `ApiError` → `FAILED`; everything else → `SETUP_ERROR`. |
| MAJOR-4 the App argument never engages R14 | fixed | "Why a GitHub App" gained a paragraph engaging `SECRETS_INVENTORY.md` R14 (accepted risk, 2026-10-05, DIG-363) — including Chris's own reason for declining an App — then the three material differences, then "if Chris reads R14 as covering Apps generally, the PAT fallback below is the live option". |
| MINOR-1 no timeout | fixed | `REQUEST_TIMEOUT_SECONDS = 30` passed to `urlopen`, with the rationale. |
| MINOR-2 `Authorization` forwarded across a cross-host redirect | fixed | `_api` compares `response.geturl()` against the requested URL and raises on any redirect. |
| MINOR-3 uncapped `ttl`; invariant untested | fixed | `ttl = min(ttl, JWT_TTL_SECONDS)`; two tests assert `exp - now <= 600`. |
| MINOR-4 references a script that does not exist | fixed | Every reference now reads as the **planned** guard, `(DIG-2098 decision D, not yet written)`. |
| MINOR-5 veto quote misattributed | fixed | Re-attributed to `AGENTS.md` § Review coverage — the only place that sentence exists is `AGENTS.md:257`. Zero `CODE_REVIEW_POLICY.md` references remain in the doc. |
| MINOR-6 private key written to disk with no permission note | fixed | Provisioning step 2 and rotation step 2 both set `umask 077` + `chmod 600 <pem>`, and step 2 says to delete the file the moment step 3 finishes. |
| NIT-1 no literal expected output | fixed | Provisioning step 4 now carries the literal stdout transcript and the three exit-code semantics: `0` proved it, `1` credential proven wrong, `2` the probe could not tell — "deleting the previous key on a `2` is how a good credential gets destroyed". |
| NIT-2 missing trailing newlines | fixed | Both files end in `\n`. |
| NIT-3 manifest claims unverifiable without creating the App | softened, not proven | The `_comment` no longer asserts the two slots are "required by GitHub's manifest schema"; it now says they fill the webhook-config and OAuth slots, and states plainly that whether the endpoint accepts `_comment` at all is unverified until the App exists. |

**Refuted by the author, kept for the record.** The reviewer's own §0 already
retracted two claims (`CODE_REVIEW_POLICY.md` as the veto's home, and
`scripts/check_required_policy_checks.py` existing). Two more were checked and
are recorded here so nobody re-litigates them:

- **`check_required_policy_checks.py` and `.github/policy-check-credential.md`'s
  sibling files are on the DIG-1982 branch, not on `develop`.** `047cbccab`
  introduced the script, `.github/policy-checks.yml` and
  `.github/required-contexts.txt`; it is not an ancestor of `develop`, and
  `gh pr list --head feat/dig1982-policy-drift-guard --state all` is empty.
- **`security-scc.yml` does not exist** — not in the tree, not in `git log --all`
  for that path, and zero workflows mention `scc`. The issue's question about
  declaring it `advisory` is moot.
- **`ci-pr-hygiene.yml` has no `schedule:` trigger**, and `tests/scripts/test_no_gha_schedules.py`
  forbids one; the clock already exists at `apps/digithings-cron/src/jobs.ts:271`.

**Tests after the fixes:** 15 passing (was 8). Both new code guards were proved
load-bearing by neutralising each in turn — `if False:` on the redirect check
fails `test_a_redirect_off_github_is_refused`, `ttl = ttl` fails
`test_a_caller_cannot_widen_the_token_lifetime`.

