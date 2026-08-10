import { TerminalManifest, type TerminalManifestRow } from "@digithings/web";

/**
 * Terminal manifest — a `digithings ps` process pane: selectable module rows
 * (status dot, two-tone mono name, port, role) beside an output panel that
 * types the selected row's summary at a blinking cursor. Column collapse is
 * container-driven — the pane adapts to its own width, not the viewport — and
 * the wide layout scrolls long output inside a fixed-height card. Consumes the
 * shared <TerminalManifest> primitive; the rows here are illustrative example
 * data, not the live module registry.
 */
const ROWS: TerminalManifestRow[] = [
  {
    id: "digigraph",
    name: "digigraph",
    port: 8000,
    status: "online",
    blurb: "supervisor · routes every request",
    detail:
      "the LangGraph supervisor — one entrypoint, every capability.\n\nRoutes each request to the right sub-graph and streams the\nanswer back over one socket.\n\nstack   LangGraph  ·  LiteLLM  ·  FastAPI",
  },
  {
    id: "digiquant",
    name: "digiquant",
    port: 8001,
    status: "online",
    blurb: "quant engine · backtest to live",
    detail:
      "the quant engine — backtest, optimize, and paper-trade on one\nrail.\n\nAtlas watches the portfolio; Hermes narrates the market.\n\nstack   NautilusTrader  ·  Polars",
  },
  {
    id: "digisearch",
    name: "digisearch",
    port: 8002,
    status: "online",
    blurb: "RAG · corpus in, citations out",
    detail:
      "retrieval over your corpus — chunked, embedded, reranked.\n\nEvery answer carries its sources.\n\nstack   Qdrant  ·  FastEmbed",
  },
  {
    id: "digikey",
    name: "digikey",
    port: 8005,
    status: "online",
    blurb: "auth · JWT + scoped API keys",
    detail:
      "the keymaster — short-lived JWTs, scoped API keys, and nothing\nshared that should not be.\n\nstack   PyJWT  ·  FastAPI",
  },
  {
    id: "digismith",
    name: "digismith",
    port: 8003,
    status: "online",
    blurb: "tracing · every hop on record",
    detail:
      "the forge's ledger — traces, spans, and token spend for every\nagent hop.\n\nstack   OpenTelemetry  ·  FastAPI",
  },
  {
    id: "digiclaw",
    name: "digiclaw",
    status: "roadmap",
    blurb: "heartbeat + audit",
    detail: "heartbeat and audit trail for the whole stack — on the roadmap.",
  },
  {
    id: "digivault",
    name: "digivault",
    port: 8004,
    status: "roadmap",
    blurb: "markdown vault management",
    detail: "Obsidian-style vault management as a service — on the roadmap.",
  },
];

export function TerminalManifestReference() {
  const online = ROWS.filter((row) => row.status === "online").length;
  const road = ROWS.length - online;

  return (
    <section className="section-block" id="terminal-manifest">
      <div className="section-head">
        <p className="kicker">{"// terminal manifest"}</p>
        <h2 className="title">A process list that answers back.</h2>
      </div>
      <p className="section-copy">
        The digithings-web landing grammar: <code>digithings ps</code> as product tour. Rows appear
        with a stagger; picking one types its summary out at the cursor. Wide panes split into
        list + output with internal scroll, narrow panes drop the port and role columns — by
        container width, not viewport. The footer slot carries the hand-off action.
      </p>

      <div className="mt-[1.2rem] max-w-[980px]">
        <p className="mb-[0.6rem] inline-block rounded-full border border-hair px-[0.5rem] py-[0.16rem] font-mono text-[0.6rem] uppercase tracking-[0.08em] text-ink-mute">
          Example data · not live
        </p>
        <TerminalManifest
          command="digithings ps"
          meta={`· ${online} online · ${road} on the roadmap`}
          rows={ROWS}
          namePrefix="digi"
          hint="select a module"
          aria-label="digithings module manifest (example data)"
          footer={
            <button
              type="button"
              className="mt-auto cursor-pointer self-end rounded-[7px] border border-hair bg-transparent px-[0.6rem] py-[0.3rem] font-mono text-[0.78rem] text-ink-soft transition-colors hover:bg-accent-weak hover:text-ink"
            >
              ask <span className="text-ink">digi</span>
              <span className="text-accent">chat</span> →
            </button>
          }
        />
      </div>
    </section>
  );
}
