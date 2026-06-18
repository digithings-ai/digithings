export function normalizeThesisId(id: string | null | undefined): string {
  return String(id ?? '').trim().toUpperCase();
}

export function thesisIdEquals(a: string | null | undefined, b: string | null | undefined): boolean {
  const left = normalizeThesisId(a);
  const right = normalizeThesisId(b);
  return Boolean(left && right && left === right);
}
