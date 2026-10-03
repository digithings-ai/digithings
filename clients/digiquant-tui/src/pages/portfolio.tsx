/** @jsxImportSource @opentui/react */
import { useEffect, useState } from "react";
import { BLOCKS, layoutFor, type BlockKind } from "../catalog";
import { COLS, ROWS } from "../grid";
import { EMPTY_READ, STUB_READ, isStubEnvelope, presentResponse, readBlock, type ReadResult } from "../read";
import { DANGER, INK, MUTE } from "../theme";
import { PaneFrame, useFocusedPane } from "./pane";
import { attributionBody } from "./attribution-format";
import { holdingsBody } from "./holdings-format";
import { ledgerBody } from "./ledger-format";
import { portfolioBody } from "./portfolio-format";
import { shapeLines, type PaneBody } from "./shape";

const API = (process.env.DQ_API_URL ?? "http://127.0.0.1:8788").replace(/\/+$/, "");

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
  if (status === "empty" || status === "loading") return MUTE;
  return DANGER;
};

type Reads = Record<string, ReadResult | undefined>;

function PortfolioDesk({ path, api, reads }: { path: PortfolioPath; api: string; reads?: Reads }) {
  const [fetched, setFetched] = useState<{ path: string; reads: Record<string, ReadResult> }>({
    path: "",
    reads: {},
  });
  const blocks = portfolioBlocks(path);
  const [focus, setFocus] = useFocusedPane(blocks.length, path);
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
    <box width="100%" height="100%" position="relative">
      {blocks.map((block, index) => {
        const view = visibleRead(shown[block.id]);
        return (
          <box
            key={block.id}
            position="absolute"
            left={share(block.x - 1, COLS)}
            top={share(block.y - 1, ROWS)}
            width={share(block.w, COLS)}
            height={share(block.h, ROWS)}
            onMouseDown={() => setFocus(index)}
          >
            <PaneFrame
              title={block.title}
              status={view.asOf ? `as of ${view.asOf}` : block.route}
              focused={index === focus}
              lines={view.lines}
              ink={tone(view.status)}
            />
          </box>
        );
      })}
    </box>
  );
}

type DeskProps = { api?: string; reads?: Reads };

const STUB_MARKS = ["99.909", "204.04", "legacy_estimate"];

type Loaded = { result: ReadResult; data: unknown };

async function loadPortfolio(api: string, route: string, kind: BlockKind, signal?: AbortSignal): Promise<Loaded> {
  let res: Response;
  try {
    res = await fetch(`${api}${route}`, { signal });
  } catch {
    if (signal?.aborted) return { result: { status: "error", lines: [], asOf: null }, data: null };
    return { result: { status: "error", lines: [`${route}: the official API could not be reached.`], asOf: null }, data: null };
  }
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }
  const result = presentResponse(route, res.status, body, kind);
  if (result.status === "error" || result.status === "stub") return { result, data: null };
  const data = body && typeof body === "object" && "data" in body ? (body as { data: unknown }).data : null;
  return { result, data };
}

function paintPortfolio(id: string, read: Loaded | undefined): { status: ReadResult["status"] | "loading"; blocks: PaneBody; asOf: string | null } {
  if (!read) return { status: "loading", blocks: shapeLines(["loading…"]), asOf: null };
  if (read.result.status === "stub" || read.result.lines.some((line) => STUB_MARKS.some((mark) => line.includes(mark)))) {
    return { status: "stub", blocks: shapeLines([STUB_READ]), asOf: null };
  }
  if (read.result.lines.length === 0 && read.result.status !== "ok") {
    return { status: read.result.status, blocks: shapeLines([EMPTY_READ]), asOf: null };
  }
  return { status: read.result.status, blocks: portfolioBody(id, read.data, read.result), asOf: read.result.asOf };
}

