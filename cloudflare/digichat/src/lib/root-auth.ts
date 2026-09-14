/**
 * Root `/` auth gate (Option A default OFF).
 *
 * When DIGICHAT_REQUIRE_ROOT_AUTH is unset or "0", `/` does not force Auth.js
 * login — operators and dogfood use `/embed` (tenant gateMode). Set to "1" only
 * when a client explicitly wants a root session wall (Option B follow-up).
 */

export function isRootAuthRequired(): boolean {
  const raw = process.env.DIGICHAT_REQUIRE_ROOT_AUTH?.trim();
  if (!raw) return false;
  const lower = raw.toLowerCase();
  return raw === "1" || lower === "true" || lower === "on" || lower === "yes";
}
