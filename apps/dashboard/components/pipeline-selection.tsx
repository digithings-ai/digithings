'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { BASELINE_PIPELINE, resolvePipelineId, usePipelines, withPipelineParam, type PipelineRef, type PipelineScope } from '@/lib/pipelines';

const KEY = 'dashboard-pipeline';

interface PipelineSelection {
  pipelines: readonly PipelineRef[];
  pipelineId: string;
  scope: PipelineScope;
  setPipelineId: (id: string) => void;
}

const Ctx = createContext<PipelineSelection | null>(null);

function readStored(): string | null {
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

/**
 * Which pipeline the dashboard is showing. Server and first client render use
 * baseline (static prerender stays stable); `?pipeline=` then localStorage apply
 * after mount. Baseline is omitted from the URL.
 */
export function PipelineSelectionProvider({ children }: { children: ReactNode }) {
  const pipelines = usePipelines();
  const [pipelineId, setId] = useState<string>(BASELINE_PIPELINE.id);

  useEffect(() => {
    const fromUrl = new URLSearchParams(window.location.search).get('pipeline');
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time post-mount read
    setId(resolvePipelineId(fromUrl ?? readStored(), pipelines));
  }, [pipelines]);

  const setPipelineId = useCallback(
    (id: string) => {
      const next = resolvePipelineId(id, pipelines);
      setId(next);
      try {
        window.localStorage.setItem(KEY, next);
      } catch {
        /* device pref only */
      }
      const { pathname, search, hash } = window.location;
      window.history.replaceState(null, '', `${pathname}${withPipelineParam(search, next)}${hash}`);
    },
    [pipelines]
  );

  const value = useMemo<PipelineSelection>(
    () => ({ pipelines, pipelineId, scope: { pipelineId }, setPipelineId }),
    [pipelines, pipelineId, setPipelineId]
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function usePipelineSelection(): PipelineSelection {
  const ctx = useContext(Ctx);
  if (!ctx) {
    const pipelines = [BASELINE_PIPELINE];
    return { pipelines, pipelineId: BASELINE_PIPELINE.id, scope: { pipelineId: BASELINE_PIPELINE.id }, setPipelineId: () => {} };
  }
  return ctx;
}
