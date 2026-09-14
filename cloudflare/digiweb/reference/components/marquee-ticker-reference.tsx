/**
 * Infinite marquee ticker — the scrolling "built on" strip common to the
 * reference sites, in our terminal register: two mono rows drifting in
 * opposite directions, edge-fade masks, seamless loop and pause-on-hover.
 * Consumes the shared <Marquee/> primitive from @digithings/web (promoted
 * #1450); this specimen is a thin wrapper — two Marquees, opposite directions —
 * that keeps the catalog rendering it. Third-party tool names keep their proper
 * casing (the naming rule reserves capitals for them); reduced motion stops the
 * drift.
 */
import { Marquee } from "@digithings/web";

const ROW_A = [
  "Polars",
  "NautilusTrader",
  "LangGraph",
  "LiteLLM",
  "Optuna",
  "Pydantic",
  "FastAPI",
];

const ROW_B = [
  "Supabase",
  "Chroma",
  "Next.js",
  "Motion",
  "Tailwind",
  "Drizzle",
  "Cloudflare",
];

export function MarqueeTickerReference() {
  return (
    <section className="section-block">
      <p className="kicker">{"// marquee"}</p>
      <h2 className="title">A strip that never stops.</h2>
      <p className="section-copy">
        The reference sites&apos; scrolling &quot;built on&quot; strip, in a terminal register: two
        mono rows drift in opposite directions behind edge-fade masks, looping seamlessly. Hover to
        pause and read; reduced motion stops the drift entirely.
      </p>

      <div className="mt-[1.4rem] flex flex-col gap-[0.85rem]">
        <Marquee items={ROW_A} direction="left" aria-label="Built on — data and quant tools" />
        <Marquee items={ROW_B} direction="right" aria-label="Built on — web and infra tools" />
      </div>
    </section>
  );
}
