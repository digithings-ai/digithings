# deploy

`deploy.sh <staging|prod>` is the one deploy path, run by hand now (`make deploy-<env>`)
and later by a Woodpecker job on a signed tag. In the template it refuses.

| Step                      | Touches                                              | Rollback                                          |
| ------------------------- | ---------------------------------------------------- | ------------------------------------------------- |
| 1. validate               | nothing (schema + tests)                             | n/a                                               |
| 2. upload seeds/skills    | R2, under this client's prefix, keyed by tag         | re-run at the previous tag                        |
| 3. write tenant doc       | KV `TENANT_CONFIG`, key from `tenant/env/<env>.yaml` | re-run at the previous tag                        |
| 4. own Workers (optional) | `client-<client-slug>-*` Workers only                | `wrangler rollback` or re-run at the previous tag |

Before any step, `make deploy-*` runs `scripts/check_forgejo_private.sh`: it reads the
Forgejo repo's `private` flag through the API (token from the keychain) and refuses when
the repo is not private or the flag cannot be read.

It never redeploys the shared stack. Prod needs a release tag signed by the owner
(`git verify-tag`). The Cloudflare token is a scoped one from the keychain, never
the account-wide token.
