import type { Metadata } from "next";
import { Footer, ModuleCard, Reveal, modules } from "@digithings/web";
import { DT_FOOTER, DT_FOOTER_META } from "../_nav";
import { DigiNav } from "@/components/landing/DigiNav";
import { AmbientMesh } from "@/components/landing/AmbientMesh";
import ArchGraph from "./ArchGraph";

export const metadata: Metadata = {
  title: "Architecture — digithings",
  description: "How the DigiThings platform fits together — a supervisor routing requests across composable services.",
};

const core = modules.filter((m) => m.tier === "core");
const support = modules.filter((m) => m.tier !== "core");

export default function ArchitecturePage() {
  return (
    <>
      <DigiNav />
      <main className="dq-subpage">
        <AmbientMesh />
        <section className="section">
          <div className="wrap">
            <Reveal className="section-head">
              <span className="kicker">// architecture</span>
              <h2 style={{ fontFamily: "var(--font-display)", fontWeight: 400, fontSize: "clamp(2.4rem,5vw,3.6rem)" }}>How the platform fits together.</h2>
              <p>A LangGraph supervisor inspects every request and routes it to the right specialist — then writes the whole run to an immutable audit trail. Hover or focus a node to trace its links; click through for the module reference.</p>
            </Reveal>
            <Reveal><ArchGraph /></Reveal>
          </div>
        </section>

        <section className="section section-alt">
          <div className="wrap">
            <Reveal className="section-head"><span className="kicker">// request lifecycle</span><h2>Request in, audited run out.</h2></Reveal>
            <div className="principles">
              <Reveal className="principle"><span className="principle-num">01</span><h3>Route</h3><p>DigiGraph selects the specialist sub-graph via a declarative tool registry, behind an OpenAI-compatible front door.</p></Reveal>
              <Reveal className="principle"><span className="principle-num">02</span><h3>Execute</h3><p>The specialist runs — quant, retrieval, or chat — with LiteLLM routing/caching and checkpoints that survive a restart.</p></Reveal>
              <Reveal className="principle"><span className="principle-num">03</span><h3>Audit</h3><p>Every span carries a correlation ID; PII is redacted before logs hit disk; the run lands in an immutable JSONL trail.</p></Reveal>
            </div>
          </div>
        </section>

        <section className="section">
          <div className="wrap">
            <Reveal className="section-head"><span className="kicker">// core verticals</span><h2>Four verticals.</h2></Reveal>
            <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))", marginBottom: "3rem" }}>
              {core.map((m) => <Reveal key={m.id}><ModuleCard m={m} /></Reveal>)}
            </div>
            <Reveal className="section-head"><span className="kicker">// support + roadmap</span><h2>Support modules.</h2></Reveal>
            <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))" }}>
              {support.map((m) => <Reveal key={m.id}><ModuleCard m={m} /></Reveal>)}
            </div>
          </div>
        </section>
      </main>
      <Footer links={DT_FOOTER} meta={DT_FOOTER_META} />
    </>
  );
}
