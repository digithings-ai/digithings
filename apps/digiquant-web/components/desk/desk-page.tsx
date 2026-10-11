"use client";

import { useEffect, useMemo, type ReactNode } from "react";
import { BLOCKS, layoutFor, pageByPath } from "../../../../clients/digiquant-tui/src/catalog";
import type { ReadResult } from "../../../../clients/digiquant-tui/src/read";
import { DeskFrame } from "./desk-frame";
import { DeskReadout } from "./desk-view";
import { BriefPage } from "./pages/brief";
import { PipelinePage } from "./pages/pipeline";
import { isInviteSurface } from "./public-surface";
import { PortfolioPages, isPortfolioPath } from "./pages/portfolio";
import { StrategiesPages } from "./pages/strategies";
import { deskCache, preloadDeskCache } from "./desk-cache";
import { useDeskReads } from "../../../../clients/digiquant-tui/src/desk-store-react";

const STRATEGY_PATHS = new Set(["/strategies", "/strategies/detail", "/strategies/deploy"]);

export type MountedDeskKind = "brief" | "portfolio" | "pipeline" | "strategies";

/** Which dedicated desk page this path is. Invite paths and web-only slots are not these pages. */
export function mountedDeskKind(path: string): MountedDeskKind | null {
  if (isInviteSurface(path)) return null;
  if (path === "/brief") return "brief";
  if (isPortfolioPath(path)) return "portfolio";
  if (path === "/pipeline") return "pipeline";
  if (STRATEGY_PATHS.has(path)) return "strategies";
  return null;
}

/** The page component `/app` mounts, without the web frame. */
export function DeskBody({ path }: { path: string }): ReactNode {
  const kind = mountedDeskKind(path);
  switch (kind) {
    case "brief":
      return <BriefPage />;
    case "portfolio":
      return <PortfolioPages path={path} />;
    case "pipeline":
      return <PipelinePage />;
    case "strategies":
      return <StrategiesPages path={path} />;
    case null:
      return null;
    default: {
      const never: never = kind;
      return never;
    }
  }
}

/** Catalog pages that have no dedicated component. Same blocks as the web desk. */
export function DeskCatalogLive({ path }: { path: string }) {
  const placements = useMemo(() => layoutFor(path), [path]);
  const routes = useMemo(
    () => placements.map((placement) => BLOCKS[placement.id].route),
    [placements],
  );
  const routeReads = useDeskReads(deskCache, routes);
  const reads = useMemo(() => {
    const byBlock: Record<string, ReadResult | undefined> = {};
    for (const placement of placements) {
      byBlock[placement.id] = routeReads[BLOCKS[placement.id].route];
    }
    return byBlock;
  }, [placements, routeReads]);

  // One read for every desk dataset, started once. Every page this desk can
  // reach is a dataset the cache already holds, so the reads above render from
  // the cache and the panel never shows a loading line.
  useEffect(() => {
    preloadDeskCache();
  }, []);

  return <DeskReadout path={path} reads={reads} />;
}

/** The page body only. The shell around it stays mounted across navigations. */
export function DeskRouteBody({ path }: { path: string }): ReactNode {
  if (isInviteSurface(path)) {
    return (
      <p className="m-0 px-3 py-6 text-[0.75rem] leading-[1.5] text-ink-mute">This page is not on the public desk.</p>
    );
  }
  if (mountedDeskKind(path)) return <DeskBody path={path} />;
  const known = pageByPath(path);
  if (!known) return <DeskReadout path="/brief" reads={{}} />;
  return <DeskCatalogLive path={known.path} />;
}

function framePath(path: string): string {
  if (isInviteSurface(path)) return "/brief";
  if (mountedDeskKind(path)) return path;
  return pageByPath(path)?.path ?? "/brief";
}

/** Loads the current page. A mounted page fetches its own reads. */
export function DeskPage({ path }: { path: string }) {
  return (
    <DeskFrame current={framePath(path)}>
      <DeskRouteBody path={path} />
    </DeskFrame>
  );
}
