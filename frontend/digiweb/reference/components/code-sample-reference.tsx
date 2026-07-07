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

      <div className="cs-block cs-install">
        <div className="cs-tabs" role="tablist" aria-label="Install method">
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
        <pre className="cs-code">
          <span className="cs-prompt" aria-hidden="true">
            ${" "}
          </span>
          {active.code}
        </pre>
      </div>

      <div className="cs-block">
        <div className="cs-head">
          <span className="cs-lang">python</span>
          <CopyButton text={SNIPPET} k="snippet" copied={copied} onCopy={onCopy} />
        </div>
        <pre className="cs-code cs-multiline">{SNIPPET}</pre>
      </div>
    </section>
  );
}
