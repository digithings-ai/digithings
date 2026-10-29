# ${REPO_NAME}

Private repo for one digithings client. It holds only the client's data and
tooling (tenant config, tools, skills, corpus, QA set, deploy script) and
consumes digithings (R0) at the versions pinned in [`digithings.lock`](digithings.lock).

Created from the Forgejo template repo `clients/client-template`. Agent rules:
[AGENTS.md](AGENTS.md). Client facts: [client/profile.md](client/profile.md).

## Layout

```
AGENTS.md            agent rules for this client (CLAUDE.md is a symlink)
VERSION, CHANGELOG.md  release version; tags are ${REPO_NAME}-vX.Y.Z
client/              profile.md, scope.md, decisions.md, comms/ (references only)
tenant/              digichat.yaml (one deployment doc), corpus-map.json, env/{local,staging,prod}.yaml,
                     SCHEMA-NOTES.md (server-only access.invite, pathPrefix rules, fail closed)
tools/               site-graph/, skills/<skill>/SKILL.md, mcp/<server>/
corpus/              crawled public pages (markdown with url: front matter) + manifest
deploy/              deploy.sh and its README (what each step touches, rollback)
compose/             docker-compose.yml (pinned R0 images) + docker-compose.dev.yml (build from ../digithings)
digithings.lock      the ONE pin file for R0
scripts/             env.sh, check_lock.sh, check_no_vendored_r0.py (CI: no file copied from R0)
tests/               schema test, questions.json, run_qa.sh, tools/ unit tests, ci/ (CI script + make bump tests)
.woodpecker.yml      Forgejo CI, owned by QA: lock, gitleaks, fetch pinned R0, no-vendored-r0, make test + tests/ci
.env.example         variable names only
Makefile             up / dev / link / unlink / bump / test / qa / release / deploy-staging / deploy-prod
```

## Run it locally

```bash
cp .env.example .env          # fill values from your own keychain; .env is gitignored
make link DIGITHINGS_DIR=../digithings   # optional: work against a local R0 checkout
make test                     # offline: schema + corpus + tool tests, no model calls
make up                       # pinned R0 images with tenant/, tools/, corpus/ mounted
make dev                      # same, but images built from ../digithings
make qa QID=Q1                # one golden question on a free model; stops on the first 429 round
```

## Release and deploy

- `make bump SHA=<sha>` re-pins `digithings.lock` to an R0 develop sha and runs `make test`.
- `make release` bumps `VERSION` and `CHANGELOG.md` and prints the tag-and-push command.
  The owner cuts and signs the tag, then pushes `main` and tags to the private
  GitHub backup (owner only; agents never push `github`).
- `make deploy-staging` / `make deploy-prod` are **stubs that refuse** in the
  template. A client repo wires `deploy/deploy.sh` once a scoped Cloudflare token
  exists. Prod needs a signed tag.

## Starting a new client from this template

1. On Forgejo: **New repository → from template `clients/client-template`**, name it
   `client-<slug>` in the `clients` org, private, with "git content" and "template
   expansion" ticked (`.forgejo/template` lists the expanded files).
2. Fill `client/profile.md` and `client/scope.md`; log the first decisions.
3. Replace the `example` tenant in `tenant/` (slug, host, skin, accent), the site graph,
   the corpus and `tests/questions.json`.
4. Pin `digithings.lock` to a commit on R0 `develop` and run `make test`.
5. Add the private GitHub backup remote as `github` (owner only, at the first release).

A `make new-client` helper that asks for the slug, domain and skin is planned; until
then, do steps 2–3 by hand.
