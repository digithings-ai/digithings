'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { buildPipelineDayData } from '@/lib/pipeline-graph-data';
import type { PipelineDayData } from '@/lib/pipeline-graph-data';
import type { ExpansionState, LaidOutNode } from '@/lib/pipeline-layout';
import type { PipelineStage } from '@/lib/pipeline-links';
import { parsePipelineParams } from '@/lib/pipeline-links';
import type { RegimeChip } from './PipelineSummaryStrip';
import PipelineSummaryStrip from './PipelineSummaryStrip';
import PipelineDaySelector from './PipelineDaySelector';
import PipelineCanvas from './PipelineCanvas';
import PipelineNodeDetail from './PipelineNodeDetail';

export interface PipelineClientProps {
  /** Initial URL search params (passed from the server page) */
  searchParams?: Record<string, string>;
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function buildInitialExpansion(stage: PipelineStage | undefined): ExpansionState {
  if (!stage) return { expandedStages: new Set(), expandedFanouts: new Set() };
  return { expandedStages: new Set([stage]), expandedFanouts: new Set() };
}

export default function PipelineClient({ searchParams = {} }: PipelineClientProps) {
  const params = useMemo(
    () => parsePipelineParams(new URLSearchParams(new URLSearchParams(searchParams).toString())),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  const [selectedDate, setSelectedDate] = useState(params.date ?? today());
  const [availableDates, setAvailableDates] = useState<string[]>([selectedDate]);
  const [dayData, setDayData] = useState<PipelineDayData>({
    fanoutCounts: {},
    presentKeys: new Set(),
  });

  // Summary strip state
  const [headline, setHeadline] = useState<string | null>(null);
  const [regimeChips] = useState<RegimeChip[]>([]);
  const [decision, setDecision] = useState<string | null>(null);

  // Node detail
  const [activeDocumentKey, setActiveDocumentKey] = useState<string | null>(params.node ?? null);

  const initialExpansion = useMemo(
    () => buildInitialExpansion(params.stage),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  // Load documents for the selected date
  useEffect(() => {
    let cancelled = false;

    void (async () => {
      try {
        const { createClient } = await import('@supabase/supabase-js');
        const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
        const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
        if (!url || !key) return;

        const supabase = createClient(url, key);

        // Load available dates (last 30 days of pipeline runs)
        const { data: dateRows } = await supabase
          .from('documents')
          .select('date')
          .gte('date', new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10))
          .order('date', { ascending: false });

        if (!cancelled && dateRows) {
          const uniqueDates = [...new Set((dateRows as { date: string }[]).map((r) => r.date))].sort().reverse();
          if (uniqueDates.length > 0) setAvailableDates(uniqueDates);
        }

        // Load documents for the selected date
        const { data: docs } = await supabase
          .from('documents')
          .select('document_key')
          .eq('date', selectedDate);

        if (!cancelled && docs) {
          const built = buildPipelineDayData(docs as { document_key: string }[]);
          setDayData(built);
        }

        // Try to fetch digest headline
        const { data: digestRow } = await supabase
          .from('documents')
          .select('content')
          .eq('document_key', 'digest')
          .eq('date', selectedDate)
          .maybeSingle();

        if (!cancelled && digestRow?.content) {
          const firstLine = (digestRow.content as string).split('\n').find((l: string) => l.trim().length > 10);
          if (firstLine) setHeadline(firstLine.replace(/^#+\s*/, '').trim());
        }

        // Try to fetch decision summary
        const { data: decisionRow } = await supabase
          .from('decision_log')
          .select('summary')
          .eq('date', selectedDate)
          .maybeSingle();

        if (!cancelled && decisionRow?.summary) {
          setDecision(decisionRow.summary as string);
        }
      } catch {
        // Supabase not configured or no data — degrade gracefully
      }
    })();

    return () => { cancelled = true; };
  }, [selectedDate]);

  const handleNodeActivate = useCallback((node: LaidOutNode) => {
    setActiveDocumentKey(node.documentKey ?? null);
  }, []);

  return (
    <div className="flex flex-col flex-1 min-h-0 min-w-0">
      {/* Summary strip row */}
      <div className="px-6 pb-3 flex flex-col gap-1">
        <div className="flex items-center gap-3 flex-wrap">
          <PipelineSummaryStrip
            headline={headline}
            regimeChips={regimeChips}
            decision={decision}
          />
          <PipelineDaySelector
            dates={availableDates}
            value={selectedDate}
            onChange={setSelectedDate}
          />
        </div>
      </div>

      {/* Canvas + NodeDetail */}
      <div className="flex flex-1 min-h-0 min-w-0">
        <PipelineCanvas
          day={dayData}
          initialExpansion={initialExpansion}
          selectedNodeId={activeDocumentKey ?? undefined}
          onNodeActivate={handleNodeActivate}
        />

        {activeDocumentKey !== null && (
          <PipelineNodeDetail
            documentKey={activeDocumentKey}
            date={selectedDate}
            onClose={() => setActiveDocumentKey(null)}
          />
        )}
      </div>
    </div>
  );
}
