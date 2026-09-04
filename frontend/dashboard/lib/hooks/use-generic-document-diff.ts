'use client';

/* eslint-disable react-hooks/set-state-in-effect -- async fetch + URL-driven compare preset lifecycle */
import { useEffect, useRef, useState } from 'react';
import {
  fetchDocumentDiffAnchors,
  loadDocumentDiff,
  type DocumentDiffCompareKind,
  type DocumentDiffPair,
} from '@/lib/queries';

/** Anchors + diff pair fetch lifecycle for GenericDiffDocumentView. */
export function useGenericDocumentDiff(
  docDate: string,
  documentKey: string,
  payload: Record<string, unknown> | null,
  viewScope: 'current' | 'difference'
) {
  const [compareKind, setCompareKind] = useState<DocumentDiffCompareKind>('previous_day');
  const [customCompareDate, setCustomCompareDate] = useState('');
  const [anchorsLoading, setAnchorsLoading] = useState(true);
  const [pairLoading, setPairLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [anchors, setAnchors] = useState<{ prev: string | null; base: string | null }>({
    prev: null,
    base: null,
  });
  const [pair, setPair] = useState<DocumentDiffPair | null>(null);
  const preferPreviousRef = useRef(false);

  const openDifferenceView = () => {
    preferPreviousRef.current = true;
  };

  useEffect(() => {
    let cancelled = false;
    setAnchorsLoading(true);
    setError(null);
    fetchDocumentDiffAnchors(docDate, documentKey, payload)
      .then((a) => {
        if (!cancelled) setAnchors({ prev: a.previousDayDate, base: a.deltaBaselineDate });
      })
      .catch(() => {
        if (!cancelled) setAnchors({ prev: null, base: null });
      })
      .finally(() => {
        if (!cancelled) setAnchorsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [docDate, documentKey, payload]);

  useEffect(() => {
    if (!preferPreviousRef.current || viewScope !== 'difference' || anchorsLoading) return;
    preferPreviousRef.current = false;
    setCustomCompareDate('');
    if (anchors.prev) setCompareKind('previous_day');
    else if (anchors.base) setCompareKind('delta_baseline');
  }, [anchors.prev, anchors.base, anchorsLoading, viewScope]);

  useEffect(() => {
    if (viewScope === 'current') return;
    let cancelled = false;
    setPairLoading(true);
    setError(null);
    loadDocumentDiff(docDate, documentKey, payload, {
      compare: compareKind,
      customCompareDate: compareKind === 'custom_date' ? customCompareDate : undefined,
    })
      .then((p) => {
        if (!cancelled) setPair(p);
      })
      .catch((e) => {
        if (!cancelled) {
          setPair(null);
          setError(e instanceof Error ? e.message : 'Failed to load diff');
        }
      })
      .finally(() => {
        if (!cancelled) setPairLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [docDate, documentKey, payload, compareKind, customCompareDate, viewScope]);

  return {
    compareKind,
    setCompareKind,
    customCompareDate,
    setCustomCompareDate,
    anchorsLoading,
    pairLoading,
    error,
    setError,
    anchors,
    pair,
    setPair,
    openDifferenceView,
  };
}
