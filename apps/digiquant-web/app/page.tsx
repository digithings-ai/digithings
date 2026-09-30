import Link from "next/link";
import {
  ContactMailto,
  CopyCommand,
  DocumentFrame,
  Figure,
  GlyphList,
  GlyphRow,
  NumberedStages,
  PageTitle,
  Section,
  fmtNum,
  fmtPct,
  subsystems,
  toneClass,
} from "@digithings/ui";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableRowHeader,
  buttonVariants,
} from "@digithings/ui/ui";
import { PortfolioIsland } from "@/components/live/portfolio-island";
import { StrategyLibraryLive } from "@/components/tearsheet/strategy-library-live";
import transcript from "./_mcp-transcript.json";
import { PRICING_FAQ, PRICING_TIERS } from "./_pricing";

// Every line below is copied from shipped source (see
// docs/superpowers/specs/2026-09-30-digiquant-web-rebuild-inventory.md): the
// pipeline from the research walkthrough, the phase ranges from the real phase
// folders, the tiers from the approved open-core pricing copy. No projections.

const REPO = "https://github.com/digithings-ai/digithings.git";

const STAGES: { n: string; title: string; body: string; tool: string }[] = [
  { n: "01", title: "Research", body: "Ask in plain language. An LLM research loop pulls free macro and market data and proposes directions to test.", tool: "chat · LLM" },
  { n: "02", title: "Indicators", body: "Compose validated indicators — moving averages, RSI, ADF, DPSD — from the shared, unit-tested library.", tool: "indicators lib" },
  { n: "03", title: "Strategy", body: "Wire indicators into a rules-based strategy with explicit entries, exits, sizing, and risk.", tool: "strategy spec" },
  { n: "04", title: "Signals", body: "Generate entry and exit signals across historical bars — deterministic and reproducible.", tool: "signal gen" },
  { n: "05", title: "Optimize", body: "Search the parameter space with Optuna against your own objective. Results are in-sample — the tearsheets say so too.", tool: "Optuna" },
  { n: "06", title: "Backtest", body: "Replay on a NautilusTrader core with Pine-faithful indicators — RSI on Wilder's smoothing, Bollinger on population sigma — a full trade ledger, and a tearsheet.", tool: "NautilusTrader" },
  { n: "07", title: "Export", body: "Export the strategy to TradingView as Pine v5. Live trading is not on yet — paper and live venues wait on a human gate.", tool: "execution · planned" },
];

// Real phase folders: research/phases/* and portfolio/phases/*. The h7 → h7e → h9
// sequence has no h8 because that number was never assigned a phase.
const PHASES: Record<string, string> = {
  research: "00–09 · preflight → triage → alt-data → institutional → macro → asset class → equities → consolidate → synthesis → publish",
  portfolio: "h1–h9 · thesis review → market thesis → vehicle map → screener → asset analyst → deliberation → PM direction → risk sizing → commit run",
  execution: "backtest and optimize on NautilusTrader · paper adapters ship · live venues refused",
};

// Read-scope tools of the digiquant MCP server (digiquant/src/digiquant/mcp_server.py,
// READ_SCOPE_TOOLS); the one-liners are that file's own docstrings.
const MCP_TOOLS: { name: string; what: string }[] = [
  { name: "digiquant_list_strategies", what: "List registered strategies — name, aliases, description, default params." },
  { name: "digiquant_get_price_technicals", what: "Technicals for a ticker from the versioned R2 price history." },
  { name: "digiquant_get_macro_series", what: "Macro observations for one or more series ids." },
  { name: "digiquant_get_trade_levels", what: "Causal ATR / swing-pivot / Donchian trade levels for one direction." },
  { name: "digiquant_query_research", what: "Query the research book: documents, snapshots, positions, NAV history, portfolio metrics." },
  { name: "digifetch_quote / digifetch_quotes_batch", what: "Latest quote for one listing, or 1–20 at once." },
  { name: "digifetch_price_history", what: "OHLCV bars for one listing." },
];
const MCP_RUN = "python -m digiquant.mcp_server --stdio --scope read";

// scripts/capture_mcp_transcript.py writes app/_mcp-transcript.json from a real
// local run; nothing in it is hand-written. Cells are formatted per column.
type TranscriptCall = (typeof transcript.calls)[number];
type TranscriptRow = Record<string, string | number | null>;

function transcriptCell(col: string, row: TranscriptRow) {
  const v = row[col];
  if (typeof v !== "number") return v ?? "n/a";
  if (col === "change_percent") return <span className={toneClass(v)}>{fmtPct(v)}</span>;
  if (col === "volume") return fmtNum(v);
  return fmtNum(v, 2);
}

