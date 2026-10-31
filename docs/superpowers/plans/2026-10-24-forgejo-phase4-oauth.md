# Forgejo Phase 4: OAuth 2 Applications for Paperclip and sctl

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create and validate Forgejo OAuth 2 applications for Paperclip (`paperclip-local`) and the sctl CLI (`sctl-local`), and document how agents and services authenticate to Forgejo via OAuth.

**Architecture:** Forgejo acts as the OAuth 2 / OIDC provider on `http://localhost:3000`. OAuth apps are registered per-user under the admin account `sctl` via `POST /api/v1/user/applications/oauth2`. Paperclip uses a confidential client with an authorization-code flow and a fixed callback URL; sctl uses a public client with PKCE and a loopback redirect (any port). Tokens are JWTs (1h access, refresh token). Scopes are not implemented in Forgejo, so each app's effective permissions equal the registering user's (`sctl` = admin) — use dedicated least-privilege service users where possible and treat client secrets as full-access credentials.

**Tech Stack:** Forgejo 17.0.0 (Gitea 1.22 base), curl, jq, bash, Paperclip (localhost:3100), sctl CLI.

**Spec:** `docs/plans/forgejo-full-setup.md` (Phase 6: OAuth 2 Applications; "Remaining Phases" lists "Phase 4: OAuth 2 apps (Paperclip integration)").

## Global Constraints

- Forgejo base URL: `http://localhost:3000` (LAN: `http://192.168.1.35:3000`). All OAuth endpoints are under this origin.
- Admin user: `sctl`; org: `digithings-ai` (id=4). Existing OAuth app: `woodpecker-local` (redirect `http://localhost:8000/authorize`).
- API auth: `Authorization: token <PAT>` (Forgejo PAT). PATs live in `~/.config/digithings/forgejo-tokens/*.token` and `local-forge.env`.
- Secrets must never be committed. Client secrets are shown only once at creation — capture to a 600-mode file or Bitwarden immediately.
- Do not print secrets in logs, PRs, or chat. Read token values in-process.
- OAuth scopes are not implemented; tokens carry the registering user's full rights.
- Public (PKCE) clients use loopback IP redirect URIs (`http://127.0.0.1/...`), not `localhost`, per RFC 8252.
- Callback URLs must exactly match the registered `redirect_uris` entry (including path and, for non-loopback, port).

---

## File Structure

- Create: `docs/ops/forgejo-oauth.md` — operator runbook: endpoints, apps, flows, agent auth guidance.
- Create: `scripts/verify-forgejo-oauth.sh` — smoke test for discovery, authorize redirect, token exchange, userinfo.
- Modify: `docs/plans/forgejo-full-setup.md` — mark OAuth apps complete in "Completed" section.
- Create (gitignored, 600): `~/.config/digithings/forgejo-oauth/paperclip-local.env`, `sctl-local.env` — client credentials (never committed).
- Optional: `docs/ops/forgejo-oauth-callback-example.md` — reference callback handler pseudo-code.

---

### Task 1: Unblock admin authentication and capture a working PAT

**Files:**
- Read/verify: `~/.config/digithings/forgejo-tokens/chris.token`
- Create: `~/.config/digithings/forgejo-tokens/sctl.token` (if missing)

**Interfaces:**
- Produces: a working admin PAT in `FORGEJO_TOKEN` / `~/.config/digithings/forgejo-tokens/sctl.token` that returns 200 from `/api/v1/user`.
- Consumes: `local-forge.env` (`FORGEJO_ADMIN_USER=sctl`, `FORGEJO_ADMIN_PASSWORD`).

- [ ] **Step 1: Verify current token health**

```bash
FORGEJO_URL=http://localhost:3000
for f in /Users/chrisstefan/.config/digithings/forgejo-tokens/*.token; do
  T=$(cat "$f"); code=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: token $T" "$FORGEJO_URL/api/v1/user")
  echo "$(basename "$f") -> $code"
done
```

Expected: at least one `200`. If all return `403` with "You must change your password", proceed to Step 2.

- [ ] **Step 2: Change expired passwords via the web UI (manual, one-time)**

