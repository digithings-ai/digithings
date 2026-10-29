# Agent instructions: ${REPO_NAME}

This private repo holds everything client-specific for one client of digithings:
its tenant config, tools, skills, corpus, QA set and deploy script. The product
code is **not** here. It comes from the public digithings repo (R0) at the
version pinned in [`digithings.lock`](digithings.lock).

## 1. Who the client is and what we are building

- Client: `<client name>` (one line). Facts: [client/profile.md](client/profile.md).
- Demo or project scope, requirements and status: [client/scope.md](client/scope.md).
- Decisions so far: [client/decisions.md](client/decisions.md).

## 2. Build on digithings, never copy it

- Never copy R0 (or any other open-source) code into this repo, not even one file.
  CI refuses vendored R0 files.
- If this client needs a new mechanism, build it **generically** in R0 first: an R0
  pull request through digiforge, with `example.com` fixtures and no client name.
  When it lands, bump `digithings.lock` here (`make bump`, or by hand) and use it.
- During development, `make link` points this repo at a local R0 checkout;
  `make unlink` restores the pins. Never commit a linked state.

## 3. What may be customised here

- Tenant config (`tenant/digichat.yaml`): a **prebuilt skin** from R0, colours
  (palette, accent) and fonts only. No custom CSS, no forked components.
- Tools (`tools/site-graph/`, `tools/mcp/`), skills (`tools/skills/`), corpus (`corpus/`).
- Any other UI or behaviour change is upstream work in R0 (see 2).

## 4. Data rules

- Public pages only, unless the client has provided data in writing (record it in
  `client/decisions.md`).
- No secrets, tokens or keys in any file. `.env.example` and `tenant/env/*.yaml`
  hold variable **names** only; values come from the operator's keychain.
- No personal data in tests, fixtures or screenshots. Contacts go in
  `client/profile.md` **by role**, not by name.
- QA runs (`make qa`) use free models only and stop at the first rate-limit round.
  Never switch to a paid model without the owner's go.

## 5. Remotes

- `origin` = Forgejo (`clients/${REPO_NAME}`). All daily work: branch, pull request,
  Woodpecker checks, review, merge to `main`.
- `github` = private backup on GitHub. Pushed **only** by `make release`, never by hand.

## 6. Deploys

- `make deploy-staging`: agents may run it only where the owner allows staging deploys
  for this client (recorded in `client/decisions.md`).
- `make deploy-prod`: only from a release tag `${REPO_NAME}-vX.Y.Z` cut and **signed**
  by the owner. Agents never cut or sign tags.
- A deploy writes this client's tenant doc to KV, its seeds and skills to R2, and
  (optionally) its own `${REPO_NAME}-*` Workers. It never redeploys the shared stack.

## 7. Org operating rules

The digithings org rules apply here by reference: the R0 `AGENTS.md` and
`CONTRIBUTING.md` (branching, review, no force-push, lowercase `digi*` names,
no secrets in logs). Where this file is stricter, this file wins.
