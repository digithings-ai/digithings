import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Nav, Footer, Emblem, StackRow, moduleById, modules } from "@digithings/web";
import { Brand, DT_NAV, DT_FOOTER, DT_FOOTER_META } from "../../_nav";

export const dynamicParams = false;
export function generateStaticParams() {
  return modules.map((m) => ({ id: m.id }));
}

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const m = moduleById(id);
  if (!m) return { title: "Module — digithings" };
  return { title: `${m.name} — digithings`, description: m.tagline };
}

export default async function ModulePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const m = moduleById(id);
  if (!m) notFound();

  return (
    <>
      <Nav brand={<Brand />} links={DT_NAV} />
      <main className="section">
        <div className="wrap" style={{ maxWidth: 820 }}>
          <p style={{ fontFamily: "var(--font-mono)", fontSize: ".8rem", color: "var(--ink-mute)", marginBottom: "1.4rem" }}>
            <a href="/architecture" style={{ color: "var(--ink-soft)" }}>architecture</a> / {m.id}
          </p>

          <div style={{ display: "flex", alignItems: "center", gap: "1rem", marginBottom: ".6rem" }}>
            <Emblem id={m.emblem} size={48} />
            <span className={`dg-tier t-${m.tier}`}>{m.tier === "roadmap" ? "roadmap" : `${m.tier} module`}</span>
          </div>
          <h1 style={{ fontFamily: "var(--font-display)", fontWeight: 400, fontSize: "clamp(2.6rem,6vw,4rem)", letterSpacing: "-.02em", lineHeight: 1.02, margin: ".4rem 0 .5rem" }}>{m.name}</h1>
          <p style={{ fontSize: "1.15rem", color: "var(--ink-soft)", maxWidth: "48ch" }}>{m.tagline}</p>
          <p style={{ fontFamily: "var(--font-mono)", fontSize: ".82rem", color: "var(--ink-mute)", marginTop: ".5rem" }}>
            {m.role}{m.port ? `  ·  :${m.port}` : ""}
          </p>

          {m.dockerCmd && (
            <div className="cmdline" style={{ marginTop: "1.6rem" }}>
              <span className="prompt">$</span> {m.dockerCmd}
            </div>
          )}

          <div style={{ marginTop: "2rem" }}>
            <p style={{ fontFamily: "var(--font-mono)", fontSize: ".72rem", letterSpacing: ".1em", textTransform: "uppercase", color: "var(--ink-mute)", marginBottom: ".6rem" }}>stack</p>
            <StackRow items={m.stack} />
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "1rem", margin: "2.2rem 0", maxWidth: "62ch" }}>
            {m.summary.map((p, i) => <p key={i} style={{ color: "var(--ink-soft)", fontSize: "1.05rem" }}>{p}</p>)}
          </div>

          <p style={{ fontFamily: "var(--font-mono)", fontSize: ".72rem", letterSpacing: ".1em", textTransform: "uppercase", color: "var(--ink-mute)", marginBottom: ".5rem" }}>initialize</p>
          <pre className="codeblock">{m.initSnippet.code}</pre>

          <div style={{ display: "flex", gap: ".75rem", flexWrap: "wrap", marginTop: "2rem" }}>
            {m.links.map((l, i) => (
              <a key={i} className={i === 0 ? "btn btn-primary" : "btn btn-ghost"} href={l.href}
                target={/^https?:/.test(l.href) ? "_blank" : undefined} rel={/^https?:/.test(l.href) ? "noopener noreferrer" : undefined}>
                {l.label}
              </a>
            ))}
          </div>

          {m.related.length > 0 && (
            <div style={{ marginTop: "3rem", paddingTop: "1.8rem", borderTop: "1px solid var(--hair)" }}>
              <p style={{ fontFamily: "var(--font-mono)", fontSize: ".72rem", letterSpacing: ".1em", textTransform: "uppercase", color: "var(--ink-mute)", marginBottom: "1rem" }}>related</p>
              <div style={{ display: "flex", gap: ".6rem", flexWrap: "wrap" }}>
                {m.related.map((rid) => {
                  const rm = moduleById(rid);
                  return <a key={rid} className="stack-chip" href={`/modules/${rid}`}>{rm?.name ?? rid}</a>;
                })}
              </div>
            </div>
          )}
        </div>
      </main>
      <Footer links={DT_FOOTER} meta={DT_FOOTER_META} />
    </>
  );
}
