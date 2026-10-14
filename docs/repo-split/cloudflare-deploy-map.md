# Cloudflare deploy map, local CI design, and the end of auto-deploy from main

Status: proposal only. No Cloudflare setting was changed. No repository was created.

## 1. Scope and limits

This document answers three questions for DIG-3571.

1. Which Cloudflare project does each package deploy to.
2. Which repository, release branch, and local command deploy it after the repo split.
3. How we stop Cloudflare from building and deploying from `main`.

I measured the live Cloudflare account with a read-only tool. I measured the repository at `github/develop` = `d227b6ed5`. I did not use a write tool. I did not change any Cloudflare setting.

I did not do the following. Each item needs a decision from Chris.

- I did not create a repository on GitHub or on Origin.
- I did not move a branch or a commit.
- I did not merge to `main`.
- I did not run a deploy.
- I did not restart Paperclip.

## 2. Table A. The six live Workers

I read these six Workers from the live Cloudflare account. The "modified" time is what Cloudflare reports for the script.

| Live Worker name | wrangler.toml on develop | Future repo | Release branch | Local deploy command |
|---|---|---|---|---|
| `digiquant-runner` | `apps/digiquant-runner/wrangler.toml` | R2 `digiquant-stack` | `release/stack` | `npx wrangler deploy -c apps/digiquant-runner/wrangler.toml` |
| `dashboard-api` | `apps/dashboard-api/wrangler.toml` | R2 `digiquant-stack` | `release/stack` | `npx wrangler deploy -c apps/dashboard-api/wrangler.toml` |
| `digithings-cron` | `apps/digithings-cron/wrangler.toml` | R5 `digithings-stack` | `release/stack` | `npx wrangler deploy -c apps/digithings-cron/wrangler.toml` |
| `digithings-stack` | `apps/digithings-stack-cloudflare/wrangler.toml` | R5 `digithings-stack` | `release/stack` | `npx wrangler deploy -c apps/digithings-stack-cloudflare/wrangler.toml` |
| `digithings-digichat` | `apps/digichat-cloudflare/wrangler.toml` | R5 `digithings-stack` | `release/stack` | `npx wrangler deploy -c apps/digichat-cloudflare/wrangler.toml` |
| `corpus-index` | `apps/corpus-index/wrangler.toml`, on 2 unmerged branches, **not on develop** | **D-1, still open** | see D-1 | `npx wrangler deploy -c apps/corpus-index/wrangler.toml` |

Modified times for the six Workers:

| Live Worker name | created | modified |
|---|---|---|
| `digiquant-runner` | unknown | 2026-10-01T13:56 |
| `dashboard-api` | unknown | 2026-09-26T19:40 |
| `digithings-cron` | unknown | 2026-10-13T12:45 |
| `digithings-stack` | unknown | 2026-10-14T12:57 |
| `digithings-digichat` | unknown | 2026-10-14T01:53 |
| `corpus-index` | 2026-10-13T17:33 | 2026-10-13T18:38 |

### 2.1 The live name is not always the directory name

`apps/digichat-cloudflare/wrangler.toml` sets `name = "digithings-digichat"`. The directory name and the Worker name differ. Use the Worker name in Cloudflare and the path in git. Do not join them by name.

### 2.2 Two Workers were never deployed

`apps/digitrace-langfuse/wrangler.toml` and `apps/digidata-api/wrangler.toml` exist on develop. The live account does not contain a Worker named `digitrace-langfuse` or `digidata-api`. These two Workers were never deployed.

`digitrace-langfuse` goes to R5. `digidata-api` goes to R7 `twelve-x`. Neither needs a migration step for Cloudflare. It needs a decision about whether to deploy it or to delete it.

### 2.3 The corpus-index finding: corrected, and the source is in the repository

**Correction.** This section first said "The public repository contains no file for it." That was wrong. The search behind that sentence was scoped to `develop`. The source is in this repository, on two unmerged branches.

`corpus-index` is live, and its source is `apps/corpus-index/`: 26 files, with its own `wrangler.toml`. It is not on `develop`. `git ls-tree -r github/develop` matches 0 paths for `corpus-index`. A control confirms the matcher fires: 8 `wrangler.toml` files are on develop.

**How I found it.** The deployed script gave me a symbol that cannot occur by accident. A search restricted to develop would never have seen it.

