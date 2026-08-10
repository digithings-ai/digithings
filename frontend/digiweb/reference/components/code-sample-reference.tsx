"use client";

import { useState } from "react";

const INSTALL = [
  { id: "docker", label: "docker", code: "docker compose up -d" },
  { id: "pip", label: "pip", code: "pip install digithings" },
  { id: "uv", label: "uv", code: "uv add digithings" },
] as const;

const SNIPPET = `from digiquant import backtest

result = backtest("trend_xsec", symbol="ETH-USD", years=8)
print(result.tearsheet())   # PF 6.62 · maxDD -59.2%`;

/**
 * Code sample — the developer-docs staple: a copyable command with a package-
 * manager switcher, and a syntax-lit snippet beside it. The command is the call
 * to action — one tap copies it to the clipboard, with the copy button flipping
 * to a confirmed state on success. Interactive display template.
 */
function CopyButton({ text, k, copied, onCopy }: {
  text: string;
  k: string;
  copied: string | null;
  onCopy: (k: string, text: string) => void;
}) {
  const is = copied === k;
  return (
    <button
      type="button"
      className={`cs-copy${is ? " is-copied" : ""}`}
      onClick={() => onCopy(k, text)}
      aria-label={is ? "Copied" : "Copy to clipboard"}
    >
      {is ? "copied ✓" : "copy"}
    </button>
  );
}

export function CodeSampleReference() {
  const [tab, setTab] = useState<(typeof INSTALL)[number]["id"]>("docker");
  const [copied, setCopied] = useState<string | null>(null);
  const active = INSTALL.find((t) => t.id === tab) ?? INSTALL[0];

  const onCopy = (key: string, text: string) => {
    navigator.clipboard?.writeText(text).catch(() => {});
    setCopied(key);
    window.setTimeout(() => setCopied((c) => (c === key ? null : c)), 1500);
  };

  return (
    <section className="section-block code-sample">
      <p className="kicker">{"// code sample"}</p>
      <h2 className="title">The snippet is the CTA.</h2>
      <p className="section-copy">
        The developer-docs staple: a copyable command with a switcher for the package manager, and
        a syntax-lit snippet beside it. The command <em>is</em> the call to action — one tap to the
        clipboard, honest about what runs.
      </p>

      <div className="cs-block cs-install mt-[1.2rem] max-w-[640px] overflow-hidden rounded-[12px] border border-hair bg-term-bg">
        <div
          className="flex items-center gap-[0.2rem] border-b border-hair py-[0.4rem] pl-[0.9rem] pr-[0.5rem]"
          role="tablist"
          aria-label="Install method"
        >
          {INSTALL.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={t.id === tab}
              className={`cs-tab${t.id === tab ? " on" : ""}`}
              onClick={() => setTab(t.id)}
            >
              {t.label}
            </button>
          ))}
          <CopyButton text={active.code} k="install" copied={copied} onCopy={onCopy} />
        </div>
        <pre className="m-0 overflow-x-auto whitespace-pre px-[1rem] py-[0.9rem] font-mono text-[0.8rem] leading-[1.7] text-ink">
          <span className="text-accent" aria-hidden="true">
            ${" "}
          </span>
          {active.code}
        </pre>
      </div>

      <div className="cs-block mt-[1.2rem] max-w-[640px] overflow-hidden rounded-[12px] border border-hair bg-term-bg">
        <div className="flex items-center gap-[0.2rem] border-b border-hair py-[0.4rem] pl-[0.9rem] pr-[0.5rem]">
          <span className="font-mono text-[0.62rem] uppercase tracking-[0.1em] text-ink-mute">
            python
          </span>
          <CopyButton text={SNIPPET} k="snippet" copied={copied} onCopy={onCopy} />
        </div>
        <pre className="m-0 overflow-x-auto whitespace-pre px-[1rem] py-[0.9rem] font-mono text-[0.8rem] leading-[1.7] text-ink-soft">
          {SNIPPET}
        </pre>
      </div>
    </section>
  );
}
