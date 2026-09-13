import { DigiquantMark } from '@digithings/web';

/**
 * Thin wrapper over the promoted @digithings/web DigiquantMark (#1548),
 * preserving the dashboard's shipped surface: 28px, ink by default (the mark
 * draws in currentColor), decorative (aria-hidden).
 */
export function DashboardMark({ className }: { className?: string }) {
  const merged = ['text-ink', className].filter(Boolean).join(' ');
  return <DigiquantMark size={28} className={merged} />;
}
