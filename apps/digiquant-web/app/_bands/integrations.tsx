import { CtaLink, Marquee } from "@digithings/ui";
import { IntegrationMark, integrationHref, RowMark, type IntegrationId, type RowProviderId } from "@/components/integrations/marks";
import { ModuleBanner } from "@/components/integrations/module-banner";
import { BANNERS } from "../../../../packages/hero-banner/src/definitions";
import { PixelWordmark } from "../../../digithings-web/components/landing/PixelWordmark";
import { Band } from "../_chrome/Band";
import { MCP_TOOLS } from "../_mcp";
import PROVIDERS from "./integrations.providers.json";

const toolCount = (prefix: string) => MCP_TOOLS.filter((t) => t.name.startsWith(prefix)).length;

const CARD =
  "flex h-auto min-h-full w-full min-w-0 shrink flex-col items-stretch gap-2.5 overflow-hidden bg-surface p-[1.15rem] text-start font-sans text-[length:inherit] font-normal whitespace-normal no-underline hover:bg-surface-2";

const DRIVERS: { id: IntegrationId; name: string; role: string; line: string; fact: string }[] = [
  {
    id: "gloomberb",
    name: "Gloomberg",
    role: "market data",
    line: "Quotes, filings, macro and options for the research stages. Enrichment, never the record the backtests run on.",
    fact: `${toolCount("gloomberb_")} MCP tools`,
  },
  {
    id: "luxalgo",
    name: "LuxAlgo",
    role: "Vela backbone · live signals",
    line: "The live chart is the hero.",
    fact: `${toolCount("luxalgo_")} MCP tools · live on hero`,
  },
  {
    id: "nautilus",
    name: "NautilusTrader",
    role: "engine",
    line: "The event-driven engine every backtest and optimize run goes through. One engine, no second code path.",
    fact: "validate → backtest → optimize → export",
  },
];

type Module = { name: string; line: string };

/** Modules digiquant actually calls. Every module shows its own hero banner,
 *  small; a name without one falls back to plain text. */
const MODULES: Module[] = [
  { name: "digigraph", line: "Orchestrates the research and portfolio runs." },
  { name: "digichat", line: "The chat where a strategy idea starts." },
  { name: "digillm", line: "Routes and caches the model calls research and the dashboard make." },
  { name: "digikey", line: "Checks the API token on digiquant requests." },
  { name: "digibase", line: "Shared errors, request handling, and metrics on the API." },
  { name: "digifetch", line: "Market-data tools the research stages call through Gloomberg." },
];

/** The rest of the platform. digiquant does not call these; they sit beside it. */
const PLATFORM: Module[] = [
  { name: "digisearch", line: "RAG ingest, query, and research." },
  { name: "digitrace", line: "Observability, health, and status for every service." },
  { name: "digivault", line: "A Markdown vault with wikilinks and lint." },
  { name: "digiclaw", line: "Heartbeat runner and an append-only audit log." },
  { name: "digivoice", line: "Local dictation and speech, on the machine." },
  { name: "digidev", line: "An agentic coding workflow kit for any codebase." },
  { name: "digibook", line: "The book: architecture, design decisions, and the reasons." },
];