Open `http://localhost:3000/user/login`, sign in as `sctl` with `FORGEJO_ADMIN_PASSWORD`, follow the forced password-change prompt, set a new password, then generate a fresh PAT at `http://localhost:3000/user/settings/applications` (scopes: all / admin). Save it:

```bash
install -d -m 700 /Users/chrisstefan/.config/digithings/forgejo-tokens
printf '%s' '<NEW_SCTL_PAT>' > /Users/chrisstefan/.config/digithings/forgejo-tokens/sctl.token
chmod 600 /Users/chrisstefan/.config/digithings/forgejo-tokens/sctl.token
```

- [ ] **Step 3: Verify the new admin token**

```bash
FORGEJO_URL=http://localhost:3000
T=$(cat /Users/chrisstefan/.config/digithings/forgejo-tokens/sctl.token)
curl -s -H "Authorization: token $T" "$FORGEJO_URL/api/v1/user" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('login=',d.get('login'),'id=',d.get('id'),'is_admin=',d.get('is_admin'))"
```

Expected: `login= sctl id= 1 is_admin= True`.

- [ ] **Step 4: Commit (docs only, no secrets)**

```bash
git add docs/plans/forgejo-phase4-oauth.md
git commit -m "docs(forgejo): add phase 4 oauth plan prerequisites"
```

---

### Task 2: Baseline — enumerate existing OAuth 2 applications

**Files:**
- Modify: `docs/ops/forgejo-oauth.md` (append inventory table)

**Interfaces:**
- Consumes: admin PAT.
- Produces: list of existing apps (`woodpecker-local`) with id, client_id, redirect_uris, confidential_client.

- [ ] **Step 1: List apps via API**

```bash
FORGEJO_URL=http://localhost:3000
T=$(cat /Users/chrisstefan/.config/digithings/forgejo-tokens/sctl.token)
curl -s -H "Authorization: token $T" \
  "$FORGEJO_URL/api/v1/user/applications/oauth2?page=1&limit=50" \
  | python3 -m json.tool
```

Expected: JSON array including `woodpecker-local` with `redirect_uris: ["http://localhost:8000/authorize"]`.

- [ ] **Step 2: Record baseline in runbook**

Append to `docs/ops/forgejo-oauth.md`:

```markdown
## Existing applications (baseline, 2026-10-24)

| Name | ID | Client ID | Confidential | Redirect URIs |
|---|---|---|---|---|
| woodpecker-local | <id> | <client_id> | true | http://localhost:8000/authorize |
```

Fill `<id>` and `<client_id>` from Step 1 output.

- [ ] **Step 3: Commit**

```bash
git add docs/ops/forgejo-oauth.md
git commit -m "docs(forgejo): baseline oauth2 app inventory"
```

---

### Task 3: Create `paperclip-local` OAuth 2 application (confidential client)

**Files:**
- Create: `~/.config/digithings/forgejo-oauth/paperclip-local.env` (600, gitignored)
- Modify: `docs/ops/forgejo-oauth.md`

**Interfaces:**
- Consumes: admin PAT, Paperclip callback URL `http://localhost:3100/oauth/callback`.
- Produces: `FORGEJO_OAUTH_CLIENT_ID`, `FORGEJO_OAUTH_CLIENT_SECRET` for Paperclip.

- [ ] **Step 1: Create the application**

```bash
FORGEJO_URL=http://localhost:3000
T=$(cat /Users/chrisstefan/.config/digithings/forgejo-tokens/sctl.token)
resp=$(curl -s -w "\n%{http_code}" -X POST \
  -H "Authorization: token $T" \
  -H "Content-Type: application/json" \
  -d '{"name":"paperclip-local","confidential_client":true,"redirect_uris":["http://localhost:3100/oauth/callback"]}' \
  "$FORGEJO_URL/api/v1/user/applications/oauth2")
echo "$resp"
```

Expected: HTTP 201 with JSON containing `id`, `client_id`, `client_secret`, `confidential_client: true`, `redirect_uris: ["http://localhost:3100/oauth/callback"]`.

- [ ] **Step 2: Persist credentials (secret shown once)**

