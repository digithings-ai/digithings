# digithings credential identity

**Adopted 2026-08-30 — HUMAN OVERRIDE** (label **digithings**, not “cursor cloud agent”).
**Vendor login 2026-09-01 — HUMAN OVERRIDE:** company Google, not Agentmail.

Vendor accounts, Supabase PATs, Cursor environment secret labels, and local
`.local/secrets/` filenames for this repo are branded **digithings**.

| Rule | Value |
|------|-------|
| Identity | **digithings** (lowercase) |
| Ownership | Repo / org — global for all digithings agents |
| PAT / env label | `digithings` |
| Local files | `.local/secrets/digithings-*` (gitignored) |
| Do not use | `cursor-cloud-agent-*` or “cursor cloud agent” as credential labels |

Cursor Cloud Agent (`exec:cursor`) remains the **execution-tier** name only.

When pasting `SUPABASE_ACCESS_TOKEN` into the Cursor env store, label it
**digithings**.

## Vendor login (company Google)

Product vendor consoles (Stripe TEST, Mailgun, X developer, Alpaca, etc.) use a
**Google account whose email is `admin@digithings.ai`**, not a personal Gmail
and not Agentmail.

| Piece | Rule |
|-------|------|
| Email vendors see | `admin@digithings.ai` |
| How agents continue | Owner signs into that Google account **on the desktop** (2FA / CAPTCHA). The agent then uses **Sign in with Google** in the same browser session. |
| Never store | Google password, 2FA seeds, or recovery codes in GitHub Secrets or `.local/secrets/` |
| Do store | API keys / OAuth client secrets / webhook secrets in GitHub Secrets + `.local/secrets/digithings-*.env` |
| Human still owns | Google Cloud org, GitHub `digithings-ai`, Supabase org, Stripe KYC — a person (Chris), not a shared mailbox as the only recovery |

Not every vendor has Google SSO (Alpaca often does not). Those still get
`admin@digithings.ai` as the account email; the owner completes CAPTCHA on the
desktop.

**X:** keep the `@digithingsai` user. Link it to the `admin@digithings.ai`
Google account (Continue with Google) instead of creating a second X app on a
personal handle.

## Agentmail — not for vendor accounts

Do **not** create Stripe, Mailgun, Alpaca, X, or Google Cloud logins as
`digithings@agentmail.to` or `cursor-cloud-agent6060@agentmail.to`. No vendor
accounts were completed on those addresses; do not start any.

Agentmail inboxes may still exist. Leave them unused for vendor signup. Do not
delete them from this hop unless the owner asks. Do not fill vendor forms with
`@agentmail.to`.

`kairos-e2e-*@agentmail.to` addresses in tests are **app** fixtures, not vendor
identity.

Visual design references to [agentmail.to](https://www.agentmail.to) in digiweb
are unrelated.
