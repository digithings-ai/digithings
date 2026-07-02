'use client';

import { useDigiSmithStatus, type StatusState } from '@/lib/digismith-status';

/** Fixed semantic status colors (not themed) — mid-tones that read on both themes. */
const META: Record<StatusState, { color: string; label: string }> = {
  ok: { color: '#3FB984', label: 'all systems operational' },
  degraded: { color: '#E0A72E', label: 'degraded' },
  error: { color: '#E0564F', label: 'service error' },
  unknown: { color: '#6B7177', label: 'status unknown' },
};

/**
 * Operator health dot wired to DigiSmith `GET /v1/status` (#1231). Renders nothing
 * unless `NEXT_PUBLIC_DIGISMITH_URL` is set (see `useDigiSmithStatus`). Non-blocking
 * and graceful — an unreachable DigiSmith shows a grey "status unknown" dot. The
 * label carries no PII. `compact` (collapsed sidebar) shows just the dot.
 */
export default function StatusDot({ compact = false }: { compact?: boolean }) {
  const { enabled, state } = useDigiSmithStatus();
  if (!enabled) return null;

  const { color, label } = META[state];
  return (
    <div
      className="flex items-center gap-2 text-text-muted"
      title={`DigiSmith · ${label}`}
      role="status"
      aria-label={`System status: ${label}`}
    >
      <span
        aria-hidden="true"
        className="inline-block h-2 w-2 shrink-0 rounded-full"
        style={{ backgroundColor: color }}
      />
      {compact ? null : (
        <span className="font-mono text-[10px] uppercase tracking-wider">{label}</span>
      )}
    </div>
  );
}
