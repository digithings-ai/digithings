# GitHub Auth — prod proof (2026-08-30T21:18Z)

**Verdict:** GitHub Olympus login **proven** on digiquant.io / Supabase `core`. Goal still **incomplete** (vendors + staging E2E).

Identity: **digithings** · PAT label: **digithings** · Project: `rwagjbkvxkdwqmouagad`  
#3183 left draft · cutover 900 **not** applied · no bootstrap deploy needed

## Unauth smoke

- `GET https://digiquant.io/olympus/login` → **308** → `/olympus/login/` **200**
- HTML: "Continue with Google", "Continue with GitHub" (no email/password fields)
- Artifact: `/opt/cursor/artifacts/olympus-login-smoke.html`

## `auth.users` (names/ids only — no passwords/tokens)

| id | email | provider | github_login | created_at (UTC) | last_sign_in_at |
|----|-------|----------|--------------|------------------|-----------------|
| `4e4ad288-ec6e-4608-b821-bd5f515fcd15` | kairos-e2e-1788116787@agentmail.to | email | — | 19:06:28 | 20:23:37 |
| `0408ba97-caba-44d3-b2d0-5690ab5160a9` | chris.stefan@proton.me | **github** | chrizefan | **21:14:44** | **21:15:48** |

Count: **2** · identities: email + github

## Personal workspace (mig 107)

Trigger `on_auth_user_created_ensure_workspace` **enabled**. Function `ensure_personal_workspace` present.

| workspace_id | slug | name | type | plan_tier | role | user |
|--------------|------|------|------|-----------|------|------|
| `4700ff6e-20cb-454e-ba3d-c6427980c856` | `u-0408ba97caba44d3b2d05690ab5160a9` | Personal | user | **free** | owner | github user above |
| `adeb7c87-29ed-41be-8b86-6afd8407b6a0` | `u-4e4ad288ec6e4608b821bd5f515fcd15` | Personal | user | custom | owner | email e2e user |

GitHub user's workspace `created_at` matches user insert → trigger fired. **bootstrap_fix_needed: false**

## Authenticated browser (agent desktop)

Tab left open at Olympus (did not disturb sibling Stripe/Mailgun/Alpaca tabs):

- Sidebar: `chris.stefan@proton.me` + Sign out
- `/olympus/` Morning brief shell
- `/olympus/settings/`: Settings UI; Data source `rwagjbkvxkdwqmouagad.supabase.co`
- Screenshots: `olympus-github-session-home.png`, `olympus-github-settings-authed.png`

## Staging E2E next

Still blocked until Stripe / Mailgun / Alpaca (and optional Google) secrets land after human captchas.
