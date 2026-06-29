"use client";
import { Fragment, useEffect, useState, type ReactNode } from "react";
import { modules, type ModuleNode, StackRow, Emblem } from "@digithings/web";
import { CopyButton } from "@/lib/CopyButton";
import { apiDocs, type ModuleApiDoc, type Endpoint } from "@/lib/apiDocs";
import { guides, type Guide, type Block } from "@/lib/sharedDocs";
import { EndpointDoc } from "./Endpoint";

/**
 * Full docs experience: shared guides (Getting started / Authentication /
 * Conventions) + a complete per-module API reference, a sticky tier-grouped
 * sidebar with scroll-spy, and "copy as Markdown" for AI agents. Content is the
 * shared module data (@digithings/web) merged with the authored apiDocs/guides —
 * all static, so the site exports cleanly.
 */
const ordered = [...modules].sort((a, b) => a.graphOrder - b.graphOrder);
const TIERS: { key: ModuleNode["tier"]; label: string }[] = [
  { key: "core", label: "Core" },
  { key: "support", label: "Support" },
  { key: "roadmap", label: "Roadmap" },
];

// ── inline backtick → <code> for guide text ──────────────────────────────────
function Inline({ text }: { text: string }): ReactNode {
  const parts = text.split(/(`[^`]+`)/g);
  return (
    <>
      {parts.map((p, i) =>
        p.startsWith("`") && p.endsWith("`") ? (
          <code key={i} className="dc-code-inline">
            {p.slice(1, -1)}
          </code>
        ) : (
          <Fragment key={i}>{p}</Fragment>
        ),
      )}
    </>
  );
}

function Blocks({ blocks }: { blocks: Block[] }) {
  return (
    <>
      {blocks.map((b, i) => {
        if (b.kind === "h") return <h3 key={i} className="doc-guide-h">{b.text}</h3>;
        if (b.kind === "code")
          return (
            <div key={i} className="doc-code">
              <CopyButton text={b.code} className="dc-code-copy" ariaLabel="Copy code" />
              <pre>
                <code>{b.code}</code>
              </pre>
            </div>
          );
        if (b.kind === "list")
          return (
            <ul key={i} className="doc-guide-list">
              {b.items.map((it, j) => (
                <li key={j}>
                  <Inline text={it} />
                </li>
              ))}
            </ul>
          );
        return (
          <p key={i} className="doc-summary">
            <Inline text={b.text} />
          </p>
        );
      })}
    </>
  );
}

// ── markdown serializers (for "copy as Markdown") ─────────────────────────────
function guideToMarkdown(g: Guide): string {
  const L: string[] = [`## ${g.title}`, ""];
  for (const b of g.blocks) {
    if (b.kind === "h") L.push(`### ${b.text}`, "");
    else if (b.kind === "p") L.push(b.text, "");
    else if (b.kind === "list") {
      b.items.forEach((it) => L.push(`- ${it}`));
      L.push("");
    } else if (b.kind === "code") L.push("```" + b.lang, b.code, "```", "");
  }
  return L.join("\n").trim();
}

function endpointToMarkdown(ep: Endpoint, L: string[]): void {
  L.push(`### ${ep.method} ${ep.path}`, ep.summary, "");
  const meta = [ep.auth && `auth: ${ep.auth}`, ep.rateLimit && `rate: ${ep.rateLimit}`, ep.flag]
    .filter(Boolean)
    .join(" · ");
  if (meta) L.push(meta, "");
  if (ep.request?.length) {
    L.push("Request:");
    ep.request.forEach((f) => L.push(`- \`${f.name}\` (${f.type})${f.required ? " — required" : ""}: ${f.description}`));
    L.push("");
  }
  if (ep.responseFields?.length) {
    L.push("Response:");
    ep.responseFields.forEach((f) => L.push(`- \`${f.name}\` (${f.type}): ${f.description}`));
    L.push("");
  }
  if (ep.responseExample) L.push("Response example:", "```json", ep.responseExample, "```", "");
  ep.examples?.forEach((ex) => L.push("```" + ex.lang, ex.code, "```", ""));
}

function moduleToMarkdown(m: ModuleNode): string {
  const d: ModuleApiDoc = apiDocs[m.id] ?? {};
  const L: string[] = [`# ${m.id}`, "", `> ${m.tagline}`, ""];
  L.push(`**Role:** ${m.role} · **Tier:** ${m.tier}`, "");
  L.push("## Overview");
  m.summary.forEach((s) => L.push(s, ""));
  if (d.authNote || d.scopes?.length) {
    L.push("## Authentication");
    if (d.authNote) L.push(d.authNote, "");
    d.scopes?.forEach((s) => L.push(`- \`${s.scope}\` — ${s.grants}`));
    L.push("");
  }
  if (d.run) {
    L.push("## Run locally");
    if (d.run.compose) L.push("```bash", d.run.compose, "```", "");
    if (d.run.standalone) L.push("```bash", d.run.standalone, "```", "");
    if (d.run.cli) L.push("```bash", d.run.cli, "```", "");
    if (d.run.mcp) L.push(`MCP: \`${d.run.mcp}\``, "");
  }
  if (d.env?.length) {
    L.push("## Configuration");
    d.env.forEach((e) => L.push(`- \`${e.name}\`${e.def ? ` (default \`${e.def}\`)` : ""}${e.required ? " — required" : ""}: ${e.description}`));
    L.push("");
  }
  if (d.endpoints?.length) {
    L.push("## Endpoints", "");
    if (d.baseUrlVar) L.push(`Base URL: \`$${d.baseUrlVar}\` (the service URL from docker-compose.yml).`, "");
    d.endpoints.forEach((ep) => endpointToMarkdown(ep, L));
  }
  if (d.publicInterface?.length) {
    L.push("## Public interface");
    d.publicInterface.forEach((it) => L.push(`- \`${it.signature}\` — ${it.description}`));
    L.push("");
  }
  if (d.mcp?.length) {
    L.push("## MCP tools");
    d.mcp.forEach((t) => L.push(`- \`${t.name}\` — ${t.description}`));
    L.push("");
  }
  if (d.notes?.length) {
    L.push("## Notes");
    d.notes.forEach((n) => L.push(`- ${n}`));
    L.push("");
  }
  L.push("## Stack", m.stack.map((s) => s.name).join(", "), "");
  if (m.related.length) L.push("## Related", m.related.join(", "), "");
  if (m.links.length) {
    L.push("## Links");
    m.links.forEach((l) => L.push(`- [${l.label}](${l.href})`));
    L.push("");
  }
  return L.join("\n").trim() + "\n";
}

const PAGE_MD = [
  "# digithings API reference",
  "",
  ...guides.map(guideToMarkdown),
  ...ordered.map(moduleToMarkdown),
].join("\n\n---\n\n");

/** Labeled "copy as Markdown" button with a confirmation flip. */
function CopyMd({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="docs-copy"
      aria-label={label}
      onClick={() =>
        navigator.clipboard?.writeText(text).then(
          () => {
            setCopied(true);
            setTimeout(() => setCopied(false), 1400);
          },
          () => {},
        )
      }
    >
      <span aria-hidden="true">{copied ? "✓ " : "⌘ "}</span>
      {copied ? "copied" : label}
    </button>
  );
}

function RunBlock({ label, code }: { label: string; code: string }) {
  return (
    <div className="doc-run-line">
      <span className="doc-run-label">{label}</span>
      <div className="doc-code">
        <CopyButton text={code} className="dc-code-copy" ariaLabel={`Copy ${label}`} />
        <pre>
          <code>{code}</code>
        </pre>
      </div>
    </div>
  );
}

function ModuleDoc({ m }: { m: ModuleNode }) {
  const d: ModuleApiDoc = apiDocs[m.id] ?? {};
  const suffix = m.id.replace(/^digi/, "");
  const isRoad = m.tier === "roadmap";
  return (
    <article className="doc-mod" id={m.id}>
      <header className="doc-mod-head">
        <Emblem id={m.emblem} size={32} />
        <div className="doc-mod-title">
          <h2>
            <span className="dt-d">digi</span>
            <span className="dt-s">{suffix}</span>
          </h2>
          <span className="doc-mod-role">{m.role}</span>
        </div>
        <span className={`doc-badge${isRoad ? " is-road" : ""}`}>{m.tier}</span>
        <CopyMd text={moduleToMarkdown(m)} label="Markdown" />
      </header>

      <p className="doc-tagline">{m.tagline}</p>

      <section className="doc-block">
        <h3>Overview</h3>
        {m.summary.map((s, i) => (
          <p className="doc-summary" key={i}>
            {s}
          </p>
        ))}
      </section>

      {(d.authNote || d.scopes?.length) && (
        <section className="doc-block">
          <h3>Authentication</h3>
          {d.authNote && <p className="doc-summary">{d.authNote}</p>}
          {d.scopes && d.scopes.length > 0 && (
            <table className="doc-fields">
              <tbody>
                {d.scopes.map((s) => (
                  <tr key={s.scope}>
                    <td className="doc-f-name">
                      <code className="dc-code-inline">{s.scope}</code>
                    </td>
                    <td className="doc-f-desc">{s.grants}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}

      {d.run && (
        <section className="doc-block">
          <h3>Run locally</h3>
          {d.run.compose && <RunBlock label="compose" code={d.run.compose} />}
          {d.run.standalone && <RunBlock label="standalone" code={d.run.standalone} />}
          {d.run.cli && <RunBlock label="cli" code={d.run.cli} />}
          {d.run.mcp && <RunBlock label="mcp" code={d.run.mcp} />}
        </section>
      )}

      {d.env && d.env.length > 0 && (
        <section className="doc-block">
          <h3>Configuration</h3>
          <table className="doc-fields">
            <tbody>
              {d.env.map((e) => (
                <tr key={e.name}>
                  <td className="doc-f-name">
                    <code className="dc-code-inline">{e.name}</code>
                    {e.required && <span className="doc-req" title="required">*</span>}
                  </td>
                  <td className="doc-f-type">{e.def ? e.def : "—"}</td>
                  <td className="doc-f-desc">{e.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {d.endpoints && d.endpoints.length > 0 && (
        <section className="doc-block">
          <h3>Endpoints</h3>
          {d.baseUrlVar && (
            <p className="doc-meta-line">
              Base URL <code className="dc-code-inline">${d.baseUrlVar}</code> — the service URL from{" "}
              <code className="dc-code-inline">docker-compose.yml</code>.
            </p>
          )}
          <div className="doc-endpoints">
            {d.endpoints.map((ep) => (
              <EndpointDoc key={`${ep.method} ${ep.path}`} ep={ep} />
            ))}
          </div>
        </section>
      )}

      {d.publicInterface && d.publicInterface.length > 0 && (
        <section className="doc-block">
          <h3>Public interface</h3>
          <ul className="doc-iface">
            {d.publicInterface.map((it, i) => (
              <li key={i}>
                <code className="dc-code-inline">{it.signature}</code>
                <span className="doc-iface-desc">{it.description}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {d.mcp && d.mcp.length > 0 && (
        <section className="doc-block">
          <h3>MCP tools</h3>
          <ul className="doc-iface">
            {d.mcp.map((t) => (
              <li key={t.name}>
                <code className="dc-code-inline">{t.name}</code>
                <span className="doc-iface-desc">{t.description}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {d.notes && d.notes.length > 0 && (
        <section className="doc-block">
          <h3>Notes</h3>
          <ul className="doc-guide-list">
            {d.notes.map((n, i) => (
              <li key={i}>
                <Inline text={n} />
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="doc-block">
        <h3>Stack</h3>
        <StackRow items={m.stack} />
      </section>

      {m.related.length > 0 && (
        <section className="doc-block">
          <h3>Related</h3>
          <nav className="doc-links">
            {m.related.map((r) => (
              <a key={r} href={`#${r}`}>
                <span className="dt-d">digi</span>
                <span className="dt-s">{r.replace(/^digi/, "")}</span>
              </a>
            ))}
          </nav>
        </section>
      )}

      {m.links.length > 0 && (
        <section className="doc-block">
          <h3>Links</h3>
          <nav className="doc-links">
            {m.links.map((l, i) => (
              <a key={i} href={l.href} {...(l.href.startsWith("http") ? { target: "_blank", rel: "noopener noreferrer" } : {})}>
                {l.label} <span aria-hidden="true">→</span>
              </a>
            ))}
          </nav>
        </section>
      )}
    </article>
  );
}

export function DocsLayout() {
  const [active, setActive] = useState(guides[0]?.id ?? "");

  useEffect(() => {
    const ids = [...guides.map((g) => g.id), ...ordered.map((m) => m.id)];
    const els = ids.map((id) => document.getElementById(id)).filter((e): e is HTMLElement => !!e);
    const obs = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActive(visible[0].target.id);
      },
      { rootMargin: "-20% 0px -70% 0px", threshold: 0 },
    );
    els.forEach((el) => obs.observe(el));
    return () => obs.disconnect();
  }, []);

  return (
    <div className="docs-shell">
      <aside className="docs-side">
        <nav aria-label="docs">
          <div className="docs-side-group">
            <span className="docs-side-label">Guides</span>
            {guides.map((g) => (
              <a key={g.id} href={`#${g.id}`} className={active === g.id ? "is-active" : ""}>
                {g.title}
              </a>
            ))}
          </div>
          {TIERS.map((t) => {
            const rows = ordered.filter((m) => m.tier === t.key);
            if (!rows.length) return null;
            return (
              <div className="docs-side-group" key={t.key}>
                <span className="docs-side-label">{t.label}</span>
                {rows.map((m) => (
                  <a key={m.id} href={`#${m.id}`} className={active === m.id ? "is-active" : ""}>
                    <span className="dt-d">digi</span>
                    <span className="dt-s">{m.id.replace(/^digi/, "")}</span>
                  </a>
                ))}
              </div>
            );
          })}
        </nav>
      </aside>

      <div className="docs-content">
        <header className="docs-hero">
          <span className="kicker">{"// api docs"}</span>
          <h1>digithings API reference.</h1>
          <p>
            Complete, end-to-end reference for the stack — setup, authentication, and every module&apos;s
            endpoints with request/response schemas and runnable examples. Copy any page (or the whole
            reference) as Markdown to drop into an AI agent.
          </p>
          <div className="docs-hero-actions">
            <CopyMd text={PAGE_MD} label="Copy all as Markdown" />
          </div>
        </header>

        {guides.map((g) => (
          <section className="doc-guide" id={g.id} key={g.id}>
            <h2 className="doc-guide-title">{g.title}</h2>
            <Blocks blocks={g.blocks} />
          </section>
        ))}

        {ordered.map((m) => (
          <ModuleDoc key={m.id} m={m} />
        ))}
      </div>
    </div>
  );
}
