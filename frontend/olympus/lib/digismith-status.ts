'use client';

import { useEffect, useState } from 'react';

export type StatusState = 'ok' | 'degraded' | 'error' | 'unknown';

export interface DigiSmithStatus {
  /** false when NEXT_PUBLIC_DIGISMITH_URL is unset — the dot renders nothing. */
  enabled: boolean;
  state: StatusState;
}

const POLL_MS = 60_000;
const FETCH_TIMEOUT_MS = 8_000;

/**
 * Poll DigiSmith `GET /v1/status` and map it to an operator health state (#1231).
 *
 * - **Disabled by default:** returns `enabled:false` unless
 *   `NEXT_PUBLIC_DIGISMITH_URL` is set, so local dev without the stack shows no dot.
 * - **Non-blocking:** the fetch runs in an effect after mount; initial state is
 *   `unknown` (grey), so it never blocks or delays first paint.
 * - **Graceful:** any failure (unreachable, CSP/CORS, timeout, non-200) degrades to
 *   `unknown`/`error` — it never throws.
 * - **No PII:** only the derived state is stored — no request ids, hosts, or other
 *   diagnostic fields from the response reach the client UI.
 *
 * Mapping: 200 + `tracing_configured` → `ok`; 200 + not configured → `degraded`;
 * non-200 → `error`; network/CSP/timeout failure → `unknown`.
 */
export function useDigiSmithStatus(pollMs: number = POLL_MS): DigiSmithStatus {
  const base = process.env.NEXT_PUBLIC_DIGISMITH_URL;
  const enabled = Boolean(base);
  const [state, setState] = useState<StatusState>('unknown');

  useEffect(() => {
    if (!base) return;
    let cancelled = false;
    const endpoint = `${base.replace(/\/+$/, '')}/v1/status`;

    const check = async () => {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
      try {
        const res = await fetch(endpoint, {
          signal: controller.signal,
          headers: { accept: 'application/json' },
        });
        if (cancelled) return;
        if (!res.ok) {
          setState('error');
          return;
        }
        const data = (await res.json()) as { tracing_configured?: boolean };
        if (!cancelled) setState(data.tracing_configured ? 'ok' : 'degraded');
      } catch {
        if (!cancelled) setState('unknown');
      } finally {
        clearTimeout(timer);
      }
    };

    void check();
    const id = setInterval(() => void check(), pollMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [base, pollMs]);

  return { enabled, state };
}
