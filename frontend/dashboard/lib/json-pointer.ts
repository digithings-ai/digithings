/** RFC 6901 JSON Pointer path segments (leading slash, split on /). */
export function getJsonAtPointer(obj: unknown, pointer: string): unknown {
  const raw = pointer.trim();
  if (!raw || raw === '/') return obj;
  const trimmed = raw.startsWith('/') ? raw.slice(1) : raw;
  if (!trimmed) return obj;
  const parts = trimmed.split('/').map((p) => p.replace(/~1/g, '/').replace(/~0/g, '~'));
  let cur: unknown = obj;
  for (const part of parts) {
    if (cur == null) return undefined;
    if (Array.isArray(cur)) {
      const i = parseInt(part, 10);
      if (String(i) !== part || i < 0 || i >= cur.length) return undefined;
      cur = cur[i];
    } else if (typeof cur === 'object') {
      cur = (cur as Record<string, unknown>)[part];
    } else {
      return undefined;
    }
  }
  return cur;
}

export function stringifyJsonish(v: unknown): string {
  if (v === undefined) return '—';
  try {
    return typeof v === 'string' ? v : JSON.stringify(v, null, 2);
  } catch {
    return String(v);
  }
}
