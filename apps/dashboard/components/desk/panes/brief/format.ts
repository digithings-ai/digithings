/** Fail closed. A missing figure is an em dash, never zero and never a guess. */
export const EM_DASH = '—';

export const GLOOMBERG_PLACEHOLDER = 'Layout placeholder. Not a Gloomberg feed.';
export const GLOOMBERG_NO_CLOSES =
  'The quote strip stays in the brief layout. This state does not print closes.';
export const GLOOMBERG_NO_TAPE = 'No tape headlines.';

export function formatSignedPct(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return EM_DASH;
  if (value > 0) return `+${value.toFixed(2)}%`;
  return `${value.toFixed(2)}%`;
}

export function formatWeight(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return EM_DASH;
  return `${value.toFixed(1)}%`;
}

export function formatMark(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return EM_DASH;
  return value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function textOrDash(value: string | null | undefined): string {
  const trimmed = value?.trim() ?? '';
  return trimmed.length > 0 ? trimmed : EM_DASH;
}

/**
 * CONTRACT §5 / §6.3: a live overlay is `live marks` and must never wear
 * `finalized accounting`, even if a payload still carries that badge string.
 */
export function provenanceBadge(
  overlay: { active: boolean; badge: string } | null | undefined,
): string {
  if (!overlay) return EM_DASH;
  if (overlay.active) return 'live marks';
  const badge = overlay.badge.trim();
  return badge.length > 0 ? badge : EM_DASH;
}
