"use client";

/**
 * The tabbed stack for V2 — three genuinely different readings of the same
 * eleven modules: the bento (weight by tier), a tier grouping, and a dependency
 * ranking using the registry's real `edges` counts. Client-side because
 * `TabStrip` is controlled.
 */
import { useState } from "react";

import { BentoCell, BentoGrid, Emblem, TabStrip, tabPanelId } from "@digithings/ui";
import { BENTO, MODULE_ROWS, type ModuleRow } from "./content";

const TAB_LABEL = "Stack views";

const TABS = [
  { id: "glance", label: "at a glance" },
  { id: "tier", label: "by tier" },
  { id: "deps", label: "by dependency" },
];

function byId(id: string): ModuleRow | undefined {
  return MODULE_ROWS.find((m) => m.id === id);
}

function ModuleCell({ id, span }: { id: string; span?: "hero" | "wide" | "tall" | "unit" }) {
  const m = byId(id);
  if (!m) return null;
  const roadmap = m.tier === "roadmap";
  return (
    <BentoCell span={span ?? "unit"} livery={m.emblem} className="gap-[0.6rem]">
      <div className="flex items-start justify-between gap-[0.6rem]">
        <Emblem id={m.emblem} size={span === "hero" ? 30 : 20} />
        {roadmap ? (
          <span className="font-mono text-[0.58rem] uppercase tracking-[0.08em] text-ink-mute">roadmap</span>
        ) : null}
      </div>
      <div>
        <p className={`m-0 font-mono text-ink ${span === "hero" ? "bento-name" : "text-[0.95rem]"}`}>{m.name}</p>
        <p className="mt-[0.3rem] mb-0 text-[0.78rem] leading-[1.5] text-ink-soft">{m.role}</p>
      </div>
    </BentoCell>
  );
}

const TIERS: { tier: string; label: string }[] = [
  { tier: "core", label: "core" },
  { tier: "support", label: "support" },
  { tier: "roadmap", label: "roadmap" },
];

const TIER_NOTE: Record<string, string> = {
  core: "The four services a request actually travels through.",
  support: "Present in every deployment, but rarely the thing you came for.",
  roadmap: "Marked roadmap in the registry — not shipped.",
};

export function StackTabs() {
  const [active, setActive] = useState(0);

  return (
    <div>
      <TabStrip tabs={TABS} active={active} onChange={setActive} label={TAB_LABEL} variant="underline" sharedPanel />

      <div className="mt-[1.4rem]" role="tabpanel" id={tabPanelId(TAB_LABEL, TABS[active].id)}>
        {active === 0 ? (
          <BentoGrid>
            {BENTO.map(({ id, span }) => (
              <ModuleCell key={id} id={id} span={span} />
            ))}
          </BentoGrid>
        ) : null}

        {active === 1 ? (
          <div className="grid gap-[1.6rem]">
            {TIERS.map(({ tier, label }) => {
              const rows = MODULE_ROWS.filter((m) => m.tier === tier);
              return (
                <div key={tier}>
                  <div className="flex items-baseline justify-between border-b border-hair pb-[0.5rem]">
                    <span className="font-mono text-[0.72rem] uppercase tracking-[var(--tracking-meta)] text-ink">
                      {label}
                    </span>
                    <span className="font-mono text-[0.72rem] text-ink-mute">{rows.length}</span>
                  </div>
                  <p className="mt-[0.6rem] mb-0 text-[0.85rem] text-ink-mute">{TIER_NOTE[tier]}</p>
                  <ul className="mt-[0.8rem] grid list-none gap-[0.55rem] p-0">
                    {rows.map((m) => (
                      <li key={m.id} className="flex items-start gap-[0.7rem] text-[0.92rem] leading-[1.6]">
                        <Emblem id={m.emblem} size={16} />
                        <span>
                          <strong className="mr-[0.5rem] font-medium text-ink">{m.name}</strong>
                          <span className="text-ink-soft">{m.role}</span>
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              );
            })}
          </div>
        ) : null}

        {active === 2 ? (
          <div>
            <div className="flex items-baseline gap-[1rem] border-b border-hair pb-[0.5rem] font-mono text-[0.68rem] uppercase tracking-[var(--tracking-meta)] text-ink-mute">
              <span className="flex-1">module</span>
              <span>edges</span>
            </div>
            <ul className="m-0 list-none p-0">
              {[...MODULE_ROWS]
                .sort((a, b) => b.deps - a.deps)
                .map((m) => (
                  <li key={m.id} className="flex items-baseline gap-[1rem] border-b border-hair py-[0.55rem] font-mono text-[0.8rem]">
                    <span className="flex-1 text-ink">{m.name}</span>
                    <span className="text-ink-soft">{m.role}</span>
                    <span className="w-[3rem] text-right text-ink-mute">{m.deps}</span>
                  </li>
                ))}
            </ul>
            <p className="mt-[0.9rem] mb-0 font-mono text-[0.72rem] text-ink-mute">
              Counts are edges in the shared registry, not calls at runtime.
            </p>
          </div>
        ) : null}
      </div>
    </div>
  );
}
