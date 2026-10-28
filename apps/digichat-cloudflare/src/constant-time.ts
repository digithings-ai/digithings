/**
 * Constant-time string comparison for secret material at the edge (DIG-3585).
 *
 * Every byte is folded in, so the time taken does not depend on where the two
 * strings first differ. Only the length leaks; a credential's length is not
 * secret here. The invite gate, the admin reset gate and the MCP key gate all
 * compare through this one function.
 */
export function constantTimeEqual(given: string, expected: string): boolean {
  const a = new TextEncoder().encode(given);
  const b = new TextEncoder().encode(expected);
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a[i]! ^ b[i]!;
  return diff === 0;
}