```
git log --all --oneline -S'FORBIDDEN_KEY'
  cfd3811a3  feat(corpus-index): add the daily multilingual index worker
  60ea0c773  fix(corpus-index): Zammad range query for the ticket cursor; mask names, mail headers and organisations
```

**Where it lives.**

| Branch | Pull request | State |
|---|---|---|
| `DIG-3269-occ-daily-index` | #5545 `feat(digisearch): add the bge-m3 daily corpus index` | OPEN, not merged |
| `DIG-2203-census-deploy` | #5580 `feat(digichat): OCC cold-start warm-up, model picker tier and mobile polish` | OPEN, not merged |

Neither commit is an ancestor of `github/develop`. `merge-base --is-ancestor` returns false for both.

**The deployed script matches the branch source.** I read the deployed script with a second read-only tool, `workers-get-worker-code`. It returns a 28,599 character esbuild bundle whose module comments name 11 source files: `model.ts`, `http.ts`, `workflow.ts`, `clients.ts`, `config.ts`, `pii.ts`, `chunk.ts`, `vectors.ts`, `sync.ts`, `run.ts`, `index.ts`. That is the `apps/corpus-index/src` layout.

Six distinctive strings are present in both the deployed bundle and the branch source: `FORBIDDEN_KEY`, `isWeeklyReconcile`, `overlapCursor`, `EMBED_MODEL_ID`, `bge-m3`, `CorpusIndexWorkflow`. A negative control, `ZZZ_NOT_PRESENT`, is 0 in both.

**The deployed build carries the privacy fix.** Commit dates are +0200, so the add commit is 16:12 UTC and the fix commit is 17:57 UTC. The Worker was created at 17:33 UTC and modified at 18:38 UTC. The fix landed after the first deploy and was deployed 41 minutes later. The live Worker masks names, mail headers and organisations.

**What this changes.**

1. It is not source-less. Table A is complete on the source side.
2. It is the one Worker whose source is on no trunk branch. It sits in two open pull requests. If both close without merging, the source is lost. That makes it the highest-priority Worker to land before any branch cleanup in the migration.
3. It is not a plain cron Worker. Its `wrangler.toml` declares an AI binding, a KV namespace and a Cloudflare Workflow.

```toml
name = "corpus-index"
main = "src/index.ts"
workers_dev = true

[ai]
binding = "AI"

[[kv_namespaces]]
binding = "CORPUS_INDEX_KV"
id = "16160cf4676d4175a2ec4044f0aead1b"

[[workflows]]
name = "corpus-index-daily"
binding = "CORPUS_INDEX_WORKFLOW"
class_name = "CorpusIndexWorkflow"

[triggers]
crons = ["0 3 * * *"]
```

The file states that the clock is on this Worker, at 03:00 UTC, and not on `digithings-cron`. Under the migration the AI binding, the KV namespace and the Workflow stay on the Cloudflare side. Only the trigger moves to the Mac. Section 6 does not need to change for it.

**One small defect.** `apps/corpus-index/.wrangler/tmp/deploy-roabtC/index.js` is committed on `DIG-2203-census-deploy`. That is a build output. `develop` has 0 such paths. It should not merge.

## 3. Table B. The two Pages projects

Cloudflare Pages builds a static site. A Pages project has a production branch. Cloudflare rebuilds the site when it sees a push to that branch.

| Site | Built from | Future repo | Release branch | Build command | Local deploy command |
|---|---|---|---|---|---|
| digiquant.io | `scripts/build-digiquant.sh` → `dist/` | R3 `digiquant-web` | `release/web` | `bash scripts/build-digiquant.sh` | `npx wrangler pages deploy dist --project-name <name>` |
| digithings.ai | `scripts/build-digithings.sh` → `dist/` | R4 `digithings-web` | `release/web` | `bash scripts/build-digithings.sh` | `npx wrangler pages deploy dist --project-name <name>` |

`build-digiquant.sh` copies `apps/digiquant-web/out/` to `dist/`. It also puts the desk in `dist/dashboard/`. `build-digithings.sh` copies `apps/digithings-web/out/` to `dist/`. It also mirrors `apps/digithings-web/functions/`. It also runs `npx --yes openwiki@0.5.0 visualize openwiki --export dist/openwiki`.

### 3.1 The wrangler.toml name for Pages is not the production name

