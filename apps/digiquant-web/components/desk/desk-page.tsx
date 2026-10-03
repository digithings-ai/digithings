"use client";

import { useEffect, useState, type ReactNode } from "react";
import { BLOCKS, layoutFor, pageByPath } from "../../../../clients/digiquant-tui/src/catalog";
import type { ReadResult } from "../../../../clients/digiquant-tui/src/read";
import { DeskFrame } from "./desk-frame";
import { DeskReadout } from "./desk-view";
import { BriefPage } from "./pages/brief";
import { PipelinePage } from "./pages/pipeline";
import { isInviteSurface } from "./public-surface";
import { PortfolioPages, isPortfolioPath } from "./pages/portfolio";
import { StrategiesPages } from "./pages/strategies";
import { readDeskBlock } from "./read-block";

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
  const [reads, setReads] = useState<Record<string, ReadResult>>({});

  useEffect(() => {
    const placements = layoutFor(path);
    const ac = new AbortController();
    let cancel = false;
    for (const placement of placements) {
      const def = BLOCKS[placement.id];
      void readDeskBlock(def.route, def.kind, ac.signal).then((result) => {
        if (cancel) return;
        setReads((prev) => ({ ...prev, [placement.id]: result }));
      });
    }
    return () => {
      cancel = true;
      ac.abort();
    };
  }, [path]);

  return <DeskReadout path={path} reads={reads} />;
}

/** Loads the current page. A mounted page fetches its own reads. */
export function DeskPage({ path }: { path: string }) {
  if (isInviteSurface(path)) {
    return (
      <DeskFrame current="/brief">
        <p className="m-0 px-3 py-6 text-[0.75rem] leading-[1.5] text-ink-mute">This page is not on the public desk.</p>
      </DeskFrame>
    );
  }
  if (mountedDeskKind(path)) {
    return (
      <DeskFrame current={path}>
        <DeskBody path={path} />
      </DeskFrame>
    );
  }
  const known = pageByPath(path);
  if (!known) {
    return (
      <DeskFrame current="/brief">
        <DeskReadout path="/brief" reads={{}} />
      </DeskFrame>
    );
  }
  return (
    <DeskFrame current={known.path}>
      <DeskCatalogLive path={known.path} />
    </DeskFrame>
  );
}
