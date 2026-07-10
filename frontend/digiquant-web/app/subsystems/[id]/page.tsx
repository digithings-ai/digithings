import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Link from "next/link";
import { Footer, Emblem, Reveal, StackRow, subsystems, subsystemById } from "@digithings/web";
import { DQ_FOOTER, DQ_FOOTER_META } from "../../_nav";
import { SiteNav } from "@/components/landing/SiteNav";

// Poster grammar (canon §12): epithet ≤ 6 words, honest to function; fine
// print is a real repo path or a real function plus the livery. Posters wear
// the standard accent-<module> scope — and atlas · hermes · kairos are
// backend langgraphs, so their accents resolve to ink under [data-theme]
// (tokens.css ruling, 2026-07-08): the poster reads monochrome by design,
// and the digiquant phosphor on these pages is reserved for the terminal
// moments below it (cmdline, init codeblock, CTAs).
const POSTER: Record<string, { epithet: string; fine: string }> = {
  atlas: {
    epithet: "he carries the data.",
    fine: "digiquant/src/digiquant/olympus/atlas/ · accent-atlas → ink",
  },
  hermes: {
    epithet: "he carries the orders.",
    fine: "digiquant/src/digiquant/olympus/hermes/ · accent-hermes → ink",
  },
  kairos: {
    epithet: "he knows the moment.",
    fine: "executes on NautilusTrader · human-gated · accent-kairos → ink",
  },
};

export const dynamicParams = false;
export function generateStaticParams() {
  return subsystems.map((s) => ({ id: s.id }));
}
export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const s = subsystemById(id);
  return s ? { title: `${s.name} — digiquant`, description: s.tagline } : { title: "Subsystem — digiquant" };
}

export default async function SubsystemPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const s = subsystemById(id);
  if (!s) notFound();

  return (
    <>
      <SiteNav />
      <main className="section dq-subpage">
        <div className="wrap" style={{ maxWidth: 820 }}>
          <p style={{ fontFamily: "var(--font-mono)", fontSize: ".8rem", color: "var(--ink-mute)", marginBottom: "1.4rem" }}>
            <Link href="/#pipeline" style={{ color: "var(--ink-soft)" }}>pipeline</Link> / {s.id}
          </p>
          {/* Entrance on the page head only (#1450 polish, flagship grammar):
              breadcrumb and body stay static so content never gates on scroll;
              reduced-motion and no-JS render everything standing (site.css
              [data-motion] neutralization). */}
          <Reveal as="header">
            <div style={{ display: "flex", alignItems: "center", gap: "1rem", marginBottom: ".6rem" }}>
              <Emblem id={s.emblem} size={48} /><span className="dg-tier t-core">{s.step}</span>
            </div>
            {POSTER[s.id] ? (
              <div className={`sub-poster accent-${s.id}`}>
                <span className="sub-regmark" aria-hidden="true">+</span>
                <h1 className="sub-poster-name">{s.name}</h1>
                <p className="sub-poster-epithet">{POSTER[s.id].epithet}</p>
                <p className="sub-poster-fine">{POSTER[s.id].fine}</p>
              </div>
            ) : (
              <h1 className="hero-title" style={{ fontSize: "clamp(2.4rem,6vw,3.6rem)", margin: ".4rem 0 .5rem" }}>{s.name}</h1>
            )}
          </Reveal>
          <p style={{ fontSize: "1.15rem", color: "var(--ink-soft)", maxWidth: "48ch" }}>{s.tagline}</p>
          <p style={{ fontFamily: "var(--font-mono)", fontSize: ".82rem", color: "var(--ink-mute)", marginTop: ".5rem" }}>{s.role}</p>

          {s.dockerCmd && <div className="cmdline" style={{ marginTop: "1.6rem" }}><span className="prompt">$</span> {s.dockerCmd}</div>}

          <div style={{ marginTop: "2rem" }}>
            <Reveal as="p" className="mb-[0.6rem] font-mono text-[0.72rem] uppercase tracking-[0.1em] text-ink-mute">
              stack
            </Reveal>
            <StackRow items={s.stack} />
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "1rem", margin: "2.2rem 0", maxWidth: "62ch" }}>
            {s.summary.map((p, i) => <p key={i} style={{ color: "var(--ink-soft)", fontSize: "1.05rem" }}>{p}</p>)}
          </div>

          <Reveal as="p" className="mb-[0.5rem] font-mono text-[0.72rem] uppercase tracking-[0.1em] text-ink-mute">
            initialize
          </Reveal>
          <pre className="codeblock">{s.initSnippet.code}</pre>

          <div style={{ display: "flex", gap: ".75rem", flexWrap: "wrap", marginTop: "2rem" }}>
            <a className="btn btn-primary" href="/olympus/">Open Olympus <span aria-hidden="true">→</span></a>
            <a className="btn btn-ghost" href="https://github.com/digithings-ai" target="_blank" rel="noopener noreferrer">Source</a>
          </div>

          <div style={{ marginTop: "3rem", paddingTop: "1.8rem", borderTop: "1px solid var(--hair)" }}>
            <Reveal as="p" className="mb-[1rem] font-mono text-[0.72rem] uppercase tracking-[0.1em] text-ink-mute">
              related
            </Reveal>
            <div style={{ display: "flex", gap: ".6rem", flexWrap: "wrap" }}>
              {s.related.map((rid) => <a key={rid} className="stack-chip" href={`/subsystems/${rid}`}>{subsystemById(rid)?.name ?? rid}</a>)}
            </div>
          </div>
        </div>
      </main>
      <Footer links={DQ_FOOTER} meta={DQ_FOOTER_META} />
    </>
  );
}
