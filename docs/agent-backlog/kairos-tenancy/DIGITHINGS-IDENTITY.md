# digithings credential identity

**Adopted 2026-08-30 — HUMAN OVERRIDE** (label **digithings**, not “cursor cloud agent”).
**Vendor email 2026-09-01 — HUMAN OVERRIDE:** `admin@digithings.ai` on Proton. No company Google account. No Agentmail for vendors.

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

## Vendor email (Proton `admin@digithings.ai`)

Google will not create a consumer account on `@digithings.ai` without Workspace.
Do **not** buy Workspace for vendor login. Do **not** Sign in with Google as the
company path.

The company mailbox is **`admin@digithings.ai`**, hosted on the owner’s **Proton**
account (domain already connected). Use that address on Stripe, Mailgun, X
(`@digithingsai`), Alpaca, and other vendor signups.

| Piece | Rule |
|-------|------|
| Email vendors see | `admin@digithings.ai` |
| Where mail lands | Proton (owner reads confirm codes / magic links) |
| How agents continue | Owner on the desktop for CAPTCHA / 2FA / Proton codes. Agents do not have Proton inbox access. |
| Never store | Proton password, Google password, 2FA seeds, or recovery codes in GitHub Secrets or `.local/secrets/` |
| Do store | API keys / OAuth client secrets / webhook secrets in GitHub Secrets + `.local/secrets/digithings-*.env` |

**Personal Google** (`chris.stefan00@gmail.com` and the existing Cloud / Supabase
org owner) stays the **human owner** of Google Cloud, GitHub `digithings-ai`, and
Supabase **until** the owner adds `admin@digithings.ai` as an owner and transfers
those orgs to the company. That transfer is a later hop — do not do it from this
doc.

**X:** keep `@digithingsai`. Set its email to `admin@digithings.ai`. Do not
require a company Google account.

## Agentmail — not for vendor accounts

Do **not** create Stripe, Mailgun, Alpaca, X, or Google Cloud logins as
`digithings@agentmail.to` or `cursor-cloud-agent6060@agentmail.to`. No vendor
accounts were completed on those addresses; do not start any.

Agentmail inboxes may still exist. Leave them unused for vendor signup. Do not
delete them unless the owner asks. Do not fill vendor forms with `@agentmail.to`.

`kairos-e2e-*@agentmail.to` addresses in tests are **app** fixtures, not vendor
identity.

Visual design references to [agentmail.to](https://www.agentmail.to) in digiweb
are unrelated.
