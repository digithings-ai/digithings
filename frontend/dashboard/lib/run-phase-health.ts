export interface PhaseHealth {
  phase: number;
  ok: number;
  failed: number;
  carried: number;
}

const PHASE_KEY = /^phase(\d+)_outputs?$/;

function num(v: unknown): number {
  return typeof v === 'number' && Number.isFinite(v) ? v : 0;
}

export function parsePhaseHealth(breakdown: Record<string, unknown> | null): PhaseHealth[] {
  if (!breakdown || typeof breakdown !== 'object') return [];
  const out: PhaseHealth[] = [];
  for (const [key, raw] of Object.entries(breakdown)) {
    const m = key.match(PHASE_KEY);
    if (!m || raw == null || typeof raw !== 'object') continue;
    const v = raw as Record<string, unknown>;
    out.push({
      phase: Number(m[1]),
      ok: num(v.ok),
      failed: num(v.failed),
      carried: num(v.carried),
    });
  }
  return out.sort((a, b) => a.phase - b.phase);
}
