'use client';

import { useMemo } from 'react';
import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';
import { useDashboard } from '@/lib/dashboard-context';
import { SUBPAGE_MAX } from '@/components/subpage-tab-bar';
import PortfolioSectionNav from '@/components/portfolio/PortfolioSectionNav';
import PageSkeleton from '@/components/page-skeleton';
import { ConvictionMeter } from '@/components/shared/conviction-meter';
import { AsOfBadge } from '@/components/shared/as-of-badge';
import { ThesisCriteriaColumns } from '@/components/portfolio/theses/ThesisCriteriaColumns';
import { ThesisHoldingsExpressing } from '@/components/portfolio/theses/ThesisHoldingsExpressing';
import { ThesisProvenanceStrip } from '@/components/portfolio/theses/ThesisProvenanceStrip';
import { findThesisById } from '@/lib/theses-ledger';
import { joinPositionsToThesis } from '@/lib/thesis-id';

const CONFIDENCE_PIPS = 4;

function confidenceToPips(confidence: number | null): number {
  if (confidence == null) return 0;
  return Math.max(0, Math.min(CONFIDENCE_PIPS, Math.round(confidence * CONFIDENCE_PIPS)));
}

function isNonActive(status: string | null): boolean {
  const s = (status ?? '').toLowerCase();
  return Boolean(s) && !s.includes('active');
}

export default function ThesisDetailPageInner({ thesisId }: { thesisId: string }) {
  const { data, loading, error } = useDashboard();

  const theses = useMemo(() => data?.portfolio?.strategy?.theses ?? [], [data]);
  const positions = useMemo(() => data?.positions ?? [], [data]);
  const lastUpdated = data?.portfolio?.meta?.last_updated ?? null;

  const thesis = useMemo(
    () => (thesisId === '_unlinked' ? null : findThesisById(theses, thesisId)),
    [theses, thesisId]
  );

  const expressingPositions = useMemo(() => {
    if (thesisId === '_unlinked') {
      return positions.filter((p) => !p.thesis_ids || p.thesis_ids.length === 0);
    }
    return joinPositionsToThesis(positions, thesisId);
  }, [positions, thesisId]);

  if (loading) return <PageSkeleton />;
  if (error || !data)
    return (
      <div className="flex items-center justify-center min-h-[40vh] text-down">
        {error || 'Failed to load'}
      </div>
    );

  if (thesisId !== '_unlinked' && !thesis) {
    return (
      <div className="flex min-h-full flex-col">
        <PortfolioSectionNav active="theses" />
        <div className={`${SUBPAGE_MAX} space-y-4 py-8`}>
          <Link
            href="/portfolio/theses"
            className="inline-flex items-center gap-2 text-sm text-accent hover:underline"
          >
            <ArrowLeft size={16} /> Back to Theses
          </Link>
          <p className="text-ink-mute">
            We don&apos;t have a thesis on record for <span className="font-mono">{thesisId}</span>.
          </p>
        </div>
      </div>
    );
  }

  // _unlinked branch — honest grouping note + the holdings list.
  if (thesisId === '_unlinked') {
    return (
      <div className="flex min-h-full flex-col">
        <PortfolioSectionNav active="theses" />
        <div className={`${SUBPAGE_MAX} flex-1 space-y-8 py-6 md:py-8`}>
          <div className="space-y-3">
            <Link
              href="/portfolio/theses"
              className="inline-flex items-center gap-2 text-sm text-accent hover:underline"
            >
              <ArrowLeft size={16} /> Back to Theses
            </Link>
            <h1 className="font-display text-2xl text-ink">Unlinked expressions</h1>
            <p className="max-w-2xl text-sm leading-relaxed text-ink-soft">
              These holdings aren&apos;t yet tied to a named thesis. They&apos;ll roll up under a
              market view once the link is recorded.
            </p>
          </div>
          <ThesisHoldingsExpressing positions={expressingPositions} />
        </div>
      </div>
    );
  }

  const t = thesis!;
  const pips = confidenceToPips(t.confidence);
  const confidenceLabel =
    t.confidence != null ? `${Math.round(t.confidence * 100)}% confidence` : 'Confidence not set';

  return (
    <div className="flex min-h-full flex-col">
      <PortfolioSectionNav active="theses" />
      <div className={`${SUBPAGE_MAX} flex-1 space-y-8 py-6 md:py-8`}>
        {/* Header — claim / conviction / horizon / status */}
        <div className="space-y-4">
          <Link
            href="/portfolio/theses"
            className="inline-flex items-center gap-2 text-sm text-accent hover:underline"
          >
            <ArrowLeft size={16} /> Back to Theses
          </Link>

          <div className="flex flex-wrap items-start justify-between gap-4">
            <h1 className="font-display text-3xl leading-tight text-ink">{t.name}</h1>
            <AsOfBadge date={lastUpdated} />
          </div>

          <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
            <div className="flex items-center gap-2">
              <ConvictionMeter value={pips} max={CONFIDENCE_PIPS} srLabel={confidenceLabel} />
              <span className="text-xs text-ink-mute tabular-nums">{confidenceLabel}</span>
            </div>
            {t.horizon ? (
              <span className="rounded-md border border-hair px-2 py-0.5 text-[11px] text-ink-soft">
                {t.horizon}
              </span>
            ) : null}
            {t.vehicle ? (
              <span className="font-mono text-xs text-ink-soft">{t.vehicle}</span>
            ) : null}
            {isNonActive(t.status) ? (
              <span className="rounded-full border border-warn/40 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-warn">
                {t.status}
              </span>
            ) : null}
          </div>

          {t.notes ? (
            <p className="max-w-3xl text-sm leading-relaxed text-ink-soft">{t.notes}</p>
          ) : null}
        </div>

        {/* Two criteria columns — the credibility win */}
        <ThesisCriteriaColumns
          validation={t.validation_criteria}
          invalidation={t.invalidation_criteria}
        />

        {/* Holdings expressing this thesis (F4 join) */}
        <ThesisHoldingsExpressing positions={expressingPositions} />

        {/* Slim provenance strip → Pipeline day (never re-renders markdown) */}
        <ThesisProvenanceStrip date={lastUpdated} documentKey="digest" />
      </div>
    </div>
  );
}
