# config/contract

Self-host stack contract: **services, ports, env, secrets, bindings** in one
source of truth, plus the generators and the acceptance check built on it.

Created by [DIG-2769](../../issues). Adding a wrangler var, a binding or a
compose interpolation without a contract entry is now a **CI failure**.

## Files

| file | role |
|---|---|
| `contract.yaml` | **source of truth.** Hand-maintained after the one-time bootstrap. |
| `bootstrap_contract.py` | one-time authoring aid that transcribed the mechanical half (which worker declares a var, which compose service interpolates a name). Not the authority; edit the YAML. |
| `generate.py` | emits `generated/wrangler.vars.<worker>.json`, `generated/compose.env`, `generated/env.example`. Deterministic. |
| `check_contract.py` | the acceptance check. `python3 config/contract/check_contract.py` |
| `generated/` | committed output, so a stale contract is visible in a diff. |

## The acceptance criterion

> every wrangler binding/var and compose env maps to the contract

`check_contract.py` reads the live repo — the 7 `apps/*/wrangler.toml`, the 2
compose files and the 2 `.env.example` files — and fails if any input has no
contract entry. It also fails if a contract env entry is claimed by no live
source, so the contract cannot rot in either direction.

**Prove it can fail.** `--self-test` runs the real check (must be green), then
injects a synthetic unmapped name into each of the four fact sources and
requires the check to turn red naming that name, then requires the tree to come
back clean:

```sh
python3 config/contract/check_contract.py --self-test
```

That is the whole point. A check that reports zero because it looks for zero is
not evidence.

## Two traps this already had to survive

- **Comments are not configuration.** `docker-compose.yml` carries a
  `${VAR:?}` *example inside a `#` comment*. Both scripts strip comments
  quote-aware before scanning, or the checker demands an entry for a variable
  that does not exist.
- **Interpolation nests.** `${DIGIKEY_LITELLM_PROXY_KEY:-${LITELLM_MASTER_KEY:-}}`
  means the operator can set either name. A non-greedy `[^}]*` stops at the
  inner brace and silently drops `LITELLM_MASTER_KEY` — a name that is then
  missing from `generated/compose.env` while still being required in practice.
  The generator counts braces and resumes the scan at the nested name.

## What the contract does not check

`wrangler.toml` does **not** declare secrets; Cloudflare holds them out of
band. The `secrets:` section is transcribed from the documented per-worker
checklists (`docs/ops/SECRETS_INVENTORY.md`, `docs/ops/digitrace-langfuse.md`,
and each `wrangler.toml` header) and is **not** machine-verified. Anything the
check covers, it covers mechanically; anything it does not, it says so rather
than implying coverage.

## Regenerating

```sh
python3 config/contract/generate.py          # refresh generated/
python3 config/contract/check_contract.py    # prove the contract still holds
```

The checked-in root `.env.example` is **not** overwritten by the generator: it
is hand-curated prose carrying security guidance (`DIGIKEY_ALLOW_EPHEMERAL_KEY=0`
is the production default, bind everything to 127.0.0.1) that a generator cannot
reproduce. Instead `generated/env.example` is the contract-derived skeleton and
the checker proves every **live** assignment in the hand-curated file maps to
the contract — a stronger property than regenerating it.