`apps/digithings-web/wrangler.toml` sets `name = "digithings-web"` and `pages_build_output_dir = "out"`. Its own header says that this file is for the local command `wrangler pages dev`. It says the production project builds the repository-root `dist/`.

So the production Pages project has another name. I could not read that name from the repository. `digithings-ai` does not appear in `deploy-digithings-cloudflare.yml` at all. Only the Cloudflare dashboard holds the real project names. Section 7 asks Chris to supply them, or to read them with a dashboard session.

## 4. Table C. What deploys today

I read all 74 workflow files on develop. Two of them deploy to Cloudflare.

| Workflow | Trigger | Deploys | State |
|---|---|---|---|
| `deploy-digithings-cron.yml` | `push` to `main` | `digithings-cron` via `cloudflare/wrangler-action@v3`, wrangler `4.28.0`, `environment: production` | works |
| `deploy-digiquant-runner.yml` | `push` to `main` | `digiquant-runner` via `npx wrangler deploy -c apps/digiquant-runner/wrangler.toml`, `environment: production` | dead |
| `build-cloudflare-workers.yml` | `pull_request` | nothing. It runs `wrangler deploy --dry-run --containers-rollout=none` | build check only |
| `deploy-digiquant-cloudflare.yml` | `pull_request`, `workflow_dispatch` | nothing | build check only |
| `deploy-digithings-cloudflare.yml` | `pull_request`, `workflow_dispatch` | nothing | build check only |

### 4.1 The dead lane

`deploy-digiquant-runner.yml` cannot fire. Its path filter needs files under `apps/digiquant-runner/`. That path holds 21 files on develop. It holds 0 files on `main`. So the filter never matches a push to `main`. The workflow has never deployed the runner.

### 4.2 No workflow deploys Pages

The control fired. Ten workflow files use the word `wrangler`. The highest count is 9 hits in `build-cloudflare-workers.yml`.

The search found 0 workflows. The search looked for `wrangler pages deploy`, for `pages deploy`, and for `CF_PAGES_BUILD`.

So no GitHub Actions workflow pushes a Pages site. The two Pages headers confirm this. `deploy-digiquant-cloudflare.yml` line 2 says "Primary deploy is Cloudflare Pages watching `main`". `deploy-digithings-cloudflare.yml` line 2 says the same for `digithings.ai`.

### 4.3 Two Workers were already deployed from the Mac

`digithings-stack` was modified 2026-10-14 at 12:57. `digithings-digichat` was modified 2026-10-14 at 01:53. No GitHub Actions workflow deploys either one. They were deployed by a person, from the Mac, today.

This is the model we want to make standard. It already runs. This proposal only writes down the steps.

## 5. Design for a local CI that runs `wrangler deploy`

Chris directed that the migration must leave GitHub Actions. GitHub Actions minutes are exhausted. Cursor Origin is available. The Mac is available.

### 5.1 The rule

Run the build on the Mac. Run the deploy on the Mac. Do not use GitHub Actions for either step. Record the local test result in the PR body.

A missing GitHub Actions check is not a failure under this rule. The local record replaces it.

### 5.2 The gate, before any deploy

Run the dry run first. A dry run builds the Worker. It does not upload it.

For a Worker:

```
npx wrangler deploy --dry-run --containers-rollout=none -c <path>/wrangler.toml
```

For a Pages site:

```
bash scripts/build-<site>.sh
npx wrangler pages functions build --project-name <name>
```

**Warning for the two container Workers.** `digithings-stack` and `digithings-digichat` declare a `[[containers]]` block. wrangler 4 needs the Docker CLI to build a container image. It needs Docker even in `--dry-run` mode. The Docker binary is at `/usr/local/bin/docker`. It is not on the agent PATH. A run that cannot find Docker fails before it prints a result. A failed dry run on these two Workers does not prove a defect.

### 5.3 The deploy

Run the deploy as Chris's normal user. Use the wrangler OAuth credential. It is at `~/Library/Preferences/.wrangler/config/default.toml`. It was present on 2026-10-11 at 03:17. Never put the token in a log, a comment, or a PR body.

```
npx wrangler deploy -c <path>/wrangler.toml
```

### 5.4 Two wrangler faults to know before you automate this