/** `/portfolio` only. Later portfolio pages stay on the line read. */
function PortfolioHome({ api }: { api: string }) {
  const path = "/portfolio";
  const [reads, setReads] = useState<Record<string, Loaded>>({});
  const layout = layoutFor(path);
  const [focus, setFocus] = useFocusedPane(layout.length, path);

  useEffect(() => {
    const placements = layoutFor(path);
    const ac = new AbortController();
    let cancel = false;
    for (const placement of placements) {
      const def = BLOCKS[placement.id];
      if (!def) continue;
      void loadPortfolio(api, def.route, def.kind, ac.signal).then((result) => {
        if (cancel) return;
        setReads((prev) => ({ ...prev, [placement.id]: result }));
      });
    }
    return () => {
      cancel = true;
      ac.abort();
    };
  }, [api]);

  return (
    <box width="100%" height="100%" position="relative">
      {layout.map((placement, index) => {
        const def = BLOCKS[placement.id];
        if (!def) return null;
        const view = paintPortfolio(placement.id, reads[placement.id]);
        return (
          <box
            key={placement.id}
            position="absolute"
            left={share(placement.x - 1, COLS)}
            top={share(placement.y - 1, ROWS)}
            width={share(placement.w, COLS)}
            height={share(placement.h, ROWS)}
            onMouseDown={() => setFocus(index)}
          >
            <PaneFrame
              title={def.title}
              status={view.asOf ? `as of ${view.asOf}` : def.route}
              focused={index === focus}
              blocks={view.blocks}
              ink={tone(view.status)}
            />
          </box>
        );
      })}
    </box>
  );
}

function page(path: PortfolioPath, props: DeskProps) {
  return <PortfolioDesk path={path} api={props.api ?? API} reads={props.reads} />;
}

export function PortfolioPage(props: DeskProps) {
  return <PortfolioHome api={props.api ?? API} />;
}

/** `/portfolio/holdings` only. Later portfolio pages stay on the line read. */
function HoldingsHome({ api }: { api: string }) {
  const path = "/portfolio/holdings";
  const [reads, setReads] = useState<Record<string, Loaded>>({});
  const layout = layoutFor(path);
  const [focus, setFocus] = useFocusedPane(layout.length, path);

  useEffect(() => {
    const placements = layoutFor(path);
    const ac = new AbortController();
    let cancel = false;
    for (const placement of placements) {
      const def = BLOCKS[placement.id];
      if (!def) continue;
      void loadPortfolio(api, def.route, def.kind, ac.signal).then((result) => {
        if (cancel) return;
        setReads((prev) => ({ ...prev, [placement.id]: result }));
      });
    }
    return () => {
      cancel = true;
      ac.abort();
    };
  }, [api]);

  return (
    <box width="100%" height="100%" position="relative">
      {layout.map((placement, index) => {
        const def = BLOCKS[placement.id];
        if (!def) return null;
        const read = reads[placement.id];
        const view = paintHoldings(placement.id, read);
        return (
          <box
            key={placement.id}
            position="absolute"
            left={share(placement.x - 1, COLS)}
            top={share(placement.y - 1, ROWS)}
            width={share(placement.w, COLS)}
            height={share(placement.h, ROWS)}
            onMouseDown={() => setFocus(index)}
          >
            <PaneFrame
              title={def.title}
              status={view.asOf ? `as of ${view.asOf}` : def.route}
              focused={index === focus}
              blocks={view.blocks}
              ink={tone(view.status)}
            />
          </box>
        );
      })}
    </box>
  );
}

function paintHoldings(id: string, read: Loaded | undefined): { status: ReadResult["status"] | "loading"; blocks: PaneBody; asOf: string | null } {
  if (!read) return { status: "loading", blocks: shapeLines(["loading…"]), asOf: null };
  if (read.result.status === "stub" || read.result.lines.some((line) => STUB_MARKS.some((mark) => line.includes(mark)))) {
    return { status: "stub", blocks: shapeLines([STUB_READ]), asOf: null };
  }
  if (read.result.lines.length === 0 && read.result.status !== "ok") {
    return { status: read.result.status, blocks: shapeLines([EMPTY_READ]), asOf: null };
  }
  return { status: read.result.status, blocks: holdingsBody(id, read.data, read.result), asOf: read.result.asOf };
}

export function HoldingsPage(props: DeskProps) {
  return <HoldingsHome api={props.api ?? API} />;
}

/** `/portfolio/attribution` only. Later portfolio pages stay on the line read. */
function AttributionHome({ api }: { api: string }) {
  const path = "/portfolio/attribution";
  const [reads, setReads] = useState<Record<string, Loaded>>({});
  const layout = layoutFor(path);
  const [focus, setFocus] = useFocusedPane(layout.length, path);

  useEffect(() => {
    const placements = layoutFor(path);
    const ac = new AbortController();
    let cancel = false;
    for (const placement of placements) {
      const def = BLOCKS[placement.id];
      if (!def) continue;
      void loadPortfolio(api, def.route, def.kind, ac.signal).then((result) => {
        if (cancel) return;
        setReads((prev) => ({ ...prev, [placement.id]: result }));
      });
    }
    return () => {
      cancel = true;
      ac.abort();
    };
  }, [api]);

  return (
    <box width="100%" height="100%" position="relative">
      {layout.map((placement, index) => {
        const def = BLOCKS[placement.id];
        if (!def) return null;
        const read = reads[placement.id];
        const view = paintAttribution(placement.id, read);
        return (
          <box
            key={placement.id}
            position="absolute"
            left={share(placement.x - 1, COLS)}
            top={share(placement.y - 1, ROWS)}
            width={share(placement.w, COLS)}
            height={share(placement.h, ROWS)}
            onMouseDown={() => setFocus(index)}
          >
            <PaneFrame
              title={def.title}
              status={view.asOf ? `as of ${view.asOf}` : def.route}
              focused={index === focus}
              blocks={view.blocks}
              ink={tone(view.status)}
            />
          </box>
        );
      })}
    </box>
  );
}

