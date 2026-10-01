'use client';

import type { ReactNode } from 'react';
import Link from 'next/link';
import {
  AllocationTreemap,
  CalendarHeatmap,
  CompositionBar,
  EmptyState,
  HeatGrid,
  Sparkline,
  Stat,
  type CompositionSegment,
} from '@digithings/ui/ui';
import { CORPUS_KEY_PREFIXES, HOUSE_BOOK_IDENTITY, HOUSE_PROFILE_PINS } from '@/lib/house-identity';
import type { BookView, CorpusView, LabelCount, ProfileView } from '@/lib/house-view';

const fmtInt = (n: number) => n.toLocaleString('en-US');
const fmtPct = (n: number | null) => (n === null ? null : `${n.toFixed(n < 10 && n > 0 ? 1 : 0)}%`);

function Section({ title, caption, children }: { title: string; caption?: string; children: ReactNode }) {
  return (
    <section className="border border-hair bg-surface p-3">
      <h2 className="font-mono text-[10px] uppercase tracking-widest text-ink-mute">{title}</h2>
      <div className="mt-2">{children}</div>
      {caption ? <p className="mt-2 font-mono text-[11px] text-ink-mute">{caption}</p> : null}
    </section>
  );
}

function ranked(rows: LabelCount[]): CompositionSegment[] {
  return rows.map((r) => ({ key: r.label, label: r.label, value: r.value }));
}

/** DB-down / not-loaded placeholder, so data tiles never render blank. */
function Unavailable({ what, cause }: { what: string; cause?: string }) {
  return (
    <EmptyState
      variant="error"
      title={`${what} unavailable`}
      body={cause ?? 'The dashboard data source is not reachable. Profile pins below still work.'}
    />
  );
}

export function CorpusPanel({ view, unavailable }: { view: CorpusView; unavailable?: string | null }) {
  const empty = view.total === 0;
  const keyed: CompositionSegment[] = [
    { key: 'keyed', label: 'Keyed (theme:/asset:/segment:)', value: view.keyedCount, tone: 'accent' },
    { key: 'other', label: 'Path-addressed', value: view.total - view.keyedCount, tone: 'mute' },
  ];
  const runMix: CompositionSegment[] = [
    { key: 'baseline', label: 'Baseline', value: view.baselineCount, tone: 'accent' },
    { key: 'delta', label: 'Delta', value: view.deltaCount, tone: 'soft' },
  ];
  return (
    <section data-testid="house-corpus-panel" className="space-y-4">
      {unavailable !== undefined && unavailable !== null && empty ? (
        <Unavailable what="Corpus" cause={unavailable || undefined} />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6">
            <Stat
              label="Documents"
              value={empty ? null : fmtInt(view.total)}
              spark={
                view.weekly.length > 1 ? (
                  <Sparkline values={view.weekly} tone="accent" label="Documents per week, last 53 weeks" />
                ) : undefined
              }
            />
            <Stat label="Days covered" value={empty ? null : fmtInt(view.daysCovered)} />
            <Stat label="Keyed" value={fmtPct(view.keyedPct)} hint="theme: / asset: / segment:" />
            <Stat label="Latest doc" value={view.latestDate} />
            <Stat label="Delta share" value={fmtPct(view.deltaSharePct)} />
            <Stat label="Changed paths 7d" value={empty ? null : fmtInt(view.changedPaths7d)} />
          </div>

          <Section
            title="Documents per day"
            caption={
              view.latestDate
                ? `${fmtInt(view.total)} documents across ${fmtInt(view.daysCovered)} days, latest ${view.latestDate}. Gaps are missed runs.`
                : undefined
            }
          >
            <CalendarHeatmap
              days={view.days}
              unit={{ singular: 'doc', plural: 'docs' }}
              emptyLabel="No documents in the dashboard snapshot yet."
            />
          </Section>

          <div className="grid gap-4 lg:grid-cols-2">
            <Section title="Run mix" caption="Baseline is the always-on house run; delta is an incremental update.">
              <CompositionBar segments={runMix} legend label={`Run mix: ${view.baselineCount} baseline, ${view.deltaCount} delta`} />
            </Section>
            <Section
              title="Key contract"
              caption="Profile identity never appears in the key. Coverage rises as Track B corpus rows land; zero is expected today."
            >
              <CompositionBar segments={keyed} mode="share" legend />
              <ul className="mt-2 flex flex-wrap gap-2 font-mono text-xs text-ink">
                {CORPUS_KEY_PREFIXES.map((prefix) => (
                  <li key={prefix} className="border border-hair bg-surface px-2 py-0.5">
                    {prefix}
                  </li>
                ))}
              </ul>
              {view.sampleKeys.length > 0 ? (
                <ul className="mt-2 divide-y divide-hair/60 border border-hair font-mono text-xs text-ink-soft">
                  {view.sampleKeys.map((k) => (
                    <li key={k} className="px-2 py-1">
                      {k}
                    </li>
                  ))}
                </ul>
              ) : null}
            </Section>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            {(
              [
                ['By category', view.byCategory],
                ['By segment', view.bySegment],
                ['By sector', view.bySector],
              ] as const
            ).map(([title, rows]) => (
              <Section key={title} title={title}>
                {rows.length === 0 ? (
                  <p className="font-mono text-xs text-ink-mute">No classified documents.</p>
                ) : (
                  <CompositionBar segments={ranked([...rows])} legend label={`${title}: ${rows.map((r) => `${r.label} ${r.value}`).join(', ')}`} />
                )}
              </Section>
            ))}
          </div>
          <p className="font-mono text-[11px] text-ink-mute">
            {HOUSE_BOOK_IDENTITY.summary}{' '}
            <Link href="/library" className="text-accent hover:underline">
              Open Library
            </Link>
          </p>
        </>
      )}
    </section>
  );
}

