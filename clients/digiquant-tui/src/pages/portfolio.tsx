/** @jsxImportSource @opentui/react */
import { useEffect, useState } from "react";
import { BLOCKS, layoutFor, type BlockKind } from "../catalog";
import { COLS, ROWS } from "../grid";
import { EMPTY_READ, STUB_READ, isStubEnvelope, readBlock, type ReadResult } from "../read";

const API = (process.env.DQ_API_URL ?? "http://127.0.0.1:8788").replace(/\/+$/, "");

const BG = "#14120f";
const INK = "#e7e1d6";
const DIM = "#8a8175";
const LINE = "#3a342c";
const BAD = "#c47a6a";
const OK = "#7d9a78";

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

const share = (cells: number, total: number): `${number}%` => `${(cells / total) * 100}%` as `${number}%`;

const tone = (status: ReadResult["status"] | "loading") => {
  if (status === "ok") return INK;
  if (status === "empty" || status === "loading") return DIM;
  return BAD;
};

const border = (status: ReadResult["status"] | "loading") => {
  if (status === "ok") return OK;
  if (status === "empty" || status === "loading") return LINE;
  return BAD;
};

type Reads = Record<string, ReadResult | undefined>;

function PortfolioDesk({ path, api, reads }: { path: PortfolioPath; api: string; reads?: Reads }) {
  const [fetched, setFetched] = useState<{ path: string; reads: Record<string, ReadResult> }>({
    path: "",
    reads: {},
  });
  const controlled = reads !== undefined;
  const shown = controlled ? reads : fetched.path === path ? fetched.reads : {};

  useEffect(() => {
    if (controlled) return;
    const ac = new AbortController();
    let cancel = false;
    for (const block of portfolioBlocks(path)) {
      void readBlock(api, block.route, block.kind, ac.signal).then((result) => {
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
  }, [api, controlled, path]);

  return (
    <box width="100%" height="100%" position="relative" backgroundColor={BG}>
      {portfolioBlocks(path).map((block) => {
        const view = visibleRead(shown[block.id]);
        return (
          <box
            key={block.id}
            position="absolute"
            left={share(block.x - 1, COLS)}
            top={share(block.y - 1, ROWS)}
            width={share(block.w, COLS)}
            height={share(block.h, ROWS)}
            border
            borderColor={border(view.status)}
            title={block.title}
            titleColor={DIM}
            bottomTitle={view.asOf ? `as of ${view.asOf}` : block.route}
            overflow="hidden"
            paddingLeft={1}
            paddingRight={1}
          >
            <text fg={tone(view.status)}>{view.lines.join("\n")}</text>
          </box>
        );
      })}
    </box>
  );
}

type DeskProps = { api?: string; reads?: Reads };

function page(path: PortfolioPath, props: DeskProps) {
  return <PortfolioDesk path={path} api={props.api ?? API} reads={props.reads} />;
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
