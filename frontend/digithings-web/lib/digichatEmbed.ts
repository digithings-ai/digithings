/** Same-origin path mount: DigiChat is routed at digithings.ai/embed (not chat.). */
const DEFAULT_ORIGIN = "https://digithings.ai";

export function getDigichatEmbedOrigin(): string {
  const raw = process.env.NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN?.trim();
  if (!raw) return DEFAULT_ORIGIN;
  return raw.replace(/\/$/, "");
}

export function buildDigichatEmbedSrc(opts?: { parentOrigin?: string }): string {
  const origin = getDigichatEmbedOrigin();
  const parent = opts?.parentOrigin ?? "https://digithings.ai";
  const url = new URL("/embed", origin);
  url.searchParams.set("host", parent);
  return url.toString();
}
