"use client";

import { useSyncExternalStore } from "react";
import {
  DIGI_CHAT_WARMUP_EVENT,
  getDigichatWarmupPhase,
  type DigichatWarmupPhase,
} from "./boot-signal";

function subscribe(cb: () => void): () => void {
  window.addEventListener(DIGI_CHAT_WARMUP_EVENT, cb);
  return () => window.removeEventListener(DIGI_CHAT_WARMUP_EVENT, cb);
}

/** Current service warm-up phase (see setDigichatWarmupPhase). */
export function useDigichatWarmupPhase(): DigichatWarmupPhase {
  return useSyncExternalStore(subscribe, getDigichatWarmupPhase, () => "idle");
}
