/**
 * Infinite marquee ticker — the scrolling "built on" strip common to the
 * reference sites, in our terminal register: two mono rows drifting in
 * opposite directions, edge-fade masks, seamless loop (content duplicated,
 * track translated exactly -50%), and pause-on-hover. Pure CSS, so a plain
 * server component. Third-party tool names keep their proper casing (the
 * naming rule reserves capitals for them); reduced motion stops the drift.
 */
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

function Track({ items, dir }: { items: string[]; dir: "a" | "b" }) {
  return (
    <div className="mq-row">
      <div className={`mq-track mq-track--${dir}`}>
        {[...items, ...items].map((t, i) => (
          <span className="mq-item" key={`${t}-${i}`} aria-hidden={i >= items.length || undefined}>
            <span className="mq-dot" aria-hidden="true" />
            {t}
          </span>
        ))}
      </div>
    </div>
  );
}

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

      <div className="mq">
        <Track items={ROW_A} dir="a" />
        <Track items={ROW_B} dir="b" />
      </div>
    </section>
  );
}