**`--define` does not work in wrangler 4.133.** It rejects every form, including `--define=FOO=bar`. It passes the raw text to esbuild. esbuild then fails. Use `--var` instead. `--var KEY:VALUE` merges with the `[vars]` table in the config. It does not replace the table.

**A build flag can hide a production flag.** `scripts/build-digiquant.sh` treats the value `CF_PAGES_BRANCH` of `develop` or `main` as production-grade. A local run has no `CF_PAGES_BRANCH` value. So a local build can take a different path than the Cloudflare build. Set the variable by hand when you need the production path. Check this before you trust a local build result.

### 5.5 The trigger

Three options. All three keep the deploy off GitHub Actions.

| Option | Trigger | Deploys on | Fits when |
|---|---|---|---|
| Manual | A person runs the script | the Mac | Chris alone deploys |
| Local watcher | A local `launchd` job watches the remote release branch | the Mac | The Mac is always on |
| Cloudflare Workers Builds | Cloudflare builds the Worker from the repository | Cloudflare | The Mac is sometimes off |

**Recommendation: manual first, then the local watcher.** The manual step is safe because a person approves it. The watcher removes that approval. Add the watcher only after a month of clean manual deploys.

**Fallback: Cloudflare Workers Builds.** This service builds a Worker from a connected repository. It uses Cloudflare's minutes, not GitHub's. Use it for a Worker that must deploy while the Mac is off. It does not support the container build the same way, so check a container Worker before you rely on it.

### 5.6 The two crons in `digithings-cron`

`apps/digithings-cron/wrangler.toml` declares 18 or more `crons` entries. For example: `40 13 * * MON-FRI`, `17 9 * * MON`, and `13 6 * * MON`. Cloudflare owns these. A local CI does not move them. A deploy of `digithings-cron` from the Mac keeps them. A `wrangler deploy` does not remove them. Do not edit the `[triggers]` block during the migration.

## 6. Proposal to stop Cloudflare from deploying from main

### 6.1 The mechanism

Cloudflare Pages holds a production branch value. When Cloudflare sees a push to that branch, it rebuilds. The value is `main` today. The value is not in the repository. `scripts/check_deploy_freshness.py` says this in its own words: the diagnosis is "answerable only in the Cloudflare dashboard". A change to that value needs a dashboard session.

The two Workers workflows use `push` to `main` in the repository. A change to that trigger is an ordinary file edit in the repository.

So the two halves of this proposal need different tools. The Pages half needs a dashboard session. The Workers half needs a pull request.

### 6.2 The steps

Each step is separate. Each step needs Chris's approval. Do the steps in order. Stop after any step that fails.

| Step | Action | Tool needed | Effect | Risk |
|---|---|---|---|---|
| 0 | Do nothing | none | sites keep building from `main` | none |
| 1 | Set the Pages production branch to `release/web` for both sites | Cloudflare dashboard | no site builds from `main` any more | a site stops building until step 2 |
| 2 | Move the build scripts and the site source into R3 and R4 | git, in the split | the branch exists | none, it is only a move |
| 3 | Point each Pages project at its new repository's `release/web` | Cloudflare dashboard | each site builds from its own repo | wrong repo gives a wrong site |
| 4 | Change `deploy-digithings-cron.yml` to `workflow_dispatch` | git | the Mac owns the cron deploy | a missed dispatch means no deploy |
| 5 | Delete `deploy-digiquant-runner.yml` | git | nothing | none. The lane is dead. See section 4.1 |

**Step 1 is the important step.** It stops both sites from building from `main` with one dashboard change each. Do step 1 only after step 2 has put `release/web` in existence. Otherwise the sites stop updating.

**Step 4 is safe to do first.** The workflow is a file in the repository. Change it to `workflow_dispatch` and the Mac owns the cron deploy. Do this before step 1 if you want one half of the migration to be reversible from git.

### 6.3 What each step does not fix

This proposal does not set up a local CI. Section 5 describes that as a design. Step 4 makes a manual Mac deploy necessary. The local watcher in section 5.5 makes it automatic.

This proposal does not move a repository. Section 2 and Table C name the destination. The move is a separate task.

This proposal does not change the cron triggers in `digithings-cron`. See section 5.6.

## 7. Decisions for Chris

### D-1. Which repo owns the corpus-index Worker?

This is the only unresolved item in Table A. The source exists and is in this repository. Section 2.3 has the evidence. The question is only which R repo the directory joins.

