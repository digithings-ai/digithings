'use client';

import { useMemo } from 'react';
import type { Position, Thesis } from '@/lib/types';
import type { TableRow } from '@/lib/database.types';
import { splitTheses } from '@/lib/theses-ledger';
import { latestDecisionByTicker } from '@/lib/holdings-decisions';
import {
  buildThesisStory,
  attributeWeightToPrimaryThesis,
  type ThesisVehicleRow,
} from '@/lib/thesis-story';
import { ThesisStorySpine } from '@/components/portfolio/theses/ThesisStorySpine';

/**
 * The Portfolio "Theses" tab — a story-first accordion spine (#1562):
 * market theses are the spine; each expands to the vehicles that express it (via
 * the reliable `thesis_vehicles` join, NOT the dead `linked_market_thesis_id`);
 * each vehicle expands to its stock-level story (held metrics + entry/exit +
 * latest signed analyst call + dossier / deliberation links). A trailing shelf
 * carries what the spine cannot place.
 *
 * Data is wired in from PortfolioShellInner so the tab stays a pure, testable
 * render. Production uses latest-available-per-entity (`anchorDate = lastUpdated`);
 * the demo anchor (`DEMO_THESIS_ANCHOR_DATE`) is available but gated off here.
 */
export default function ThesesTab({
  lastUpdated,
  positions,
  theses,
  decisions,
  thesisVehicleRows,
}: {
  lastUpdated: string | null;
  positions: Position[];
  theses: Thesis[];
  decisions: TableRow<'decision_log'>[];
  thesisVehicleRows: ThesisVehicleRow[];
}) {
  const { market, vehicle } = useMemo(() => splitTheses(theses), [theses]);
  const decisionsByTicker = useMemo(() => latestDecisionByTicker(decisions), [decisions]);

  const { stories, unassigned, weightByThesis } = useMemo(() => {
    const result = buildThesisStory(market, thesisVehicleRows, positions, decisionsByTicker, {
      anchorDate: lastUpdated,
      vehicleTheses: vehicle,
    });
    return {
      stories: result.stories,
      unassigned: result.unassigned,
      weightByThesis: attributeWeightToPrimaryThesis(positions, result.effectiveRows),
    };
  }, [market, vehicle, thesisVehicleRows, positions, decisionsByTicker, lastUpdated]);

  return (
    <ThesisStorySpine
      stories={stories}
      unassigned={unassigned}
      weightByThesis={weightByThesis}
      asOf={lastUpdated}
    />
  );
}
