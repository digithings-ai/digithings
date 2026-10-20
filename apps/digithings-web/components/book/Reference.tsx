/**
 * A "go deeper" card (DIG-2818 editorial rule).
 *
 * digibook explains the why; the reference docs carry the how — API docs,
 * module ARCHITECTURE.md files, the self-host and local-stack guides. A chapter
 * points at them with this card instead of reproducing env names, ports or file
 * paths in prose. Server component: plain link, prints as a link with its URL.
 *
 *   <Reference kind="API" href="/docs/api" title="digigraph API">
 *     Every orchestrator endpoint, with request and response shapes.
 *   </Reference>
 */
import type { ReactNode } from "react";

export const REPO_BLOB = "https://github.com/digithings-ai/digithings/blob/develop";

export interface ReferenceProps {
  href: string;
  title: string;
  kind?: "API" | "architecture" | "guide" | "reference";
  children?: ReactNode;
}

/** `repo:docs/SELF_HOST.md` → the file on GitHub, so chapters stay short. */
export function resolveReferenceHref(href: string): string {
  return href.startsWith("repo:") ? `${REPO_BLOB}/${href.slice(5).replace(/^\/+/, "")}` : href;
}

export default function Reference({ href, title, kind = "reference", children }: ReferenceProps) {
  const url = resolveReferenceHref(href);
  const external = /^https?:/.test(url);
  return (
    <a
      href={url}
      className="book-reference my-4 block max-w-[64ch] border border-hair px-4 py-3 no-underline"
      {...(external ? { target: "_blank", rel: "noreferrer" } : {})}
    >
      <span className="block font-mono text-[0.7rem] uppercase tracking-[0.08em] text-ink-soft">go deeper · {kind}</span>
      <span className="mt-1 block font-mono text-[0.95rem] text-ink">{title} →</span>
      {/* A div, not a span: MDX wraps the children in <p>, and <p> inside
          <span> is invalid nesting that the HTML parser rewrites before
          React hydrates. */}
      {children ? <div className="book-reference__body mt-1 text-[0.95rem] leading-[1.6] text-ink-soft">{children}</div> : null}
    </a>
  );
}
