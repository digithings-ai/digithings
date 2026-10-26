# Forgejo 2FA recovery (localhost:3000)

- Requirement: `GLOBAL_TWO_FACTOR_REQUIREMENT = admin` in `[security]`
  (`app.ini`); admins (`sctl`, `chris`) must enroll TOTP.
- Recovery codes: stored in password manager under
  "forgejo-<user>-2fa-recovery". Use one if the authenticator is lost.
- Admin reset (loses 2FA, user must re-enroll):
  `docker exec -u git "${FORGEJO_CONTAINER:-local-forge-forgejo-1}" forgejo admin user reset-mfa -u <username>`
- If SECRET_KEY is lost, ALL 2FA secrets are unrecoverable; restore from backup.
- Never disable 2FA globally except during a documented incident; re-enable
  immediately after.