export function BookPanel({
  view,
  unavailable,
}: {
  view: BookView;
  unavailable?: string | null;
}) {
  const empty = view.positionCount === 0 && view.nav.length === 0;
  const up = view.navReturnPct !== null && view.navReturnPct >= 0;
  const sleeveSegments: CompositionSegment[] = [
    ...view.sleeves.map((s) => ({ key: s.id, label: s.label, value: s.value })),
    ...(view.cashPct !== null && view.cashPct > 0
      ? [{ key: 'cash', label: 'Cash', value: view.cashPct, cash: true }]
      : []),
  ];
  return (
    <section data-testid="house-book-panel" className="space-y-4">
      {unavailable !== undefined && unavailable !== null && empty ? (
        <Unavailable what="Book" cause={unavailable || undefined} />
      ) : (
        <>
          <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6">
            <Stat
              label="NAV"
              value={view.latestNav === null ? null : view.latestNav.toFixed(2)}
              delta={view.navReturnPct === null ? undefined : `${up ? '+' : ''}${view.navReturnPct.toFixed(2)}%`}
              deltaTone={up ? 'up' : 'down'}
              spark={
                view.nav.length > 1 ? (
                  <Sparkline values={view.nav} tone={up ? 'up' : 'down'} label="NAV history" />
                ) : undefined
              }
            />
            <Stat label="Positions" value={view.positionCount || null} hint={`${view.longCount} long / ${view.shortCount} short`} />
            <Stat label="Gross" value={view.positionCount ? `${view.grossPct.toFixed(1)}%` : null} />
            <Stat label="Cash" value={view.cashPct === null ? null : `${view.cashPct.toFixed(1)}%`} />
            <Stat label="Sleeves" value={view.sleeves.length || null} />
            <Stat label="Off target" value={view.positionCount ? view.drifted : null} hint="> 1pp from target" />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Section title="Holdings by weight" caption="Area is absolute weight. Open Holdings for prices and thesis.">
              <AllocationTreemap
                items={view.holdings}
                label="House book holdings by weight"
                emptyLabel="No positions in the dashboard snapshot."
              />
            </Section>
            <Section title="Sleeve mix" caption="Share of book by category; cash is undeployed.">
              {sleeveSegments.length === 0 ? (
                <p className="font-mono text-xs text-ink-mute">No sleeves to show.</p>
              ) : (
                <CompositionBar segments={sleeveSegments} mode="stacked" total={100} height={14} legend />
              )}
            </Section>
          </div>
          <nav aria-label="House book surfaces" className="flex flex-wrap gap-4 font-mono text-xs">
            <Link href="/portfolio" className="text-accent hover:underline">
              Holdings
            </Link>
            <Link href="/portfolio/performance" className="text-accent hover:underline">
              Tearsheet
            </Link>
            <Link href="/portfolio/ledger" className="text-accent hover:underline">
              Ledger
            </Link>
          </nav>
        </>
      )}
    </section>
  );
}

export function ProfilePanel({ view }: { view: ProfileView }) {
  // Kit grid is rows x cols: artifact classes down, plan tiers across. Zero -> null (empty cell).
  const rows = view.classes.map((c) => c.replace(/_/g, ' '));
  const values = view.classes.map((_, ci) => view.tiers.map((_, ti) => (view.grid[ti][ci] ? 1 : null)));
  return (
    <section data-testid="house-profile-panel" className="space-y-4">
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        <Stat label="Profile id" value={HOUSE_PROFILE_PINS.profileId} />
        <Stat label="Editable" value={HOUSE_PROFILE_PINS.editable ? 'yes' : 'read-only'} />
        <Stat label="Risk" value="Paper only" hint={HOUSE_PROFILE_PINS.riskStance} />
        <Stat label="Universe" value={view.universe.length || null} hint="categories held" />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Section title="Plan tier visibility" caption="Which artifact classes each plan tier can see. Presentation only; row-level security is the hard gate.">
          <HeatGrid
            rows={rows}
            cols={[...view.tiers]}
            values={values}
            format={(v) => (v ? 'yes' : 'no')}
            showValues
            cellWidth={52}
            labelWidth={140}
            label="Plan tier by artifact class visibility"
          />
        </Section>
        <div className="space-y-4">
          <Section title="Declared universe" caption={HOUSE_PROFILE_PINS.note}>
            {view.universe.length === 0 ? (
              <p className="font-mono text-xs text-ink-mute">{HOUSE_PROFILE_PINS.universe}</p>
            ) : (
              <ul className="flex flex-wrap gap-2 font-mono text-xs text-ink">
                {view.universe.map((u) => (
                  <li key={u} className="border border-hair px-2 py-0.5">
                    {u}
                  </li>
                ))}
              </ul>
            )}
          </Section>
          <Section title="Constraints">
            {view.constraints.length === 0 ? (
              <p className="font-mono text-xs text-ink-mute">No scalar constraints published.</p>
            ) : (
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 font-mono text-xs">
                {view.constraints.map((c) => (
                  <div key={c.key} className="contents">
                    <dt className="text-ink-mute">{c.key}</dt>
                    <dd className="text-right tabular-nums text-ink">{c.value}</dd>
                  </div>
                ))}
              </dl>
            )}
          </Section>
        </div>
      </div>
    </section>
  );
}
