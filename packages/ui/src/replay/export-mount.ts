"use client";

import { useSyncExternalStore } from "react";
import { flushSync } from "react-dom";

let keep = false;
const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** True only while an HTML export is reading the page. */
export function useExportKeepMounted(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => keep,
    () => false,
  );
}

/** Mount closed panels for the export, then commit before the caller reads the DOM. */
export function setExportKeepMounted(value: boolean): void {
  if (keep === value) return;
  keep = value;
  flushSync(() => {
    for (const listener of listeners) listener();
  });
}