function ModuleGrid({ label, modules }: { label: string; modules: Module[] }) {
  return (
    <div className="flex w-full min-w-0 flex-col gap-4">
      <h3 className="m-0 font-mono text-[0.75rem] font-normal tracking-[0.08em] text-ink-soft uppercase">{label}</h3>
      <ul aria-label={label} className="m-0 grid w-full list-none gap-x-8 gap-y-5 p-0 sm:grid-cols-2 lg:grid-cols-3">
        {modules.map((mod) => (
          <li key={mod.name} className="min-w-0">
            {mod.name in BANNERS ? (
              <ModuleBanner name={mod.name} className="block h-full !w-auto" />
            ) : (
              <span className="block font-mono text-[0.95rem] text-ink">{mod.name}</span>
            )}
            <span className="mt-1.5 block text-[0.875rem] leading-[1.5] text-ink-soft">{mod.line}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The connected-package rows. Each entry carries its provider's official mark;
 *  the label is the copy the band shipped with, unchanged. */
type RowEntry = { id: RowProviderId; label: string };

/** The rows themselves are generated, not written here: a provider appears only
 *  when a manifest in this repo declares one of its packages AND a non-test
 *  source file imports it. That is what keeps a dead provider out of the band —
 *  FRED, for instance, is still declared by the sealed `m2` parquet fixture but
 *  nothing imports it, so it no longer scrolls past.
 *
 *  Rebuild with `python3 scripts/build_providers_band.py`; CI refuses the band
 *  when the committed JSON has drifted from the tree. Editing this list by hand
 *  is exactly the staleness the generator exists to end. */
const PACKAGES: RowEntry[] = (PROVIDERS.providers as { id: RowProviderId; label: string }[]).map(
  ({ id, label }) => ({ id, label }),
);

/** Two rows, split by position so the list length is what decides it rather than
 *  a second hardcoded array to keep in step: even entries scroll left, odd scroll
 *  right. A single-entry provider set still fills both rows. */
const PACKAGES_A = PACKAGES.filter((_, i) => i % 2 === 0);
const PACKAGES_B = PACKAGES.filter((_, i) => i % 2 === 1);

/** One row lozenge. Marquee's `items` prop resolves its icon from a slug it looks
 *  up itself, so it cannot mix registry marks with providers that have none; the
 *  rows pass their own chips as `children` instead and keep Marquee's Chip dress
 *  verbatim. If those class names ever change in marquee/Marquee.tsx, change them
 *  here in the same commit or the two rows drift out of step with every other
 *  Marquee consumer. The group gap (2.2rem) and the wrap geometry stay in
 *  marquee.css — .mq-group lays these spans out as flex items either way. */
function RowItem({ entry }: { entry: RowEntry }) {
  return (
    <span className="inline-flex items-center gap-[0.55rem] font-mono text-[0.82rem] whitespace-nowrap text-ink-soft">
      <RowMark id={entry.id} />
      {entry.label}
    </span>
  );
}


/** Integrations. digithings is the platform under the agents and the chat.
 *  Gloomberg, LuxAlgo Vela, and NautilusTrader are the three drivers.
 *  The scrolling rows name the other packages this tree actually calls. */
export function IntegrationsBand() {
  return (
    <Band
      id="integrations"
      title="What the engine is built on"
      takeaway="digithings runs the agents, the chat, and the model calls. Gloomberg supplies the data, LuxAlgo Vela the live chart, and NautilusTrader the engine."
    >
      <div className="flex min-w-0 flex-col gap-8">
        <div className="integrations-hero flex min-w-0 flex-col items-center gap-8 border border-hair px-4 py-8 sm:px-8 sm:py-10">
          <CtaLink
            href={integrationHref("digithings")}
            external
            variant="ghost"
            className="h-auto w-fit max-w-full shrink justify-center overflow-visible p-0 hover:bg-transparent"
          >
            <PixelWordmark />
          </CtaLink>
          <p className="m-0 max-w-[36rem] text-center text-[1.05rem] leading-[1.55] text-ink-soft">
            The platform that drives the agentic side of digiquant.
          </p>
          <ModuleGrid label="digiquant calls" modules={MODULES} />
          <ModuleGrid label="the rest of digithings" modules={PLATFORM} />
        </div>

        <ul aria-label="Architectural drivers" className="m-0 grid min-w-0 list-none gap-px overflow-x-clip border border-hair bg-hair p-px md:grid-cols-3">
          {DRIVERS.map((d) => (
            <li key={d.id} className="min-w-0">
              <CtaLink href={integrationHref(d.id)} external variant="ghost" className={CARD}>
                <span className="flex items-center gap-3 text-ink">
                  <IntegrationMark id={d.id} size={d.id === "nautilus" ? 36 : 32} />
                  <span className="min-w-0">
                    <span className="block font-display text-[1.25rem] font-medium leading-tight tracking-[-0.02em] text-ink">{d.name}</span>
                    <span className="block font-mono text-[0.68rem] font-normal text-ink-mute">{d.role}</span>
                  </span>
                </span>
                <span className="text-[0.8125rem] font-normal leading-[1.55] text-ink-soft">{d.line}</span>
                <span className="mt-auto border-t border-hair pt-2 font-mono text-[0.68rem] font-normal text-ink-mute">{d.fact}</span>
              </CtaLink>
            </li>
          ))}
        </ul>

        <div className="flex min-w-0 flex-col gap-3" aria-label="Connected packages">
          <Marquee direction="left" speed={42}>
            {PACKAGES_A.map((entry) => (
              <RowItem key={entry.id} entry={entry} />
            ))}
          </Marquee>
          <Marquee direction="right" speed={50}>
            {PACKAGES_B.map((entry) => (
              <RowItem key={entry.id} entry={entry} />
            ))}
          </Marquee>
        </div>
      </div>
    </Band>
  );
}
