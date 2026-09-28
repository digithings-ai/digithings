/** Friendly host label for the data source — the Supabase URL's hostname, never the anon key. */
export function dataSourceHost(): string | null {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  if (!url) return null;
  try {
    return new URL(url).host;
  } catch {
    return null;
  }
}
