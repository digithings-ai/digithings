"use client";

/**
 * Read embed UI overrides from the iframe URL.
 *
 * Why not `useMemo(() => readEmbedUiParams(window.location.search), [])`?
 * That factory returns `{}` during SSR (`window` missing). On the client,
 * React 19 / Next hydration can keep the server-computed memo value (or
 * recover from a style-attribute mismatch by retaining the server DOM), so
 * the wrapper's `style` stays null even though `location.search` has a valid
 * `?accent=%23b5562b`. Welcome/suggestions often still "work" because they
 * also arrive from the tenant-config fetch, which triggers a later client
 * re-render — but if the live registry omits `accent` (or the URL is the
 * only source), terracotta never applies.
 *
 * useSyncExternalStore is the React-recommended browser-API read: server
 * snapshot is empty (no hydration mismatch), client snapshot reads
 * location.search. Avoids `setState` inside `useEffect`
 * (`react-hooks/set-state-in-effect`). Snapshot is cached by search string
 * so Object.is stays stable across renders.
 */

import { useSyncExternalStore } from "react";
import { readEmbedUiParams, type EmbedUiParams } from "@/lib/embed-ui-params";

const EMPTY: EmbedUiParams = {};

let cachedSearch: string | null = null;
let cachedParams: EmbedUiParams = EMPTY;

function subscribe(onStoreChange: () => void): () => void {
  window.addEventListener("popstate", onStoreChange);
  return () => window.removeEventListener("popstate", onStoreChange);
}

function getSnapshot(): EmbedUiParams {
  const search = window.location.search;
  if (search !== cachedSearch) {
    cachedSearch = search;
    cachedParams = readEmbedUiParams(search);
  }
  return cachedParams;
}

function getServerSnapshot(): EmbedUiParams {
  return EMPTY;
}

export function useEmbedUiParams(): EmbedUiParams {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
