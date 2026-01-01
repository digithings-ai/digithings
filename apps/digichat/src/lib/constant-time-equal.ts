/**
 * Constant-time comparison of two strings, for secret material (DIG-3585).
 *
 * Pure JS (TextEncoder + XOR fold), so it is safe in every bundle this repo
 * builds: server routes, the edge, and modules a client component imports for
 * their types or defaults (`embed-client-config.ts` is one). Server-only code
 * may use `safeEqualStr` from `./safe-equal` instead; both compare in time that
 * does not depend on where the strings first differ. Only the length leaks,
 * and a credential's length is not secret here.
 */
export function constantTimeEqual(a: string, b: string): boolean {
  const ea = new TextEncoder().encode(a);
  const eb = new TextEncoder().encode(b);
  if (ea.length !== eb.length) return false;
  let diff = 0;
  for (let i = 0; i < ea.length; i++) diff |= ea[i]! ^ eb[i]!;
  return diff === 0;
}
