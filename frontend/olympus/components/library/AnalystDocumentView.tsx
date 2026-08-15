'use client';

import { SafeMarkdown } from '@/components/SafeMarkdown';
import { parseAnalystPayload } from '@/lib/queries';
import { Badge } from '@/components/ui';
import { SignedConvictionBadge } from '@/components/shared/signed-conviction-badge';
import AnalystDossierCard from '@/components/portfolio/tickers/AnalystDossierCard';

/**
 * Structured view for Hermes per-ticker analyst specialist reports (`analyst/{ticker}`).
 * Converges on `AnalystDossierCard` (#1562 PR4) so the library path and the
 * Ticker Dossier route (`components/portfolio/tickers`) render the SAME analyst
 * payload identically — thesis, bull/bear case, tailwinds/headwinds, risks,
 * technicals/expectations/fundamentals, price targets, and sources. All of
 * these fields are present in the live `documents.payload` shape
 * (`digiquant/.../hermes/models/analyst.py:AnalystPayload`) — all 80 frozen
 * analyst docs carry bull_case/bear_case/headwinds/tailwinds (#1562 blueprint
 * §3), so they are no longer discarded here.
 *
 * The ticker/stance/conviction identity row is kept local (rather than folded
 * into `AnalystDossierCard`, which omits it — the dossier route's page header
 * already carries that identity) and mirrors `TickerDossierView`'s neutral
 * `Badge` + `SignedConvictionBadge` treatment: CANON reserves `--up`/`--down`
 * for realized P&L / signed-conviction values, never a qualitative stance label.
 */

export default function AnalystDocumentView({
  payload,
  fallbackMarkdown,
}: {
  payload: Record<string, unknown> | null;
  fallbackMarkdown: string;
}) {
  const analyst = parseAnalystPayload(payload);

  // No recognizable analyst fields (or no payload at all) — fall back to markdown.
  if (!analyst || (!analyst.thesis.trim() && !analyst.stance.trim())) {
    return <SafeMarkdown>{fallbackMarkdown}</SafeMarkdown>;
  }

  return (
    <div className="space-y-4 text-sm">
      <div className="flex flex-wrap items-center gap-3">
        {analyst.ticker && (
          <span className="font-mono text-base font-semibold text-accent">{analyst.ticker}</span>
        )}
        {analyst.stance && (
          <Badge variant="default">
            <span className="capitalize">{analyst.stance}</span>
          </Badge>
        )}
        {analyst.conviction_score != null && (
          <SignedConvictionBadge value={analyst.conviction_score} />
        )}
      </div>

      <AnalystDossierCard payload={analyst} asOf={null} />
    </div>
  );
}
