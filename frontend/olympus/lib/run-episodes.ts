import type { AtlasRunDiagnostics } from './types';

export type RunOutcome = 'ok' | 'recovered' | 'degraded' | 'failed';

export interface RunEpisode {
  key: string;
  runDate: string | null;
  runType: string | null;
  attempts: number;
  outcome: RunOutcome;
  latest: AtlasRunDiagnostics;
  errorSummary: string | null;
}

function classify(status: string | null): 'ok' | 'degraded' | 'failed' {
  const s = (status ?? '').toLowerCase();
  if (s.includes('ok') || s.includes('success') || s === 'complete' || s === 'completed') return 'ok';
  if (s.includes('degrad') || s.includes('partial') || s.includes('carr')) return 'degraded';
  return 'failed';
}

function ts(d: AtlasRunDiagnostics): number {
  return d.created_at ? Date.parse(d.created_at) : 0;
}

export function groupRunEpisodes(diagnostics: AtlasRunDiagnostics[]): RunEpisode[] {
  const byKey = new Map<string, AtlasRunDiagnostics[]>();
  for (const d of diagnostics) {
    const key = `${d.run_date ?? '?'}|${d.run_type ?? '?'}`;
    const arr = byKey.get(key) ?? [];
    arr.push(d);
    byKey.set(key, arr);
  }
  const episodes: RunEpisode[] = [];
  for (const [key, attemptsUnsorted] of byKey) {
    const attempts = [...attemptsUnsorted].sort((a, b) => ts(a) - ts(b)); // oldest → newest
    const latest = attempts[attempts.length - 1];
    const finalClass = classify(latest.status);
    const hadFailure = attempts.slice(0, -1).some((a) => classify(a.status) !== 'ok');
    const outcome: RunOutcome =
      finalClass === 'ok' ? (hadFailure ? 'recovered' : 'ok') : finalClass;
    episodes.push({
      key,
      runDate: latest.run_date,
      runType: latest.run_type,
      attempts: attempts.length,
      outcome,
      latest,
      errorSummary: attempts.find((a) => a.error_summary)?.error_summary ?? null,
    });
  }
  return episodes.sort((a, b) => ts(b.latest) - ts(a.latest)); // newest episode first
}