function paintAttribution(id: string, read: Loaded | undefined): { status: ReadResult["status"] | "loading"; blocks: PaneBody; asOf: string | null } {
  if (!read) return { status: "loading", blocks: shapeLines(["loading…"]), asOf: null };
  if (read.result.status === "stub" || read.result.lines.some((line) => STUB_MARKS.some((mark) => line.includes(mark)))) {
    return { status: "stub", blocks: shapeLines([STUB_READ]), asOf: null };
  }
  if (read.result.lines.length === 0 && read.result.status !== "ok") {
    return { status: read.result.status, blocks: shapeLines([EMPTY_READ]), asOf: null };
  }
  return { status: read.result.status, blocks: attributionBody(id, read.data, read.result), asOf: read.result.asOf };
}

export function AttributionPage(props: DeskProps) {
  return <AttributionHome api={props.api ?? API} />;
}

/** `/portfolio/ledger` only. Later portfolio pages stay on the line read. */
function LedgerHome({ api }: { api: string }) {
  const path = "/portfolio/ledger";
  const [reads, setReads] = useState<Record<string, Loaded>>({});
  const layout = layoutFor(path);
  const [focus, setFocus] = useFocusedPane(layout.length, path);

  useEffect(() => {
    const placements = layoutFor(path);
    const ac = new AbortController();
    let cancel = false;
    for (const placement of placements) {
      const def = BLOCKS[placement.id];
      if (!def) continue;
      void loadPortfolio(api, def.route, def.kind, ac.signal).then((result) => {
        if (cancel) return;
        setReads((prev) => ({ ...prev, [placement.id]: result }));
      });
    }
    return () => {
      cancel = true;
      ac.abort();
    };
  }, [api]);

  return (
    <box width="100%" height="100%" position="relative">
      {layout.map((placement, index) => {
        const def = BLOCKS[placement.id];
        if (!def) return null;
        const read = reads[placement.id];
        const view = paintLedger(placement.id, read);
        return (
          <box
            key={placement.id}
            position="absolute"
            left={share(placement.x - 1, COLS)}
            top={share(placement.y - 1, ROWS)}
            width={share(placement.w, COLS)}
            height={share(placement.h, ROWS)}
            onMouseDown={() => setFocus(index)}
          >
            <PaneFrame
              title={def.title}
              status={view.asOf ? `as of ${view.asOf}` : def.route}
              focused={index === focus}
              blocks={view.blocks}
              ink={tone(view.status)}
            />
          </box>
        );
      })}
    </box>
  );
}

function paintLedger(id: string, read: Loaded | undefined): { status: ReadResult["status"] | "loading"; blocks: PaneBody; asOf: string | null } {
  if (!read) return { status: "loading", blocks: shapeLines(["loading…"]), asOf: null };
  if (read.result.status === "stub" || read.result.lines.some((line) => STUB_MARKS.some((mark) => line.includes(mark)))) {
    return { status: "stub", blocks: shapeLines([STUB_READ]), asOf: null };
  }
  if (read.result.lines.length === 0 && read.result.status !== "ok") {
    return { status: read.result.status, blocks: shapeLines([EMPTY_READ]), asOf: null };
  }
  return { status: read.result.status, blocks: ledgerBody(id, read.data, read.result), asOf: read.result.asOf };
}

export function LedgerPage(props: DeskProps) {
  return <LedgerHome api={props.api ?? API} />;
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
  if (path === "/portfolio") return <PortfolioHome api={props.api ?? API} />;
  if (path === "/portfolio/holdings") return <HoldingsHome api={props.api ?? API} />;
  if (path === "/portfolio/attribution") return <AttributionHome api={props.api ?? API} />;
  if (path === "/portfolio/ledger") return <LedgerHome api={props.api ?? API} />;
  if (!isPortfolioPath(path)) return null;
  return page(path, props);
}