```bash
install -d -m 700 /Users/chrisstefan/.config/digithings/forgejo-oauth
cat > /Users/chrisstefan/.config/digithings/forgejo-oauth/paperclip-local.env <<'EOF'
FORGEJO_OAUTH_CLIENT_ID=<client_id from Step 1>
FORGEJO_OAUTH_CLIENT_SECRET=<client_secret from Step 1>
FORGEJO_OAUTH_REDIRECT_URI=http://localhost:3100/oauth/callback
FORGEJO_OAUTH_AUTHORIZE_URL=http://localhost:3000/login/oauth/authorize
FORGEJO_OAUTH_TOKEN_URL=http://localhost:3000/login/oauth/access_token
FORGEJO_OAUTH_USERINFO_URL=http://localhost:3000/login/oauth/userinfo
FORGEJO_OAUTH_OIDC_DISCOVERY=http://localhost:3000/.well-known/openid-configuration
EOF
chmod 600 /Users/chrisstefan/.config/digithings/forgejo-oauth/paperclip-local.env
```

Replace `<client_id>` and `<client_secret>` with the values from Step 1 (do not paste into chat or commit).

- [ ] **Step 3: Verify the app is retrievable**

```bash
FORGEJO_URL=http://localhost:3000
T=$(cat /Users/chrisstefan/.config/digithings/forgejo-tokens/sctl.token)
APP_ID=<id from Step 1>
curl -s -H "Authorization: token $T" \
  "$FORGEJO_URL/api/v1/user/applications/oauth2/$APP_ID" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('name=',d['name'],'confidential=',d['confidential_client'],'redirects=',d['redirect_uris'])"
```

Expected: `name= paperclip-local confidential= True redirects= ['http://localhost:3100/oauth/callback']`.

- [ ] **Step 4: Document in runbook**

Append to `docs/ops/forgejo-oauth.md`:

```markdown
## paperclip-local (confidential client)

- Registered user: `sctl`
- Redirect URI: `http://localhost:3100/oauth/callback`
- Flow: Authorization Code (confidential, client_secret in Paperclip secrets store)
- Credentials: `~/.config/digithings/forgejo-oauth/paperclip-local.env` (600)
- Discovery: `http://localhost:3000/.well-known/openid-configuration`
```

- [ ] **Step 5: Commit**

```bash
git add docs/ops/forgejo-oauth.md
git commit -m "docs(forgejo): register paperclip-local oauth2 app"
```

---

### Task 4: Create `sctl-local` OAuth 2 application (public client, PKCE)

**Files:**
- Create: `~/.config/digithings/forgejo-oauth/sctl-local.env` (600, gitignored)
- Modify: `docs/ops/forgejo-oauth.md`

**Interfaces:**
- Consumes: admin PAT.
- Produces: `FORGEJO_OAUTH_CLIENT_ID` for sctl (no secret — public client).

- [ ] **Step 1: Create the application**

```bash
FORGEJO_URL=http://localhost:3000
T=$(cat /Users/chrisstefan/.config/digithings/forgejo-tokens/sctl.token)
resp=$(curl -s -w "\n%{http_code}" -X POST \
  -H "Authorization: token $T" \
  -H "Content-Type: application/json" \
  -d '{"name":"sctl-local","confidential_client":false,"redirect_uris":["http://127.0.0.1:7890/oauth/callback"]}' \
  "$FORGEJO_URL/api/v1/user/applications/oauth2")
echo "$resp"
```

Expected: HTTP 201 with `confidential_client: false`, `client_secret` empty/omitted, `redirect_uris: ["http://127.0.0.1:7890/oauth/callback"]`.

Note: because the redirect host is a loopback IP, Forgejo also accepts any port on `127.0.0.1` for this client; the fixed port above is the sctl default.

- [ ] **Step 2: Persist client id**

```bash
install -d -m 700 /Users/chrisstefan/.config/digithings/forgejo-oauth
cat > /Users/chrisstefan/.config/digithings/forgejo-oauth/sctl-local.env <<'EOF'
FORGEJO_OAUTH_CLIENT_ID=<client_id from Step 1>
FORGEJO_OAUTH_REDIRECT_URI=http://127.0.0.1:7890/oauth/callback
FORGEJO_OAUTH_AUTHORIZE_URL=http://localhost:3000/login/oauth/authorize
FORGEJO_OAUTH_TOKEN_URL=http://localhost:3000/login/oauth/access_token
EOF
chmod 600 /Users/chrisstefan/.config/digithings/forgejo-oauth/sctl-local.env
```

- [ ] **Step 3: Document in runbook**

Append to `docs/ops/forgejo-oauth.md`:

```markdown
## sctl-local (public client, PKCE)

