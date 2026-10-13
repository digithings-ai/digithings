/**
 * Citation links (DIG-3269): a non-web source (repo://, vault path) reaches the
 * renderer with its href emptied by the sanitizer, and <a href=""> would reload
 * the embed itself, query string included. Only these hrefs are links.
 */
export function isFollowableHref(href: string | undefined): boolean {
  if (!href) return false;
  return /^(https?:|mailto:|#|\/(?!\/))/i.test(href.trim());
}