function TranscriptCallTable({ call }: { call: TranscriptCall }) {
  const rows = call.rows as TranscriptRow[];
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-[0.6rem]">
      <p className="m-0 break-words text-ink-soft">
        <span className="text-ink-mute">tools/call</span> {call.tool} {JSON.stringify(call.args)}
      </p>
      <Table density="compact">
        <TableHeader>
          <TableRow>
            {call.columns.map((c) => (
              <TableHead key={c} numeric={typeof rows[0]?.[c] === "number"}>
                {c}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row, i) => (
            <TableRow key={i}>
              {call.columns.map((c, j) =>
                j === 0 ? (
                  <TableRowHeader key={c}>{transcriptCell(c, row)}</TableRowHeader>
                ) : (
                  <TableCell key={c} numeric={typeof row[c] === "number"}>
                    {transcriptCell(c, row)}
                  </TableCell>
                ),
              )}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

// Gloomberg density: tighter block step than the kit default (--page-step).
const DENSE = "py-[1.75rem]";
const LINK = "text-ink underline-offset-[3px] hover:underline";

export default function Home() {
  return (
    <main id="main" tabIndex={-1}>
      <DocumentFrame>
        <Section className={DENSE}>
          <PageTitle title="A quant research desk in a glass box you own">
            The research stack an institutional desk would build — research runs daily and
            portfolio sizes the risk, through backtest to a tearsheet. Open-source and
            self-hosted, so work that once needed a team runs for one.
          </PageTitle>
          <div className="mt-[1.6rem] grid grid-cols-[minmax(0,1fr)] gap-[1.2rem]">
            <CopyCommand
              ariaLabel="Clone the repository"
              samples={[{ label: "git", code: `git clone ${REPO}`, protocol: "git clone" }]}
            />
            <div className="flex flex-wrap gap-[0.6rem]">
              <a className={buttonVariants({ variant: "default" })} href="/dashboard/">
                Open dashboard <span aria-hidden="true">→</span>
              </a>
              <a
                className={buttonVariants({ variant: "ghost" })}
                href="https://github.com/digithings-ai"
                target="_blank"
                rel="noopener noreferrer"
              >
                Source
              </a>
            </div>
          </div>
        </Section>

        <Section
          className={DENSE}
          id="numbers"
          title="The desk, in three numbers."
          lede="No projections — every figure is a property of the shipped stack. Live stays zero because nothing is sent to a venue yet."
        >
          <Figure n={1} caption="Properties of the shipped stack: subsystems, pipeline stages, live orders.">
            <Table density="compact">
              <TableBody>
                <TableRow>
                  <TableRowHeader>subsystems</TableRowHeader>
                  <TableCell numeric>{subsystems.length}</TableCell>
                </TableRow>
                <TableRow>
                  <TableRowHeader>pipeline stages</TableRowHeader>
                  <TableCell numeric>{STAGES.length}</TableCell>
                </TableRow>
                <TableRow>
                  <TableRowHeader>live orders</TableRowHeader>
                  <TableCell numeric>0</TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </Figure>
        </Section>

        <Section className={DENSE} id="pipeline" title="Pipeline" lede="Research to tearsheet in seven stages. Results are in-sample, and the tearsheets say so.">
          <NumberedStages
            stages={STAGES.map((s) => ({ num: s.n, title: s.title, mech: s.body, tag: s.tool }))}
          />
        </Section>

        <Section
          className={DENSE}
          id="book"
          title="The research book, live"
          lede="Read from the same public seam the dashboard uses. It is a research/paper portfolio — nothing here is a live-traded fund."
        >
          <PortfolioIsland />
        </Section>

        <Section
          className={DENSE}
          id="dashboard"
          title="The dashboard"
          lede="A walkthrough of the dashboard goes here once its rebuild is final."
        >
          {/* Slot for the dashboard recording: swap the inner div for a media
              part once the video exists (kit promotion + reference specimen). */}
          <Figure n={2} caption="Dashboard walkthrough — recording to come.">
            <div
              role="img"
              aria-label="Placeholder for the dashboard walkthrough video"
              className="grid aspect-video w-full place-items-center border border-hair text-ink-mute"
            >
              Video placeholder · 16:9
            </div>
          </Figure>
        </Section>

        <Section
          className={DENSE}
          id="desk"
          title="Desk"
          lede="Three subsystems, research → portfolio → execution. Phase ids are the real folder names — h8 was never assigned."
        >
          <Table density="compact">
            <TableHeader>
              <TableRow>
                <TableHead>Subsystem</TableHead>
                <TableHead>Phases</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {subsystems.map((s) => (
                <TableRow key={s.id}>
                  <TableRowHeader className="whitespace-normal">
                    <a className={LINK} href={`/subsystems/${s.id}/`}>
                      {s.name}
                    </a>
                    <span className="block font-normal text-ink-mute">{s.tagline}</span>
                  </TableRowHeader>
                  <TableCell className="whitespace-normal text-ink-soft">{PHASES[s.id]}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Section>

        <Section
          className={DENSE}
          id="strategies"
          title="Strategies"
          lede="Backtest tearsheets — equity, drawdown, trade log, and risk metrics. Each run is a Nautilus backtest on Coinbase daily OHLCV."
        >
          <StrategyLibraryLive />
          <p className="mt-[1rem] mb-0 text-[length:var(--type-body)] text-ink-soft">
            <Link className={LINK} href="/strategies/">
              Full strategy library →
            </Link>
          </p>
        </Section>

        <Section
          className={DENSE}
          id="mcp"
          title="Drive it from your agent"
          lede="The desk is also an MCP server. Point any MCP client at it and the same research, book and market reads are tools — read scope is the default hosted surface."
        >
          <div className="grid grid-cols-[minmax(0,1fr)] gap-[1.2rem]">
            <CopyCommand
              ariaLabel="Run the digiquant MCP server"
              samples={[{ label: "stdio", code: MCP_RUN, protocol: "mcp" }]}
            />
            <Table density="compact">
              <TableHeader>
                <TableRow>
                  <TableHead>Tool</TableHead>
                  <TableHead>What it returns</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {MCP_TOOLS.map((t) => (
                  <TableRow key={t.name}>
                    <TableRowHeader className="whitespace-normal">{t.name}</TableRowHeader>
                    <TableCell className="whitespace-normal text-ink-soft">{t.what}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <Figure
              n={3}
              caption={`Recorded session, ${transcript.capturedAt.slice(0, 10)} — real calls to a local run of \`${transcript.command}\` (${transcript.server.name}, ${transcript.toolCount} tools listed). Fields trimmed to a few per row. ${transcript.calls[0].envelope.attribution}; ${transcript.calls[0].envelope.delay_notice?.toLowerCase()}. A recording, not a live feed.`}
            >
              <div className="grid grid-cols-[minmax(0,1fr)] gap-[1.4rem]">
                {transcript.calls.map((call) => (
                  <TranscriptCallTable key={call.tool} call={call} />
                ))}
              </div>
            </Figure>
          </div>
        </Section>

        <Section
          className={DENSE}
          id="pricing"
          title="Pricing"
          lede="digiquant is open core. Self-host the whole stack at no cost, join the waitlist for managed hosting, or talk to us about enterprise — the same engine either way."
        >
          <Table density="compact">
            <TableHeader>
              <TableRow>
                <TableHead>Tier</TableHead>
                <TableHead>Price</TableHead>
                <TableHead>Includes</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {PRICING_TIERS.map((t) => (
                <TableRow key={t.id}>
                  <TableRowHeader>{t.name}</TableRowHeader>
                  <TableCell className="text-ink-soft">
                    {t.price}
                    {t.cadence ? ` ${t.cadence}` : ""}
                  </TableCell>
                  <TableCell className="whitespace-normal text-ink-soft">
                    {t.desc} {t.features.join(" · ")}.
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <div className="mt-[1.2rem] flex flex-wrap gap-[0.6rem]">
            <a
              className={buttonVariants({ variant: "ghost" })}
              href="https://github.com/digithings-ai/digithings"
              target="_blank"
              rel="noopener noreferrer"
            >
              Self-host on GitHub
            </a>
            {PRICING_TIERS.map((t) =>
              t.cta ? (
                <ContactMailto
                  key={t.id}
                  className={buttonVariants({ variant: "ghost" })}
                  email={t.cta.email}
                  subject={t.cta.subject}
                >
                  {t.cta.label} <span aria-hidden="true">→</span>
                </ContactMailto>
              ) : null,
            )}
          </div>
        </Section>

        <Section className={DENSE} title="Questions">
          <GlyphList>
            {PRICING_FAQ.map((item) => (
              <GlyphRow key={item.q} label={item.q}>
                {item.a}
              </GlyphRow>
            ))}
          </GlyphList>
        </Section>
      </DocumentFrame>
    </main>
  );
}