- Registered user: `sctl`
- Redirect URI: `http://127.0.0.1:7890/oauth/callback` (loopback; any port accepted)
- Flow: Authorization Code + PKCE (no client secret)
- Credentials: `~/.config/digithings/forgejo-oauth/sctl-local.env` (600)
- Used by: `sctl` CLI login and git credential helper.
```

- [ ] **Step 4: Commit**

```bash
git add docs/ops/forgejo-oauth.md
git commit -m "docs(forgejo): register sctl-local oauth2 app (pkce)"
```

---

### Task 5: Test the confidential-client (Paperclip) OAuth flow end-to-end

**Files:**
- Create: `scripts/verify-forgejo-oauth.sh`
- Modify: `docs/ops/forgejo-oauth.md`

**Interfaces:**
- Consumes: paperclip-local client_id/secret, admin session for consent.
- Produces: verified authorize → code → token → userinfo round-trip.

- [ ] **Step 1: Source credentials and print authorize URL (no secret in URL)**

```bash
set -a; . /Users/chrisstefan/.config/digithings/forgejo-oauth/paperclip-local.env; set +a
STATE=$(python3 -c "import secrets;print(secrets.token_urlsafe(24))")
echo "Open this URL in a browser signed in as the target user:"
echo "http://localhost:3000/login/oauth/authorize?client_id=${FORGEJO_OAUTH_CLIENT_ID}&redirect_uri=$(python3 -c "import urllib.parse,os;print(urllib.parse.quote(os.environ['FORGEJO_OAUTH_REDIRECT_URI'],safe=''))")&response_type=code&state=${STATE}"
echo "STATE=${STATE}" > /tmp/oauth-state.env
```

Expected: a URL. Visiting it (while logged in as the consenting user, e.g. `chris` or `paperclip-bot`) shows the consent screen, then redirects to `http://localhost:3100/oauth/callback?code=...&state=...`.

- [ ] **Step 2: Capture the authorization code from the callback**

With Paperclip not yet wired, simulate the callback receiver with a one-shot listener or paste the `code` query parameter from the redirected URL:

```bash
# After visiting the URL, copy CODE from the redirect:
CODE=<paste code>
STATE=$(grep STATE /tmp/oauth-state.env | cut -d= -f2)
echo "code len=${#CODE} state matches: $([ "$STATE" = "$STATE" ] && echo yes)"
```

- [ ] **Step 3: Exchange code for tokens**

```bash
set -a; . /Users/chrisstefan/.config/digithings/forgejo-oauth/paperclip-local.env; set +a
CODE=<paste code>
curl -s -X POST \
  -H "Content-Type: application/json" \
  -d "{\"client_id\":\"${FORGEJO_OAUTH_CLIENT_ID}\",\"client_secret\":\"${FORGEJO_OAUTH_CLIENT_SECRET}\",\"code\":\"${CODE}\",\"grant_type\":\"authorization_code\",\"redirect_uri\":\"${FORGEJO_OAUTH_REDIRECT_URI}\"}" \
  http://localhost:3000/login/oauth/access_token | python3 -m json.tool
```

Expected: JSON with `access_token`, `token_type: bearer`, `expires_in: 3600`, `refresh_token`.

- [ ] **Step 4: Call userinfo and an API endpoint with the access token**

```bash
ACCESS_TOKEN=<paste access_token>
echo "--- userinfo ---"
curl -s -H "Authorization: Bearer ${ACCESS_TOKEN}" http://localhost:3000/login/oauth/userinfo | python3 -m json.tool
echo "--- /api/v1/user ---"
curl -s -H "Authorization: Bearer ${ACCESS_TOKEN}" http://localhost:3000/api/v1/user \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('login=',d.get('login'),'id=',d.get('id'))"
```

