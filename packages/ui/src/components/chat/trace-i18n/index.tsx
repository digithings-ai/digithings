"use client";

import { createContext, useContext, useMemo, type ReactNode } from "react";
import { useEmbedChatPrefsOptional } from "../stock/embed-chat-prefs";
import { DEFAULT_TRACE_LOCALE, createTraceT, type TraceT } from "./core";

export * from "./core";
export type { TraceStrings, PluralMessage } from "./types";

const TraceLocaleContext = createContext<string | null>(null);

/** Pins the trace language below it (tests, hosts without chat prefs). */
export function TraceLocaleProvider({ locale, children }: { locale: string; children: ReactNode }) {
  return <TraceLocaleContext.Provider value={locale}>{children}</TraceLocaleContext.Provider>;
}

/** Trace strings in the session language: the provider, else the chat prefs `/language`, else English. */
export function useTraceT(): TraceT {
  const pinned = useContext(TraceLocaleContext);
  const prefs = useEmbedChatPrefsOptional();
  const locale = pinned ?? prefs?.prefs.language ?? DEFAULT_TRACE_LOCALE;
  return useMemo(() => createTraceT(locale), [locale]);
}
