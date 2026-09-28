"use client";

import type { DigichatDeployment } from "@/lib/deploy-config/schema";
import { welcomeBodyLines, welcomeTitle } from "@/lib/deploy-config/schema";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-2 py-0.5 text-xs">
      <dt className="shrink-0 text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-right font-mono break-words">{children}</dd>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section aria-label={title} className="rounded-lg border p-2">
      <h3 className="mb-1 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">
        {title}
      </h3>
      <dl>{children}</dl>
    </section>
  );
}

function Pill({ on, label }: { on: boolean; label: string }) {
  return (
    <span
      className={`mr-1 mb-1 inline-block rounded-full border px-1.5 py-px font-mono text-[10px] ${
        on ? "border-green-500/50 text-green-600 dark:text-green-400" : "text-muted-foreground"
      }`}
    >
      {on ? "●" : "○"} {label}
    </span>
  );
}

/**
 * Human-readable extraction of a deployment config — the at-a-glance
 * alternative to reading raw YAML. Display-only; secrets never reach this
 * component (stripped server-side before serving).
 */
export function DevkitSummary({ deployment }: { deployment: DigichatDeployment }) {
  const { chrome } = deployment;
  const features = deployment.features;
  const featureFlags: Array<[string, boolean]> = [
    ["attachments", features.attachments],
    ["dictation", features.dictation],
    ["speech", features.speech],
    ["sources", features.sources],
    ["model picker", features.modelPicker],
    ["branch picker", features.branchPicker],
  ];

  return (
    <div className="flex flex-col gap-2">
      <Section title="Identity">
        <Row label="slug">{deployment.slug}</Row>
        <Row label="backend">{deployment.backend.type}</Row>
        {deployment.backend.type === "digigraph" ? (
          <>
            {deployment.backend.digisearchIndex ? (
              <Row label="index">{deployment.backend.digisearchIndex}</Row>
            ) : null}
            {deployment.backend.vaultPathPrefix ? (
              <Row label="vault prefix">{deployment.backend.vaultPathPrefix}</Row>
            ) : null}
          </>
        ) : null}
        {deployment.backend.type === "foundry" ? (
          <Row label="agent">{deployment.backend.agentName}</Row>
        ) : null}
        <Row label="persistence">{deployment.persistence}</Row>
        <Row label="auth">{deployment.auth}</Row>
      </Section>

      <Section title="Appearance">
        <Row label="skin">{chrome.skin}</Row>
        <Row label="theme">{chrome.theme}</Row>
        <Row label="mode">{chrome.mode}</Row>
        {chrome.title ? <Row label="title">{chrome.title}</Row> : null}
        {chrome.accent ? (
          <Row label="accent">
            <span
              aria-hidden
              className="mr-1 inline-block size-3 rounded-sm border align-middle"
              style={{ backgroundColor: chrome.accent.color }}
            />
            {chrome.accent.color}
          </Row>
        ) : null}
        {welcomeTitle(chrome.welcome) ? (
          <Row label="welcome">{welcomeTitle(chrome.welcome)}</Row>
        ) : null}
        {welcomeBodyLines(chrome.welcome).map((line) => (
          <Row key={line} label="welcome body">
            {line}
          </Row>
        ))}
        {chrome.placeholder ? <Row label="placeholder">{chrome.placeholder}</Row> : null}
        {chrome.suggestions && chrome.suggestions.length > 0 ? (
          <Row label="suggestions">{String(chrome.suggestions.length)}</Row>
        ) : null}
        {chrome.attribution !== undefined ? (
          <Row label="attribution">{chrome.attribution ? "on" : "off"}</Row>
        ) : null}
        {chrome.launcher ? (
          <Row label="launcher">{chrome.launcher.mode ?? "default"}</Row>
        ) : null}
      </Section>
      {chrome.suggestions && chrome.suggestions.length > 0 ? (
        <Section title="Starter prompts">
          <ul className="flex flex-col gap-1">
            {chrome.suggestions.map((s) => (
              <li key={s} className="rounded bg-muted/40 px-1.5 py-0.5 font-mono text-[11px]">
                {s}
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      <Section title="Features">
        <div>
          {featureFlags.map(([label, on]) => (
            <Pill key={label} on={on} label={label} />
          ))}
        </div>
        <Row label="view">{features.view}</Row>
        <Row label="thinking">{features.thinking}</Row>
        <Row label="page context">{features.pageContext}</Row>
      </Section>

      <Section title="Models">
        {deployment.models.default ? (
          <Row label="default">{deployment.models.default}</Row>
        ) : (
          <Row label="default">none</Row>
        )}
        {deployment.models.available.length > 0 ? (
          <div className="flex flex-col gap-0.5 pt-1">
            {deployment.models.available.map((m) => (
              <span key={m} className="text-right font-mono text-[11px]">
                {m}
              </span>
            ))}
          </div>
        ) : null}
        {deployment.models.allowPicker !== undefined ? (
          <Row label="picker">{deployment.models.allowPicker ? "allowed" : "locked"}</Row>
        ) : null}
      </Section>

      {deployment.tools && deployment.tools.catalog.length > 0 ? (
        <Section title="Tools">
          <Row label="user toggle">{deployment.tools.allowUserToggle ? "on" : "off"}</Row>
          <div className="pt-1">
            {deployment.tools.catalog.map((t) => (
              <Pill key={t.id} on={t.default ?? false} label={t.label ?? t.id} />
            ))}
          </div>
        </Section>
      ) : null}

      {deployment.mcp && deployment.mcp.servers.length > 0 ? (
        <Section title="MCP servers">
          <Row label="user servers">{deployment.mcp.allowUserServers ? "on" : "off"}</Row>
          <div className="flex flex-col gap-1 pt-1">
            {deployment.mcp.servers.map((s) => (
              <div key={s.id} className="rounded bg-muted/40 px-1.5 py-1 font-mono text-[11px]">
                <Pill on={s.default ?? false} label={s.label ?? s.id} />
                <div className="mt-0.5 break-all text-muted-foreground">{s.url}</div>
              </div>
            ))}
          </div>
        </Section>
      ) : null}

      <Section title="Gate">
        <Row label="mode">{deployment.gate.mode}</Row>
        <Row label="activity">{deployment.gate.activityDetail}</Row>
        {deployment.gate.llmAccess ? <Row label="llm access">{deployment.gate.llmAccess}</Row> : null}
        {deployment.gate.showByok !== undefined ? (
          <Row label="byok">{deployment.gate.showByok ? "shown" : "hidden"}</Row>
        ) : null}
        {deployment.gate.webSearch !== undefined ? (
          <Row label="web search">{deployment.gate.webSearch ? "on" : "off"}</Row>
        ) : null}
        {deployment.gate.requiredPlanTier ? (
          <Row label="min plan">{deployment.gate.requiredPlanTier}</Row>
        ) : null}
      </Section>
    </div>
  );
}
