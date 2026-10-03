"use client";

import { useEffect, useState, type ReactNode } from "react";
import { BLOCKS, layoutFor } from "../../../../clients/digiquant-tui/src/catalog";
import type { ReadResult } from "../../../../clients/digiquant-tui/src/read";
import { DeskFrame } from "./desk-frame";
import { DeskView } from "./desk-view";
import { BriefPage } from "./pages/brief";
import { PipelinePage } from "./pages/pipeline";
import { isInviteSurface } from "./public-surface";
import { PortfolioPages, isPortfolioPath } from "./pages/portfolio";
import { StrategiesPages } from "./pages/strategies";
import { readDeskBlock } from "./read-block";

const STRATEGY_PATHS = new Set(["/strategies", "/strategies/detail", "/strategies/deploy"]);

function isMountedPath(path: string): boolean {
  return path === "/brief" || path === "/pipeline" || isPortfolioPath(path) || STRATEGY_PATHS.has(path);
}

/** Pages that paint their own blocks. Everything else stays on the catalog grid. */
function mountedPage(path: string): ReactNode | null {
  if (path === "/brief") return <BriefPage />;
  if (isPortfolioPath(path)) return <PortfolioPages path={path} />;
  if (path === "/pipeline") return <PipelinePage />;
  if (STRATEGY_PATHS.has(path)) return <StrategiesPages path={path} />;
  return null;
}

/** Loads the current page's official reads. A mounted page fetches its own. */
export function DeskPage({ path }: { path: string }) {
  const page = mountedPage(path);
  const [reads, setReads] = useState<Record<string, ReadResult>>({});

  useEffect(() => {
    if (isMountedPath(path) || isInviteSurface(path)) return;
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

  if (isInviteSurface(path)) {
    return (
      <DeskFrame current="/brief">
        <p className="m-0 px-3 py-6 text-[0.75rem] leading-[1.5] text-ink-mute">This page is not on the public desk.</p>
      </DeskFrame>
    );
  }
  if (page) {
    return <DeskFrame current={path}>{page}</DeskFrame>;
  }
  return <DeskView path={path} reads={reads} />;
}
