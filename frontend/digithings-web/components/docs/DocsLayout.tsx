"use client";
import { Fragment, useState, type ReactNode } from "react";
import {
  modules,
  type ModuleNode,
  StackRow,
  Emblem,
  DocsLayout as DocsShell,
  type DocsNavGroup,
  EndpointDoc,
  type DocsEndpoint,
  DocsCodeBlock,
} from "@digithings/web";
import { apiDocs, type ModuleApiDoc, type Endpoint } from "@/lib/apiDocs";
import { guides, type Block } from "@/lib/sharedDocs";
import { guideToMarkdown, moduleToMarkdown } from "@/lib/docsSerializers";

/**
 * Full docs experience on the shared docs family (@digithings/web): DocsShell
 * owns the responsive sidebar + scroll-spy + mobile disclosure, EndpointDoc /
 * DocsCodeBlock own the endpoint and code-block chrome. This file keeps only
 * what is digithings content: the tier-grouped nav model, the shared guides
 * (Getting started / Authentication / Conventions), the per-module reference
 * merged from apiDocs, and "copy as Markdown" for AI agents. All static, so
 * the site exports cleanly.
 */
const ordered = [...modules].sort((a, b) => a.graphOrder - b.graphOrder);
const TIERS: { key: ModuleNode["tier"]; label: string }[] = [
  { key: "core", label: "Core" },
  { key: "support", label: "Support" },
  { key: "roadmap", label: "Roadmap" },
];

// Two-tone module wordmark for nav labels: shared DocsShell labels are
// ReactNode, so the brand styling travels in the markup (the plain half
// inherits the link's state color; the suffix is always accent).
function ModuleWordmark({ id }: { id: string }) {
  return (
    <>
      digi<span className="text-accent">{id.replace(/^digi/, "")}</span>
    </>
  );
}

const NAV: DocsNavGroup[] = [
  { label: "Guides", items: guides.map((g) => ({ id: g.id, label: g.title })) },
  ...TIERS.map((t) => ({
    label: t.label,
    items: ordered
      .filter((m) => m.tier === t.key)
      .map((m) => ({ id: m.id, label: <ModuleWordmark id={m.id} /> })),
  })).filter((g) => g.items.length > 0),
];

// App boundary: apiDocs examples are keyed by language id; the shared CodeTabs
// takes display labels, so the bash→curl naming decision lives here.
const EXAMPLE_LABEL: Record<string, string> = {
  bash: "curl",
  python: "Python",
  typescript: "TypeScript",
};

function toDocsEndpoint(ep: Endpoint): DocsEndpoint {
  return {
    ...ep,
    examples: ep.examples?.map((e) => ({ label: EXAMPLE_LABEL[e.lang] ?? e.lang, code: e.code })),
  };
}

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
        if (b.kind === "code") return <DocsCodeBlock key={i} code={b.code} />;
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
    <div className="mt-[0.5rem] flex flex-col gap-[0.25rem]">
      <span className="font-mono text-[0.68rem] uppercase tracking-[0.1em] text-ink-mute">
        {label}
      </span>
      <DocsCodeBlock code={code} copyLabel={`Copy ${label}`} />
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
            <table className="doc-fields w-full border-collapse text-[0.84rem]">
              <tbody>
                {d.scopes.map((s) => (
                  <tr key={s.scope}>
                    <td className="whitespace-nowrap">
                      <code className="dc-code-inline">{s.scope}</code>
                    </td>
                    <td className="w-full leading-[1.5] text-ink-soft">{s.grants}</td>
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
          <table className="doc-fields w-full border-collapse text-[0.84rem]">
            <tbody>
              {d.env.map((e) => (
                <tr key={e.name}>
                  <td className="whitespace-nowrap">
                    <code className="dc-code-inline">{e.name}</code>
                    {e.required && <span className="ml-[0.15rem] text-down" title="required">*</span>}
                  </td>
                  <td className="whitespace-nowrap font-mono text-[0.78rem] text-ink-mute">
                    {e.def ? e.def : "—"}
                  </td>
                  <td className="w-full leading-[1.5] text-ink-soft">{e.description}</td>
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
            <p className="m-0 mt-[0.5rem] text-[0.8rem] text-ink-mute">
              Base URL <code className="dc-code-inline">${d.baseUrlVar}</code> — the service URL from{" "}
              <code className="dc-code-inline">docker-compose.yml</code>.
            </p>
          )}
          <div className="mt-[0.5rem] flex flex-col gap-[1rem]">
            {d.endpoints.map((ep) => (
              <EndpointDoc key={`${ep.method} ${ep.path}`} ep={toDocsEndpoint(ep)} />
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
  return (
    <DocsShell
      nav={NAV}
      ariaLabel="docs"
      contentsLabel="contents"
      hero={{
        kicker: "// api docs",
        title: "digithings API reference.",
        lede:
          "Complete, end-to-end reference for the stack — setup, authentication, and every module's " +
          "endpoints with request/response schemas and runnable examples. Copy any page (or the whole " +
          "reference) as Markdown to drop into an AI agent.",
        actions: <CopyMd text={PAGE_MD} label="Copy all as Markdown" />,
      }}
    >
      {guides.map((g) => (
        <section className="doc-guide" id={g.id} key={g.id}>
          <h2 className="doc-guide-title">{g.title}</h2>
          <Blocks blocks={g.blocks} />
        </section>
      ))}

      {ordered.map((m) => (
        <ModuleDoc key={m.id} m={m} />
      ))}
    </DocsShell>
  );
}
