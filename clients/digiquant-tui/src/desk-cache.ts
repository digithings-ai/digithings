import { BLOCKS } from "./catalog";
import { createDeskStore, kindsByRoute, uniqueRoutes } from "./desk-store";
import { readBlock, type ReadResult } from "./read";

const API = (process.env.DQ_API_URL ?? "http://127.0.0.1:8788").replace(/\/+$/, "");
const KIND_BY_ROUTE = kindsByRoute(BLOCKS);

/** How often the terminal desk re-reads every dataset it has shown. */
export const DESK_REFRESH_MS = 30_000;

/**
 * Every desk dataset, held once.
 *
 * The pages draw from the catalog, so a dataset is identified by its route and
 * one read serves every block that asks for it. The store is the only thing
 * that talks to the network: a page switch reads from it and costs nothing.
 */
export const deskCache = createDeskStore<ReadResult>({
  refreshMs: DESK_REFRESH_MS,
  fetchDataset: (route, signal) => readBlock(API, route, KIND_BY_ROUTE.get(route) ?? "fields", signal),
});

/** Read every dataset and keep them fresh. Safe to call more than once. */
export function preloadDeskCache(): void {
  deskCache.preload(uniqueRoutes(BLOCKS));
}
