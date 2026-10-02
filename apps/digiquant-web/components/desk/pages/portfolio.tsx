"use client";

import { useEffect, useState } from "react";
import { BLOCKS, layoutFor, type BlockKind } from "../../../../../clients/digiquant-tui/src/catalog";
import { EMPTY_READ, STUB_READ, isStubEnvelope, type ReadResult } from "../../../../../clients/digiquant-tui/src/read";
import { readDeskBlock } from "../read-block";
import { DeskPane, usePaneFocus } from "./pane";

/** Portfolio family. Tearsheet and performance share one layout. No dossier. */
export const PORTFOLIO_PATHS = [
  "/portfolio",
  "/portfolio/holdings",
  "/portfolio/attribution",
  "/portfolio/ledger",
  "/portfolio/theses",
  "/portfolio/tearsheet",
  "/performance",
] as const;

export type PortfolioPath = (typeof PORTFOLIO_PATHS)[number];

export function isPortfolioPath(path: string): path is PortfolioPath {
  return (PORTFOLIO_PATHS as readonly string[]).includes(path);
}

export type PortfolioBlock = {
  id: string;
  title: string;
  route: string;
  kind: BlockKind;
  x: number;
  y: number;
  w: number;
  h: number;
};

/** One catalog placement per block. A dossier route is never included. */
export function portfolioBlocks(path: string): PortfolioBlock[] {
  if (!isPortfolioPath(path)) return [];
  const blocks: PortfolioBlock[] = [];
  for (const placement of layoutFor(path)) {
    const def = BLOCKS[placement.id];
    if (!def || placement.id === "dossier" || def.route.includes("/dossier")) continue;
    blocks.push({
      id: placement.id,
      title: def.title,
      route: def.route,
      kind: def.kind,
      x: placement.x,
      y: placement.y,
      w: placement.w,
      h: placement.h,
    });
  }
  return blocks;
}

/** Stub envelopes stay one sentence. Empty reads stay empty. Nothing is filled in. */
export function visibleRead(read: ReadResult | undefined): {
  status: ReadResult["status"] | "loading";
  lines: string[];
  asOf: string | null;
} {
  if (!read) return { status: "loading", lines: ["loading…"], asOf: null };
  if (read.status === "stub" || isStubEnvelope(read.lines)) {
    return { status: "stub", lines: [STUB_READ], asOf: null };
  }
  return {
    status: read.status,
    lines: read.lines.length > 0 ? read.lines : [EMPTY_READ],
    asOf: read.asOf,
  };
}

const tone: Record<ReadResult["status"] | "loading", string> = {
  ok: "text-ink",
  empty: "text-ink-mute",
  loading: "text-ink-mute",
  stub: "text-ink-soft",
  error: "text-ink-soft",
};

type Reads = Record<string, ReadResult | undefined>;

function PortfolioDesk({ path, reads }: { path: PortfolioPath; reads?: Reads }) {
  const [fetched, setFetched] = useState<{ path: string; reads: Record<string, ReadResult> }>({
    path: "",
    reads: {},
  });
  const blocks = portfolioBlocks(path);
  const panes = usePaneFocus(blocks.map((block) => block.id));
  const controlled = reads !== undefined;
  const shown = controlled ? reads : fetched.path === path ? fetched.reads : {};

  useEffect(() => {
    if (controlled) return;
    const ac = new AbortController();
    let cancel = false;
    for (const block of portfolioBlocks(path)) {
      void readDeskBlock(block.route, block.kind, ac.signal).then((result) => {
        if (cancel) return;
        setFetched((prev) => {
          const base = prev.path === path ? prev.reads : {};
          return { path, reads: { ...base, [block.id]: result } };
        });
      });
    }
    return () => {
      cancel = true;
      ac.abort();
    };
  }, [controlled, path]);

  return (
    <div className="grid h-full min-h-0 flex-1 grid-cols-12 grid-rows-12 gap-1 p-1">
      {blocks.map((block) => {
        const view = visibleRead(shown[block.id]);
        return (
          <div
            key={block.id}
            className="min-h-0 min-w-0"
            style={{ gridColumn: `${block.x} / span ${block.w}`, gridRow: `${block.y} / span ${block.h}` }}
          >
            <DeskPane
              title={block.title}
              route={block.route}
              asOf={view.asOf}
              lines={view.lines}
              tone={tone[view.status]}
              focused={panes.focus === block.id}
              onFocus={() => panes.focusAt(block.id)}
              onNext={panes.next}
            />
          </div>
        );
      })}
    </div>
  );
}

type DeskProps = { reads?: Reads };

function page(path: PortfolioPath, props: DeskProps) {
  return <PortfolioDesk path={path} reads={props.reads} />;
}

export function PortfolioPage(props: DeskProps) {
  return page("/portfolio", props);
}

export function HoldingsPage(props: DeskProps) {
  return page("/portfolio/holdings", props);
}

export function AttributionPage(props: DeskProps) {
  return page("/portfolio/attribution", props);
}

export function LedgerPage(props: DeskProps) {
  return page("/portfolio/ledger", props);
}

export function ThesesPage(props: DeskProps) {
  return page("/portfolio/theses", props);
}

export function TearsheetPage(props: DeskProps) {
  return page("/portfolio/tearsheet", props);
}

export function PerformancePage(props: DeskProps) {
  return page("/performance", props);
}

/** Renders a portfolio-family path. Any other path, including a dossier, is empty. */
export function PortfolioPages({ path, ...props }: DeskProps & { path: string }) {
  if (!isPortfolioPath(path)) return null;
  return page(path, props);
}
