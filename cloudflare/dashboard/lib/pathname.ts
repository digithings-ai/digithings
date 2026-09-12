/** Strip trailing slashes so `/settings` and `/settings/` compare equal. */
export function normalizePathname(pathname: string): string {
  const normalized = pathname.replace(/\/+$/, '');
  return normalized || '/';
}