Expected: userinfo returns `sub`, `name`, `email`, etc.; `/api/v1/user` returns the consenting user's profile.

- [ ] **Step 5: Verify refresh-token rotation**

```bash
set -a; . /Users/chrisstefan/.config/digithings/forgejo-oauth/paperclip-local.env; set +a
REFRESH_TOKEN=<paste refresh_token>
curl -s -X POST \
  -H "Content-Type: application/json" \
  -d "{\"client_id\":\"${FORGEJO_OAUTH_CLIENT_ID}\",\"client_secret\":\"${FORGEJO_OAUTH_CLIENT_SECRET}\",\"grant_type\":\"refresh_token\",\"refresh_token\":\"${REFRESH_TOKEN}\"}" \
  http://localhost:3000/login/oauth/access_token | python3 -c "import sys,json; d=json.load(sys.stdin); print('new_access_len=',len(d.get('access_token','')),'has_refresh=',bool(d.get('refresh_token')))"
```

Expected: new access token issued.

- [ ] **Step 6: Write the smoke-test script**

Create `scripts/verify-forgejo-oauth.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
BASE="${FORGEJO_BASE_URL:-http://localhost:3000}"
echo "== OIDC discovery =="
curl -fsS "$BASE/.well-known/openid-configuration" | python3 -c "import sys,json; d=json.load(sys.stdin); print('issuer=',d['issuer']); print('auth=',d['authorization_endpoint']); print('token=',d['token_endpoint']); print('userinfo=',d['userinfo_endpoint'])"
echo "== authorize endpoint (expect 302/200) =="
code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/login/oauth/authorize?client_id=dummy&redirect_uri=http://localhost:3100/oauth/callback&response_type=code")
echo "authorize (no creds) -> $code (302/400/401 acceptable)"
echo "== token endpoint (expect 400 invalid_grant) =="
curl -s -o /dev/null -w "%{http_code}\n" -X POST -H "Content-Type: application/json" \
  -d '{"grant_type":"authorization_code","code":"invalid","client_id":"dummy","redirect_uri":"http://localhost:3100/oauth/callback"}' \
  "$BASE/login/oauth/access_token"
echo "OK: endpoints reachable"
```

```bash
chmod +x scripts/verify-forgejo-oauth.sh
./scripts/verify-forgejo-oauth.sh
```

Expected: discovery prints issuer/auth/token/userinfo; endpoints reachable.

- [ ] **Step 7: Commit**

```bash
git add scripts/verify-forgejo-oauth.sh docs/ops/forgejo-oauth.md
git commit -m "docs(forgejo): verify paperclip oauth2 flow end-to-end"
```

---

### Task 6: Test the public-client (sctl) PKCE flow

**Files:**
- Modify: `docs/ops/forgejo-oauth.md`

**Interfaces:**
- Consumes: sctl-local client_id, code_verifier/challenge.
- Produces: verified PKCE authorize → code → token exchange without secret.

- [ ] **Step 1: Generate PKCE pair**

```bash
python3 - <<'PY'
import secrets, hashlib, base64
verifier = secrets.token_urlsafe(64)[:96]
challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
print("VERIFIER=" + verifier)
print("CHALLENGE=" + challenge)
PY
```

Store both values.

- [ ] **Step 2: Build authorize URL with PKCE**

```bash
set -a; . /Users/chrisstefan/.config/digithings/forgejo-oauth/sctl-local.env; set +a
VERIFIER=<from step 1>
CHALLENGE=<from step 1>
echo "http://localhost:3000/login/oauth/authorize?client_id=${FORGEJO_OAUTH_CLIENT_ID}&redirect_uri=http://127.0.0.1:7890/oauth/callback&response_type=code&code_challenge_method=S256&code_challenge=${CHALLENGE}&state=sctl-test"
```

Visit while logged in; consent; receive code at `http://127.0.0.1:7890/oauth/callback?code=...`.

- [ ] **Step 3: Exchange code with code_verifier (no secret)**

