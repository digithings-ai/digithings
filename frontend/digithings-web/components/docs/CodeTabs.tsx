"use client";
import { useState } from "react";
import { CopyButton } from "@/lib/CopyButton";
import type { CodeExample } from "@/lib/apiDocs";

const LABEL: Record<string, string> = { bash: "curl", python: "Python", typescript: "TypeScript" };

/** Language-tabbed code block (curl / Python / TypeScript) with a copy button. */
export function CodeTabs({ examples }: { examples: CodeExample[] }) {
  const [sel, setSel] = useState(0);
  if (!examples.length) return null;
  const cur = examples[Math.min(sel, examples.length - 1)];
  return (
    <div className="doc-tabs">
      {examples.length > 1 && (
        <div className="doc-tabbar" role="tablist">
          {examples.map((e, i) => (
            <button
              key={e.lang}
              type="button"
              role="tab"
              aria-selected={i === sel}
              className={`doc-tab${i === sel ? " is-active" : ""}`}
              onClick={() => setSel(i)}
            >
              {LABEL[e.lang] ?? e.lang}
            </button>
          ))}
        </div>
      )}
      <div className="doc-code">
        <CopyButton text={cur.code} className="dc-code-copy" ariaLabel={`Copy ${LABEL[cur.lang] ?? cur.lang} example`} />
        <pre>
          <code>{cur.code}</code>
        </pre>
      </div>
    </div>
  );
}