- **A.** R5 `digithings-stack`, with the other Workers. Its `wrangler.toml` names the same Cloudflare account.
- **B.** R2 `digiquant-stack`. Pull request #5545 titles the branch feature `digisearch`, so the owning seat may read it as a digisearch component.
- **C.** No repository. Keep it in Cloudflare only.
- **D.** R6 `digichat-tenants`. It binds a KV namespace for a corpus and reads the helpdesk token.

**My recommendation stays A, for one reason that is now sharper.** The two open pull requests disagree about who owns it. #5545 calls it `feat(digisearch)`. #5580 carries it inside a `feat(digichat)` branch. That disagreement is the reason to settle the owner in writing before the migration rather than during it.

### D-2. What are the two production Pages project names?

I could not read them. See section 3.1. I need the names to write the local `wrangler pages deploy` commands in section 3. The dashboard holds them.

### D-3. Who makes the dashboard change in step 1?

I have no write access to the Cloudflare dashboard. I have a read-only tool. Step 1 needs a person.

### D-4. Is the Mac always on?

The local watcher needs the Mac. The Cloudflare Workers Builds fallback needs the Mac to be off. This answer decides option 2 or option 3 in section 5.5.

### D-5. Which R0–R7 repo names do you accept?

Table A uses the repo names from the verified split plan at `develop@83a104a10`. That plan is dated 2026-10-14 at 02:49 CEST. Read `/Users/chrisstefan/Code/occ-backups/repo-split-docs/repo-split.md`. The names are R0 `digithings` (public), R1 `digiquant-strategies`, R2 `digiquant-stack`, R3 `digiquant-web`, R4 `digithings-web`, R5 `digithings-stack`, R6 `digichat-tenants`, R7 `twelve-x` (exists). The plan carries 14 open decisions of its own. I did not resolve them here.

## 8. Method and evidence

I read the live Cloudflare account with one read-only tool: `workers-list`. The tool returns the Worker name, the script ID, and the modified time. I did not call a write tool. The account is `ae2ea3eb4ce5f7cc9bec1478f6e60e15`. That value is in tracked wrangler files. It is not a secret.

I read the repository at `github/develop` = `d227b6ed5`. The 74 workflow files and the 8 wrangler.toml files are the whole input for section 4 and Table A. A control proved the search instrument works: 10 workflow files contain the word `wrangler`.

I also read the deployed script of `corpus-index` with a second read-only tool, `workers-get-worker-code`. Section 2.3 uses it. The first version of section 2.3 was wrong because the search covered one ref. A pickaxe over all refs, `git log --all -S<symbol>`, found the source in one call. An absence measured on one ref is an absence on that ref, not on the repository.

I could not read the Cloudflare Pages settings. No read-only Pages tool exists in the tool gateway. The Pages rows in Table B come from the two workflow headers and the two build scripts. **The Pages production branch and the Pages project names are not verified.** Section 3.1 and D-2 name this gap.

**How to run the local gate.** `scripts/check_doc_links.py` sets `REPO_ROOT` from its own location on line 12, not from the current directory. Run the copy inside the tree you are testing. Run the copy in another checkout and it scans that checkout instead, and the scanned file count differs: 398 files in this branch's worktree against 554 in the shared checkout. Both answers can be green at once.

I hit exactly that while proving this revision. A break planted in this file left the gate at exit code 0 and it never named the file. The plant only failed the gate when the gate ran from this worktree. **A green gate is a statement about the tree the script was loaded from.**

The pass recorded for this revision: exit code 0 with 398 markdown files scanned. Non-vacuity: a broken link planted inside this file makes the gate exit code 1 and name `docs/repo-split/cloudflare-deploy-map.md`. The file was restored byte-for-byte and the gate returned to exit code 0.

I did not run any deploy, and I did not run any dry run. Section 5 is a design, not a measurement. The Docker warning in section 5.2 and the `--define` fault in section 5.4 come from earlier measurements on this host. Check both again before you build the gate on them.

## 9. One-line summary

Six Workers map cleanly to R2 and R5, The sixth, `corpus-index`, has its source in this repository on two unmerged branches and on no trunk branch at all, both sites build from `main` on Cloudflare's side with no GitHub Actions workflow involved, and the only deploy lane that works today is one that pushes `main`. Moving both sites to a release branch is two dashboard changes and stops the auto-deploy.
