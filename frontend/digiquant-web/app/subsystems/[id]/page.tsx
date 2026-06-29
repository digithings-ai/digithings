import type { Metadata } from "next";
import { notFound } from "next/navigation";
import Link from "next/link";
import { Footer, Emblem, StackRow, subsystems, subsystemById } from "@digithings/web";
import { DQ_FOOTER, DQ_FOOTER_META } from "../../_nav";
import { DqNav } from "@/components/landing/DqNav";

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
      <DqNav />
      <main className="section dq-subpage">
        <div className="wrap" style={{ maxWidth: 820 }}>
          <p style={{ fontFamily: "var(--font-mono)", fontSize: ".8rem", color: "var(--ink-mute)", marginBottom: "1.4rem" }}>
            <Link href="/#pipeline" style={{ color: "var(--ink-soft)" }}>pipeline</Link> / {s.id}
          </p>
          <div style={{ display: "flex", alignItems: "center", gap: "1rem", marginBottom: ".6rem" }}>
            <Emblem id={s.emblem} size={48} /><span className="dg-tier t-core">{s.step}</span>
          </div>
          <h1 className="hero-title" style={{ fontSize: "clamp(2.4rem,6vw,3.6rem)", margin: ".4rem 0 .5rem" }}>{s.name}</h1>
          <p style={{ fontSize: "1.15rem", color: "var(--ink-soft)", maxWidth: "48ch" }}>{s.tagline}</p>
          <p style={{ fontFamily: "var(--font-mono)", fontSize: ".82rem", color: "var(--ink-mute)", marginTop: ".5rem" }}>{s.role}</p>

          {s.dockerCmd && <div className="cmdline" style={{ marginTop: "1.6rem" }}><span className="prompt">$</span> {s.dockerCmd}</div>}

          <div style={{ marginTop: "2rem" }}>
            <p style={{ fontFamily: "var(--font-mono)", fontSize: ".72rem", letterSpacing: ".1em", textTransform: "uppercase", color: "var(--ink-mute)", marginBottom: ".6rem" }}>stack</p>
            <StackRow items={s.stack} />
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "1rem", margin: "2.2rem 0", maxWidth: "62ch" }}>
            {s.summary.map((p, i) => <p key={i} style={{ color: "var(--ink-soft)", fontSize: "1.05rem" }}>{p}</p>)}
          </div>

          <p style={{ fontFamily: "var(--font-mono)", fontSize: ".72rem", letterSpacing: ".1em", textTransform: "uppercase", color: "var(--ink-mute)", marginBottom: ".5rem" }}>initialize</p>
          <pre className="codeblock">{s.initSnippet.code}</pre>

          <div style={{ display: "flex", gap: ".75rem", flexWrap: "wrap", marginTop: "2rem" }}>
            <a className="btn btn-primary" href="/olympus/">Open Olympus <span aria-hidden="true">→</span></a>
            <a className="btn btn-ghost" href="https://github.com/digithings-ai" target="_blank" rel="noopener noreferrer">Source</a>
          </div>

          <div style={{ marginTop: "3rem", paddingTop: "1.8rem", borderTop: "1px solid var(--hair)" }}>
            <p style={{ fontFamily: "var(--font-mono)", fontSize: ".72rem", letterSpacing: ".1em", textTransform: "uppercase", color: "var(--ink-mute)", marginBottom: "1rem" }}>related</p>
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
