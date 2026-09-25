/**
 * Slice 0006 — thin mount adapters reconciling the three slice idioms into
 * one (envelope's `AddRoute` shape wins; no slice logic is rewritten here).
 *
 * - envelope (slice 0003) mounts directly via `AddRoute`.
 * - brief / performance / kpis-live / benchmarks (slice 0004) register via
 *   `onGet:(path,handler)=>void` — `adaptOnGet` adapts that onto `AddRoute`.
 * - ledger (slice 0005) mounts via `tryHandleLedger(req,book)=>Response|null`.
 */

import type { AddRoute, RouteHandler } from './envelope';

export type OnGet = (path: string, handler: RouteHandler) => void;

/** Adapt a slice-0004 `onGet` registrar onto the envelope `AddRoute` shape. */
export function adaptOnGet(addRoute: AddRoute): OnGet {
  return (path, handler) => addRoute('GET', path, handler);
}
