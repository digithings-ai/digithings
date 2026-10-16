import type { ResearchRunDiagnostics } from './types';

export type RunOutcome = 'ok' | 'recovered' | 'degraded' | 'failed';

export interface RunEpisode {
  key: string;
  runDate: string | null;
  runType: string | null;
  attempts: number;
  outcome: RunOutcome;
  latest: ResearchRunDiagnostics;
  errorSummary: string | null;
}

function classify(status: string | null): 'ok' | 'degraded' | 'failed' {
  const s = (status ?? '').toLowerCase();
  if (s.includes('ok') || s.includes('success') || s === 'complete' || s === 'completed') return 'ok';
  if (s.includes('degrad') || s.includes('partial') || s.includes('carr')) return 'degraded';
  return 'failed';
}

function ts(d: ResearchRunDiagnostics): number {
  return d.created_at ? Date.parse(d.created_at) : 0;
}

/**
 * Order two attempts of the same episode, oldest first.
 *
 * `attempt` is exact where it exists (#1762) and `created_at` is only a proxy — two attempts
 * of one job can share a timestamp to the millisecond, and before migration 065 the surviving
 * row's `created_at` was the *first* attempt's insert time while all its other columns were the
 * last attempt's. So prefer the counter, and fall back to the timestamp for rows that predate
 * it (`attempt` 0 or null) or when a date mixes both.
 */
function byAttempt(a: ResearchRunDiagnostics, b: ResearchRunDiagnostics): number {
  const ai = a.attempt ?? 0;
  const bi = b.attempt ?? 0;
  if (ai > 0 && bi > 0 && ai !== bi) return ai - bi;
  return ts(a) - ts(b);
}

export function groupRunEpisodes(diagnostics: ResearchRunDiagnostics[]): RunEpisode[] {
  const byKey = new Map<string, ResearchRunDiagnostics[]>();
  for (const d of diagnostics) {
    const key = `${d.run_date ?? '?'}|${d.run_type ?? '?'}`;
    const arr = byKey.get(key) ?? [];
    arr.push(d);
    byKey.set(key, arr);
  }
  const episodes: RunEpisode[] = [];
  for (const [key, attemptsUnsorted] of byKey) {
    const attempts = [...attemptsUnsorted].sort(byAttempt); // oldest → newest
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
