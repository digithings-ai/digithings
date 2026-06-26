'use client';

import { createContext, useContext } from 'react';
import type { ReactNode } from 'react';

import type { WatchlistApi } from './useWatchlist';

/** The five twelve-x workspace tabs. */
export type TwelveXTab = 'today' | 'consensus' | 'intelligence' | 'events' | 'matrix';

/** A cross-surface navigation intent fired from any tab. */
export type CrossLink =
  | { kind: 'currency'; currency: string }
  | { kind: 'brief'; sourceFile: string; runDate: string | null }
  | { kind: 'event'; eventName: string | null; externalId?: string | null }
  | { kind: 'tab'; tab: TwelveXTab };

/** Shared workspace plumbing every tab can reach via `useTwelveX()`. */
export interface TwelveXContextValue {
  runDate: string | null;
  crossLink: (l: CrossLink) => void;
  openBrief: (sourceFile: string, runDate: string | null) => void;
  watchlist: WatchlistApi;
}

export const TwelveXContext = createContext<TwelveXContextValue | null>(null);

export function useTwelveX(): TwelveXContextValue {
  const v = useContext(TwelveXContext);
  if (!v) throw new Error('useTwelveX must be used within TwelveXProvider');
  return v;
}

export function TwelveXProvider({
  value,
  children,
}: {
  value: TwelveXContextValue;
  children: ReactNode;
}) {
  return <TwelveXContext.Provider value={value}>{children}</TwelveXContext.Provider>;
}