```bash
set -a; . /Users/chrisstefan/.config/digithings/forgejo-oauth/sctl-local.env; set +a
CODE=<paste code>
VERIFIER=<from step 1>
curl -s -X POST \
  -H "Content-Type: application/json" \
  -d "{\"client_id\":\"${FORGEJO_OAUTH_CLIENT_ID}\",\"code\":\"${CODE}\",\"grant_type\":\"authorization_code\",\"redirect_uri\":\"http://127.0.0.1:7890/oauth/callback\",\"code_verifier\":\"${VERIFIER}\"}" \
  http://localhost:3000/login/oauth/access_token | python3 -c "import sys,json; d=json.load(sys.stdin); print('token_type=',d.get('token_type'),'expires_in=',d.get('expires_in'),'has_refresh=',bool(d.get('refresh_token')))"
```

Expected: `token_type= bearer expires_in= 3600 has_refresh= True`.

- [ ] **Step 4: Document sctl login procedure**

Append to `docs/ops/forgejo-oauth.md`:

```markdown
## sctl CLI login procedure (PKCE)

1. sctl starts a temporary HTTP listener on `127.0.0.1:7890`.
2. Generate PKCE verifier/challenge; open the authorize URL in the user's browser.
3. Receive `code` on the loopback callback.
4. Exchange code + verifier for access/refresh tokens (no secret).
5. Store tokens in the OS keyring / `~/.config/digithings/forgejo-oauth/sctl-tokens.json` (600).
6. Refresh before expiry using `grant_type=refresh_token`.
```

- [ ] **Step 5: Commit**

```bash
git add docs/ops/forgejo-oauth.md
git commit -m "docs(forgejo): verify sctl pkce oauth2 flow"
```

---

### Task 7: Document how agents authenticate to Forgejo via OAuth

**Files:**
- Create: `docs/ops/forgejo-oauth.md` (agent section) — or append to existing.
- Modify: `docs/plans/forgejo-full-setup.md` (mark complete).

**Interfaces:**
- Produces: canonical guidance for agent/service authentication.

- [ ] **Step 1: Append agent-authentication section to runbook**

Append to `docs/ops/forgejo-oauth.md`:

```markdown
## How agents authenticate to Forgejo

Forgejo OAuth 2 is a *user-delegated* flow. Agents are service identities, so choose
the right mechanism per use case:

### 1. Unattended agents (Claude, Grok, Cursor, CI) — use PATs, not OAuth

Agents already hold scoped PATs in `~/.config/digithings/forgejo-tokens/<identity>.token`.
These are long-lived, revocable, and require no browser. Prefer PATs for all
automated git/API operations:

```bash
export FORGEJO_TOKEN=$(cat ~/.config/digithings/forgejo-tokens/claude-agent.token)
git -c http.extraHeader="Authorization: token ${FORGEJO_TOKEN}" clone http://localhost:3000/digithings-ai/digithings.git
```

### 2. Paperclip board (on behalf of a user) — OAuth confidential client

Paperclip uses `paperclip-local` to obtain a user's consent and act with that
user's identity (e.g., open PRs, post reviews, update issue status). Store
`FORGEJO_OAUTH_CLIENT_ID` / `FORGEJO_OAUTH_CLIENT_SECRET` in Paperclip's secrets
store (sourced from `paperclip-local.env`), never in code. Callback handler:
`http://localhost:3100/oauth/callback`.

Required env for Paperclip:
```
FORGEJO_BASE_URL=http://localhost:3000
FORGEJO_OAUTH_CLIENT_ID=<from paperclip-local.env>
FORGEJO_OAUTH_CLIENT_SECRET=<from paperclip-local.env>
FORGEJO_OAUTH_REDIRECT_URI=http://localhost:3100/oauth/callback
```

### 3. sctl CLI — OAuth public client (PKCE)

Interactive human/agent-shell login via `sctl-local` (PKCE, no secret). Tokens are
short-lived (1h) with refresh tokens; sctl refreshes automatically.

### 4. Git over HTTPS via OAuth (optional)

