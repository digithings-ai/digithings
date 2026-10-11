import { BLOCKS } from "../../../../clients/digiquant-tui/src/catalog";
import { createDeskStore, kindsByRoute, uniqueRoutes } from "../../../../clients/digiquant-tui/src/desk-store";
import type { ReadResult } from "../../../../clients/digiquant-tui/src/read";
import { readDeskBlock } from "./read-block";

const KIND_BY_ROUTE = kindsByRoute(BLOCKS);

/** How often the web desk re-reads every dataset it has shown. */
export const DESK_REFRESH_MS = 30_000;

/**
 * Every desk dataset, held once, shared by the whole browser session.
 *
 * Same store the terminal desk uses, with the web reader plugged in: the web
 * resolves its API base per request, the terminal resolves it from the
 * environment. A page switch reads from here and costs nothing, so no desk
 * page opens on a `loading...` panel while the answer is already in memory.
 */
export const deskCache = createDeskStore<ReadResult>({
  refreshMs: DESK_REFRESH_MS,
  fetchDataset: (route, signal) => readDeskBlock(route, KIND_BY_ROUTE.get(route) ?? "fields", signal),
});

/** Read every dataset and keep them fresh. Safe to call more than once. */
export function preloadDeskCache(): void {
  deskCache.preload(uniqueRoutes(BLOCKS));
}
