'use client';

import { useSyncExternalStore } from 'react';
import { FileText } from 'lucide-react';

import { Card } from '@digithings/ui/ui';
import { SafeMarkdown } from '@/components/SafeMarkdown';
import { calendarDay, todayYmd, tradingSessionsSince } from '@/lib/trading-calendar';
import { TwelveXSectionHeading } from './TwelveXSectionHeading';

/**
 * Age policy, in trading sessions behind the last run, mirroring the FX pane
 * (clients/digiquant-tui/src/pages/fx.tsx):
 *   0-1  ok    the run is still the one the next session owes
 *   2    warn  past one trading session
 *   3+   stale past the point where the next session should have landed
 * Weekends do not count (see trading-calendar), so Monday morning does not warn
 * on Friday's digest.
 */
const SESSION_WARN = 2;
const SESSION_STALE = 3;

type DigestAge = { sessions: number; tone: 'warn' | 'stale' };

/** The aged state of `run_date` against `now`, or null while it is current. */
function digestAge(runDate: string, now: string): DigestAge | null {
  const sessions = tradingSessionsSince(runDate, now);
  if (sessions === null) return null;
  if (sessions >= SESSION_STALE) return { sessions, tone: 'stale' };
  if (sessions >= SESSION_WARN) return { sessions, tone: 'warn' };
  return null;
}

/** The age in words. The tone alone is a colour; the reader needs the count. */
function ageLabel(sessions: number): string {
  return sessions === 1 ? '1 trading day old' : `${sessions} trading days old`;
}

const AGE_CLASS: Record<DigestAge['tone'], string> = {
  warn: 'border-warn/40 text-warn',
  stale: 'border-danger/40 text-danger',
};

/**
 * The reader's calendar day can turn while the tab stays open. Re-read it on
 * the minute (React compares the string and skips the render unless the day
 * moved) and when a hidden tab becomes visible again, so an idle FX Hub cannot
 * keep serving the age it computed at load. Never called on the server.
 */
function subscribeToday(onChange: () => void): () => void {
  if (typeof window === 'undefined') return () => {};
  const timer = window.setInterval(onChange, 60_000);
  const onVisibility = () => {
    if (!document.hidden) onChange();
  };
  document.addEventListener('visibilitychange', onVisibility);
  return () => {
    window.clearInterval(timer);
    document.removeEventListener('visibilitychange', onVisibility);
  };
}

export default function DigestBrief({
  digest,
  now,
}: {
  digest: { run_date: string; summary: string; key_themes: string[]; doc_count: number; broker_count: number } | null;
  /** Reader's calendar day as `YYYY-MM-DD`. Defaults to the browser's today
   *  after mount, so a static export never bakes its build date into the age. */
  now?: string;
}) {
  // The browser's today, read client-side only: the static export's server
  // snapshot is null, so the build date is never baked into the age.
  const today = useSyncExternalStore(
    subscribeToday,
    () => now ?? todayYmd(),
    () => now ?? null,
  );
  if (!digest) {
    return (
      <Card data-reveal className="gap-0 p-5">
        <TwelveXSectionHeading>Digest brief</TwelveXSectionHeading>
        <p className="mt-2 text-sm text-ink-mute">No digest for today yet.</p>
      </Card>
    );
  }
  const runDate = calendarDay(digest.run_date) ?? digest.run_date;
  const age = today === null ? null : digestAge(digest.run_date, today);
  return (
    <Card data-reveal className="flex flex-col gap-2 p-5">
      <header className="flex min-w-0 items-baseline gap-2">
        <FileText size={15} className="shrink-0 text-accent" aria-hidden />
        <TwelveXSectionHeading>Digest brief</TwelveXSectionHeading>
        <span className="ml-auto min-w-0 shrink text-right font-mono text-[10px] leading-snug text-ink-mute">
          {digest.doc_count} docs · {digest.broker_count} brokers
        </span>
      </header>
      {/* The digest is the freshest covered session, not necessarily today:
          always name the run date and age it in trading sessions. */}
      <div className="flex flex-wrap items-center gap-2 font-mono text-[10px] leading-snug text-ink-mute">
        <span>as of {runDate}</span>
        {age ? (
          <span data-digest-age={age.tone} className={`border px-1.5 py-0.5 ${AGE_CLASS[age.tone]}`}>
            {ageLabel(age.sessions)} · {age.tone}
          </span>
        ) : null}
      </div>
      {/* The pipeline-written summary renders through SafeMarkdown (sanitizer
          stays — REM-076) inside the canonical .chat-md typography scope.
          `whitespace-pre-line` is kept ON PURPOSE: react-markdown emits soft
          breaks as literal "\n" text nodes, so plain-text summaries keep their
          exact pre-markdown line layout while real markdown (emphasis, lists,
          tables) now picks up the shared grammar. */}
      <SafeMarkdown className="whitespace-pre-line">{digest.summary}</SafeMarkdown>
      {digest.key_themes.length > 0 ? (
        <div className="mt-1 flex flex-wrap gap-1.5">
          {digest.key_themes.map((t) => (
            <span key={t} className="rounded-none border border-hair px-2.5 py-0.5 text-[11px] text-ink-soft">
              {t}
            </span>
          ))}
        </div>
      ) : null}
    </Card>
  );
}
