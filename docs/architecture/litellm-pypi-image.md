# LiteLLM: digithings image from the PyPI wheel

**Status:** implemented (DIG-1780) · **Decided:** 2026-10-07 · **Owner:** DevOps

## Why

Counsel reviewed four OSS dependencies on [DIG-1768](https://github.com/digithings-ai/digithings/issues/1768).
Chris answered both questions put to him and ratified a red line:

> LiteLLM from the Python package repository only, never the official Docker image.

The reason is the licence, not preference. BerriAI publishes a second licence,
`enterprise/LICENSE.md`, covering the `enterprise/` tree that their container image
deliberately bundles:

> This software and associated documentation files (the "Software") may only be used in
> production, if you (and any entity that you represent) have agreed to, and are in
> compliance with, the BerriAI Subscription Terms of Service … and otherwise have a
> valid BerriAI Enterprise license for the correct number of user seats.
>
> Notwithstanding the foregoing, you may copy and modify the Software for development
> and testing purposes, without requiring a subscription.

So a local `docker compose` stack was **licensed**. A production gateway was **not**.
That asymmetry is what set the order of work: establish exposure first, because it
decides whether this is a refactor or an incident.

## Exposure finding (AC1)

**No deployment of ours ran the vendor image as the live gateway.** The deployed
Profile A stack is `apps/digithings-stack-cloudflare`, and `Dockerfile.digithings-stack-cloudflare`
installs `litellm[proxy]==1.72.6` from PyPI and runs it under supervisord. It was
already compliant; the red line was crossed only in two tracked compose files, one of
which (`infra/digichat-release/compose.profile-a.yml`) ships to external self-host
operators.

One board-level question was raised to CTO on DIG-1780 and is **not** answered by this
document: has any external environment actually installed Profile A? If yes, we handed
an operator an artifact that instructs production use of a dev/test-licensed image,
and that is an unlicensed-use question for the board, not an engineering fix.

## What we build

[`Dockerfile.litellm`](../../../Dockerfile.litellm) builds from the PyPI wheel, pinned
to `litellm[proxy]==1.72.6` — the same pin the deployed stack uses, so the self-host
image and production cannot drift on the one dependency they share.

The pin is not the interesting part. The interesting part is that the build
**asserts its own compliance**:

- [`scripts/verify_litellm_no_enterprise.py`](../../../scripts/verify_litellm_no_enterprise.py)
  runs as a `RUN` step. It fails the build if a `litellm-enterprise` distribution is
  installed, if an `enterprise/` directory is importable from any `sys.path` entry, or
  if `<app>/enterprise` exists. A dirty image cannot be built, so it cannot be pushed.
- [`scripts/check_litellm_vendor_boundary.sh`](../../../scripts/check_litellm_vendor_boundary.sh)
  fails CI if a vendor image reference reappears in any tracked file, and if any
  litellm image reference is not tagged with exactly that pin.

The `sys.path` check is the load-bearing one. Upstream resolves
`enterprise.enterprise_hooks` **by source path**, not through an installed
distribution — upstream's own Dockerfile comment says so. A stray `enterprise/`
directory is therefore sufficient to restore production use with no enterprise wheel
present anywhere, which is exactly the state a "we installed from PyPI, we're fine"
check would wave through.

## The functional gap, stated plainly

Exactly three production files in the MIT tree import from `enterprise`. The cost of
leaving it out:

| Behaviour | Without `enterprise/` |
|---|---|
| Proxy startup, routing, budgets, keys, `/customer/new\|info\|update\|delete\|list\|daily/activity` | works |
| `/customer/block`, `/end_user/block` | **works** — writes `blocked: true` directly to the DB |
| `/customer/unblock`, `/end_user/unblock` | **HTTP 400** — `"Blocked user check was never set. This call has no effect."` |
| Enterprise proxy hooks | degrades to an empty set, no error |
| OpenAI / Google Text Moderation guardrails | raises a clear exception **only if configured** — we configure neither |

### Decision on end-user unblock: **explicitly accepted as absent**

Not implemented. Three reasons:

1. **No caller.** `git grep` finds no caller of `/customer/unblock` or
   `/end_user/unblock` anywhere in this repo, and neither endpoint is in any
   documented API surface. The capability is absent from what we build, not broken.
2. **The blast radius is one DB column.** `unblock_user` writes the same row `block_user`
   writes. Reimplementing it is a small endpoint, not a subsystem — which means it can
   be added later, on demand, with a real caller to design against, without guessing.
3. **Shipping a reimplementation of a licensed endpoint is the riskier choice.** The
   call is refused loudly (HTTP 400) rather than silently doing something subtly
   different from upstream. A caller that needed it would have hit that refusal and
   raised it, instead of inheriting a divergence we wrote ourselves and did not test
   against upstream.

**Caller impact, stated for the record:** an operator who today calls
`/customer/unblock` against a Profile A install gets HTTP 400 and a message that says
the call has no effect. They do not get a silent no-op and they do not get a partial
write. Blocking still works, so the moderation path is intact in one direction.

If a caller appears, the fix is a small endpoint in the digithings stack, tracked as a
new issue — not a reason to carry the vendor image.

## Enforcement

| Guard | Where |
|---|---|
| Build fails if the image would carry proprietary code | `Dockerfile.litellm` `RUN` step |
| CI fails if a vendor image reference reappears | `scripts/check_litellm_vendor_boundary.sh`, wired into the `ruff-and-scripts` job |
| CI fails if a litellm image tag is not the exact pin | same script |
| Licence text recorded | [`THIRD_PARTY_NOTICES`](../../../THIRD_PARTY_NOTICES) |

### Known blind spot

`.gitignore:41` ignores `/projects/*`, so `projects/sitaas/docker-compose.yml` — which
carried the vendor-published image (BerriAI namespace, `litellm`, moving `:main-latest`
tag) — is invisible to `git grep`, to this gate, and to **every other boundary check in
this repo**. It was fixed on disk; it cannot land in a commit and cannot be gated.
Closing that hole is separate work.

This gate also covers its own regression suite: the test file builds the forbidden image
reference from string parts rather than writing it literally, so `git grep` for the
reference returns nothing even there. A gate that had to be exempted from itself would
leave the grep in the acceptance criterion permanently red.

The gate also permits two named exceptions, `scripts/provider_review/bootstrap.py` and
`docs/superpowers/plans/2026-05-01-provider-review.md`. Both fetch upstream source over
HTTPS for the licence review and are not image pulls. The exception is conditional on
the matched line containing `raw.githubusercontent.com`, so an image pull cannot be
smuggled into an allowlisted file and inherit the exemption.

## Bumping the pin

1. Change `ARG LITELLM_VERSION` in `Dockerfile.litellm`.
2. Change `LITELLM_VERSION` in `scripts/check_litellm_vendor_boundary.sh` in the same
   commit — the gate fails if they disagree.
3. Change the three compose tags (`docker-compose.yml`,
   `infra/self-host/compose.ghcr.yml`, `infra/digichat-release/compose.profile-a.yml`).
   The gate fails if any of them still carries the old tag.
4. `docker build -f Dockerfile.litellm -t digi-litellm:<new> .` and smoke-test a
   completion through `config/litellm.yaml` before publishing.

`fastapi` stays on a ceiling rather than a pin: litellm 1.72.x calls fastapi internals
that 0.116 removed. Lifting it needs a litellm bump and a proxy smoke test, together.

## Publishing

The image is published to `ghcr.io/digithings-ai/litellm`. Note that
`publish-service-images.yml` and `publish-digichat-image.yml` were **deleted on
`develop` by #4919** (the 2026-10-01 Actions-budget cut, a Chris-approved human gate),
so no workflow on `develop` re-publishes on merge. Until that gate is revisited, the
image is built and pushed by hand:

```bash
docker build -f Dockerfile.litellm -t ghcr.io/digithings-ai/litellm:<version> .
docker push ghcr.io/digithings-ai/litellm:<version>
```

A `write:packages` credential is required. The compose files reference the exact
version tag; for a production operator, pin the digest instead.