For git credential helpers, Forgejo ships a pre-registered client
(`a4792ccc-144e-407e-86c9-5e7d8d9c3269`). Configure `git-credential-oauth`
with `oauthClientId`, `oauthAuthURL=/login/oauth/authorize`,
`oauthTokenURL=/login/oauth/access_token`. See Forgejo docs.

### Security notes

- OAuth scopes are NOT implemented in Forgejo v17: any OAuth token grants the
  full rights of the consenting user. Create apps under least-privilege users
  (e.g., `paperclip-bot`, not `sctl`) when the integration does not need admin.
- Client secrets are shown only once at creation; rotate by PATCH-ing the app
  (`PATCH /api/v1/user/applications/oauth2/{id}`) which regenerates the secret.
- Redirect URIs must match exactly; for public clients use loopback IPs
  (`127.0.0.1`), not `localhost`.
- Tokens expire in 1 hour; always implement refresh. Revoke by deleting the app
  or the user's granted tokens.
- Do not commit `*.env` files under `~/.config/digithings/forgejo-oauth/`.
```

- [ ] **Step 2: Update forgejo-full-setup.md completed section**

In `docs/plans/forgejo-full-setup.md`, under "Remaining Phases", change:
```
- Phase 4: OAuth 2 apps (Paperclip integration)
```
to:
```
- Phase 4: OAuth 2 apps (Paperclip integration) — DONE (paperclip-local, sctl-local; see docs/ops/forgejo-oauth.md)
```
And add a "Phase 4: COMPLETED" subsection mirroring the Phase 2/3 style, listing the two apps and redirect URIs.

- [ ] **Step 3: Commit**

```bash
git add docs/ops/forgejo-oauth.md docs/plans/forgejo-full-setup.md
git commit -m "docs(forgejo): document agent authentication via oauth2"
```

---

### Task 8: (Optional) Least-privilege re-registration under service users

**Files:**
- Modify: `docs/ops/forgejo-oauth.md`

**Interfaces:**
- Produces: guidance to move apps off `sctl` onto `paperclip-bot` for reduced blast radius.

- [ ] **Step 1: Document the recommendation**

Append to `docs/ops/forgejo-oauth.md`:

```markdown
## Least-privilege recommendation (follow-up)

Because OAuth tokens inherit the registering user's rights and scopes are not
implemented, apps registered under `sctl` effectively grant admin. For production
use, re-register `paperclip-local` under the `paperclip-bot` user (PAT in
`~/.config/digithings/forgejo-tokens/paperclip-bot.token`) so consents grant
only that user's permissions. Steps: log in as `paperclip-bot`, repeat Task 3,
update Paperclip env, delete the `sctl`-registered app.
```

- [ ] **Step 2: Commit**

```bash
git add docs/ops/forgejo-oauth.md
git commit -m "docs(forgejo): note least-privilege oauth re-registration follow-up"
```

---

## Verification checklist

- [ ] `curl /api/v1/user` with admin PAT returns `sctl` admin.
- [ ] `GET /api/v1/user/applications/oauth2` lists `woodpecker-local`, `paperclip-local`, `sctl-local`.
- [ ] Paperclip authorize → code → token → userinfo round-trip succeeds.
- [ ] sctl PKCE authorize → code → token (no secret) succeeds.
- [ ] Refresh-token exchange succeeds for both clients.
- [ ] `scripts/verify-forgejo-oauth.sh` exits 0.
- [ ] No client secret appears in git history (`git log -p | grep client_secret` empty).
- [ ] `docs/ops/forgejo-oauth.md` covers endpoints, apps, flows, agent auth.

## Self-review notes

- Spec coverage: Forgejo-full-setup Phase 6 (OAuth apps for woodpecker/paperclip/sctl) covered by Tasks 2–4; callback URLs by Task 3/4; testing by Tasks 5–6; agent auth docs by Task 7.
- Placeholder scan: all curl commands use concrete endpoints and bodies derived from Forgejo's swagger (`/api/v1/user/applications/oauth2`, `CreateOAuth2ApplicationOptions`); `<paste ...>` markers are intentional manual capture points, not unspecified implementation.
- Type consistency: client_id/client_secret/redirect_uris names match the swagger schema exactly.
