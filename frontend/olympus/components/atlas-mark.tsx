import { OlympusMark } from '@digithings/web';

/**
 * Thin wrapper over the promoted @digithings/web OlympusMark (#1548),
 * preserving olympus's shipped surface: 28px, ink by default (the mark
 * draws in currentColor), decorative (aria-hidden).
 */
export function AtlasMark({ className }: { className?: string }) {
  const merged = ['text-ink', className].filter(Boolean).join(' ');
  return <OlympusMark size={28} className={merged} />;
}
