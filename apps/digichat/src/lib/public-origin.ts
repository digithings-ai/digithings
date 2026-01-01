/**
 * The public origin the chat is served from, for absolute URLs in page
 * metadata (og:image, twitter:image).
 *
 * Without a `metadataBase`, Next resolves relative metadata URLs against
 * `http://localhost:<port>` at build time, and that leaks into production
 * link previews. The digithings.ai image sets
 * NEXT_PUBLIC_DIGICHAT_PUBLIC_ORIGIN=https://digithings.ai at build time
 * (infra/docker/Dockerfile.digichat-cloudflare). Self-hosted builds can set
 * their own; when it is unset or not an http(s) origin, this returns
 * undefined and Next keeps its default.
 */
export function publicOrigin(raw: string | undefined): URL | undefined {
  const value = (raw ?? "").trim();
  if (!value) return undefined;
  try {
    const url = new URL(value);
    if (url.protocol !== "https:" && url.protocol !== "http:") return undefined;
    return new URL(url.origin);
  } catch {
    return undefined;
  }
}

export const PUBLIC_ORIGIN = publicOrigin(process.env.NEXT_PUBLIC_DIGICHAT_PUBLIC_ORIGIN);
