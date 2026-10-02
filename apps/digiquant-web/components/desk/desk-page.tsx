"use client";

import { useEffect, useState } from "react";
import { BLOCKS, layoutFor } from "../../../../clients/digiquant-tui/src/catalog";
import type { ReadResult } from "../../../../clients/digiquant-tui/src/read";
import { DeskView } from "./desk-view";
import { readDeskBlock } from "./read-block";

/** Loads the current page's official reads. A path change drops the previous blocks. */
export function DeskPage({ path }: { path: string }) {
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

  return <DeskView path={path} reads={reads} />;
}
