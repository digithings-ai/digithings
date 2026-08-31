# digithings credential identity

**Adopted 2026-08-30 — HUMAN OVERRIDE.**

Vendor accounts, Supabase PATs, Cursor environment secret labels, and local
`.local/secrets/` filenames for this repo are branded **digithings** — not
“cursor cloud agent”.

| Rule | Value |
|------|-------|
| Identity | **digithings** (lowercase) |
| Ownership | Repo / org — global for all digithings agents |
| PAT / env label | `digithings` |
| Local files | `.local/secrets/digithings-*` (gitignored) |
| Do not use | `cursor-cloud-agent-*` or “cursor cloud agent” as credential labels |

Cursor Cloud Agent (`exec:cursor`) remains the **execution-tier** name only.
Full convention + rename-after notes (no secrets):
`/opt/cursor/artifacts/kairos-DIGITHINGS-IDENTITY.md`.

When pasting `SUPABASE_ACCESS_TOKEN` into the Cursor env store, label it
**digithings**. Vendor signup under the old name is paused until parent
resumes under digithings.
