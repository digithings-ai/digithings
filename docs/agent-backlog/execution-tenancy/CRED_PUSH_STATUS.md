# Kairos credential push status (2026-08-30)

See `EPIC.md` § Agent delivery status for the full ledger.

## This turn
- Merged [#3178](https://github.com/digithings-ai/digithings/pull/3178) to `develop`.
- **No new nonempty vendor secrets.**
- Mailgun: MCP auth fail; browser signup blocked (reCAPTCHA + agentmail rejection).
- Stripe TEST: one attempt → hCaptcha → stopped.
- Alpaca: Turnstile on signup; Cognito login `NotAuthorizedException`.
- EF secrets push blocked without `sbp_` PAT.
- `request-environment-setup-actions` filed for remaining desktop items.

## Parent-openable branch
`cursor/kairos-cred-push-3d52` → compare against `develop`.
