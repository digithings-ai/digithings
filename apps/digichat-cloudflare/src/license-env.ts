/**
 * License inputs for the digichat container (spec §7.1).
 *
 * digichat verifies its license JWT at startup against `DIGIKEY_PUBLIC_KEY_PEM`
 * and, when valid, forwards it to digigraph as `X-Digi-License`. digigraph
 * refuses hosted web search without that header, and digichat then retries the
 * turn without web search, so a missing license looks like a chat that simply
 * has no web search tool.
 *
 * Secret stores often keep a PEM on one line with literal `\n` sequences;
 * Node's `createPublicKey` rejects that form, so expand them before the value
 * reaches the container. Real newlines pass through unchanged.
 */
export function pemEnvValue(raw: string | undefined): string {
  const value = (raw ?? "").trim();
  if (!value) return "";
  return value.includes("\\n") ? value.replace(/\\n/g, "\n") : value;
}
