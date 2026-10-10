# config/contract/ — the single config contract (epic DIG-2758 §8)

One source of truth for services, ports, env, secrets, and bindings across
the self-hosted (compose) and hosted (Cloudflare) variants. Before this,
env names drifted across wrangler `[vars]`, compose `environment`, and
`.env.example` with no authority (plan §2.7).

## Files

- `variants.yaml` — variant identity (`DT_VARIANT` / `DT_TARGET` /
  `DT_BASE_URL`) + verified hosted routes. Nothing else defines these.
- `services.yaml` — prod inventory at base `develop@404b816c`: shared env
  (values verified in ≥1 artifact), compose port/profile table, worker
  binding table.
- `secrets.yaml` — secret NAMES, consumers, required-in, source. Values
  never enter this repo (plan §4).
- This README.

## Generators

`scripts/render_config_contract.py` (house `refresh_*` pattern):

- `make config-contract` — render. Updates marked blocks in place:
  - root `.env.example` (identity vars),
  - `[vars]` in the 5 wrangler.toml files that have one (hosted identity
    vars — INERT keys no code reads yet; zero behavior change),
  - `config/generated/compose-contract.env` (selfhost env set).
- `make config-contract-check` — network-free drift guard for CI (S9).

Marked blocks are delimited `# BEGIN/END config-contract`. Never hand-edit
inside them; edit the YAML and re-render.

## What S1 does NOT touch (sibling scope)

- `docker-compose.yml` service bodies — S4 wires `compose-contract.env`
  via `env_file` and owns all compose edits.
- `wrangler dev` / Miniflare / container shim — S3 reads `DT_VARIANT`
  from the contract blocks.
- Secret VALUES / Keychain render — S5 owns `dt secrets render`.
- Local Supabase values (`SUPABASE_URL` selfhost) — S2 fills the null.
- CI parity suite consuming `--check` — S9.
- Docs page (`docs/SELF_HOST.md`) — S10.

## Conventions

- All compose host binds are loopback (`127.0.0.1`); remote access is
  Tailscale/Cloudflare per SECURITY.md. The contract never introduces a
  non-loopback bind.
- `hosted` values appear ONLY where inventoried from prod `wrangler.toml`.
  `null` means "unknown here, do not guess" — the generator never emits
  nulls; the `--check` test fails a null that reaches an artifact.
- Brand: digithings (one word, lowercase) everywhere in generated text.
