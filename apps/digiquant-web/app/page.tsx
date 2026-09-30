import Link from "next/link";
import {
  ContactMailto,
  CopyCommand,
  DocumentFrame,
  Figure,
  GlyphList,
  GlyphRow,
  PageTitle,
  Section,
  subsystems,
} from "@digithings/ui";
import {
  Badge,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableRowHeader,
  buttonVariants,
} from "@digithings/ui/ui";
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

const PUBLISHED: { id: string; name: string; symbol: string }[] = [
  { id: "btc_slapper", name: "BTC L/S", symbol: "BTC-USD" },
  { id: "eth_slapper", name: "ETH L/S", symbol: "ETH-USD" },
  { id: "sol_slapper", name: "SOL L/S", symbol: "SOL-USD" },
  { id: "btc_sdca", name: "BTC-SDCA", symbol: "BTC-USD" },
];

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
          <Table density="compact">
            <TableHeader>
              <TableRow>
                <TableHead>#</TableHead>
                <TableHead>Stage</TableHead>
                <TableHead>What it does</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {STAGES.map((s) => (
                <TableRow key={s.n}>
                  <TableCell className="text-ink-mute">{s.n}</TableCell>
                  <TableRowHeader>
                    {s.title}
                    <span className="block font-normal text-ink-mute">{s.tool}</span>
                  </TableRowHeader>
                  <TableCell className="whitespace-normal text-ink-soft">{s.body}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
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
          <Table density="compact">
            <TableHeader>
              <TableRow>
                <TableHead>Strategy</TableHead>
                <TableHead>Symbol</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {PUBLISHED.map((s) => (
                <TableRow key={s.id}>
                  <TableRowHeader>
                    <a className={LINK} href={`/strategies/${s.id}/`}>
                      {s.name}
                    </a>
                  </TableRowHeader>
                  <TableCell className="text-ink-soft">{s.symbol}</TableCell>
                  <TableCell>
                    <Badge variant="neutral">Backtest only</Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <p className="mt-[1rem] mb-0 text-[length:var(--type-body)] text-ink-soft">
            <Link className={LINK} href="/strategies/">
              Full strategy library →
            </Link>
          </p>
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
