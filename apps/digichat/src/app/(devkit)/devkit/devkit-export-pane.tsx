"use client";

import { useState } from "react";
import { buildComposeBundle, buildEmbedBundle } from "./devkit-export";

type ExportTab = "compose" | "embed" | "yaml";

function CopyBlock({ label, text, which }: { label: string; text: string; which: string }) {
  const [copied, setCopied] = useState<string | null>(null);
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between">
        <span className="font-mono text-[11px] text-muted-foreground">{label}</span>
        <button
          type="button"
          onClick={() => {
            void navigator.clipboard?.writeText(text).then(() => {
              setCopied(which);
              window.setTimeout(() => setCopied((c) => (c === which ? null : c)), 1500);
            });
          }}
          className="rounded-md border px-2 py-0.5 text-xs hover:bg-accent"
        >
          {copied === which ? "copied ✓" : "copy"}
        </button>
      </div>
      <pre className="max-h-64 overflow-auto rounded-md border bg-muted/30 p-2 font-mono text-[11px] whitespace-pre-wrap break-words">
        {text}
      </pre>
    </div>
  );
}

/**
 * Export popup: builds deploy artifacts from the LIVE draft text.
 * Client-side only — no new API. Secrets never leave as values:
 * bundles substitute `${VAR}` placeholders and list a setup checklist.
 */
export function DevkitExportPane({
  slug,
  host,
  draftText,
  onClose,
}: {
  slug: string;
  host: string | null;
  draftText: string;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<ExportTab>("compose");
  const bundle = buildComposeBundle(slug, draftText);
  const embed = buildEmbedBundle(slug, host);

  const tabs: Array<{ id: ExportTab; label: string }> = [
    { id: "compose", label: "local compose" },
    { id: "embed", label: "embed snippet" },
    { id: "yaml", label: "config YAML" },
  ];

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Export deployment"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="flex max-h-[85vh] w-full max-w-2xl flex-col gap-3 overflow-hidden rounded-lg border bg-background p-4">
        <div className="flex items-center justify-between">
          <h2 className="font-mono text-sm font-semibold">export ‘{slug}’</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close export"
            className="rounded-md border px-2 py-0.5 text-xs hover:bg-accent"
          >
            ✕
          </button>
        </div>
        <div role="tablist" aria-label="Export targets" className="flex gap-1">
          {tabs.map((t) => (
            <button
              key={t.id}
              role="tab"
              aria-selected={tab === t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`rounded-md border px-2 py-1 font-mono text-xs ${
                tab === t.id ? "bg-accent" : "hover:bg-accent/50"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="flex min-h-0 flex-col gap-3 overflow-y-auto">
          {tab === "compose" ? (
            <>
              <p className="text-xs text-muted-foreground">
                Launch this config locally: save the config file, fill the .env
                fragment, and run the up command from the repo root
                (digichat profile in the root compose file).
              </p>
              <CopyBlock label={`${slug}.yaml (secrets → placeholders)`} text={bundle.configYaml} which="cfg" />
              <CopyBlock label=".env fragment" text={bundle.envFragment} which="env" />
              <CopyBlock label="up command (repo root)" text={bundle.upCommand} which="up" />
              <div className="rounded-md border p-2">
                <p className="mb-1 font-mono text-[11px] text-muted-foreground">checklist</p>
                <ol className="flex list-decimal flex-col gap-0.5 pl-4 text-xs">
                  {bundle.checklist.map((c) => (
                    <li key={c}>{c}</li>
                  ))}
                </ol>
              </div>
              {bundle.hasSentinel ? (
                <p className="rounded-md border border-amber-500/50 p-2 text-xs text-amber-600 dark:text-amber-400">
                  Draft still holds redacted sentinels — set the real secret
                  values in env; placeholders above already point at the right vars.
                </p>
              ) : null}
            </>
          ) : null}
          {tab === "embed" ? (
            <>
              <p className="text-xs text-muted-foreground">
                Iframe this deployment into a parent site. Token passes as
                `&token=…` unless the host is first-party registered.
              </p>
              <CopyBlock label="iframe snippet" text={embed.snippet} which="snip" />
              <CopyBlock label="operator env" text={embed.envLines} which="eenv" />
              <ul className="flex list-disc flex-col gap-0.5 pl-4 text-xs text-muted-foreground">
                {embed.notes.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            </>
          ) : null}
          {tab === "yaml" ? (
            bundle.hasSentinel ? (
              <p className="rounded-md border border-amber-500/50 p-2 text-xs text-amber-600 dark:text-amber-400">
                Blocked: this draft still holds redacted sentinels, so a raw
                copy would not run elsewhere. Save first (restores secrets
                server-side), or use the local compose tab — its placeholders
                already cover the secret lines.
              </p>
            ) : (
              <CopyBlock label={`${slug}.yaml`} text={draftText} which="raw" />
            )
          ) : null}
        </div>
      </div>
    </div>
  );
}
