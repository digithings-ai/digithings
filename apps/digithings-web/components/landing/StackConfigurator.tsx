/**
 * Study E — build your stack (review-only configurator).
 *
 * Two live columns: pick a provider per layer on the left, a digithings
 * option per layer on the right, and the diagram plus the invoice move
 * together — both render from the same pick, so graph and bill can never
 * disagree. Defaults are the most common off-the-shelf stack against
 * full self-hosted digithings.
 *
 * Client component (dropdown state); the diagrams are static renders, not
 * scroll walks, so picking re-draws instantly with no pin to fight.
 */

"use client";

import { useState } from "react";
import { ArchitectureDiagram } from "@digithings/ui";

import {
  DIGI_LAYERS,
  DEFAULT_DIGI_PICK,
  DEFAULT_PROVIDER_PICK,
  PROVIDER_LAYERS,
  digiSpec,
  pricePick,
  providerSpec,
  type Layer,
  type StackPick,
} from "@/lib/stackCatalog";
import { RAG_PRICING } from "@/lib/ragCost";

const LABEL = "font-mono text-[0.68rem] uppercase tracking-[0.08em] text-ink-mute";
const SELECT =
  "w-full border border-hair bg-surface px-[0.7rem] py-[0.55rem] font-mono text-[0.82rem] text-ink";
const TOTAL = "font-mono text-[clamp(1.4rem,2.6vw,2rem)] font-medium text-ink font-variant-numeric tabular-nums";

function usd(n: number): string {
  return `$${n.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}

function Column({
  title,
  layers,
  pick,
  onPick,
  diagram,
  caption,
}: {
  title: string;
  layers: Layer[];
  pick: StackPick;
  onPick: (pick: StackPick) => void;
  diagram: React.ReactNode;
  caption: string;
}) {
  const price = pricePick(layers, pick);
  return (
    <div className="flex min-w-0 flex-col gap-[1rem] border border-hair bg-surface p-[1.4rem]">
      <span className={LABEL}>{title}</span>
      {layers.map((layer) => (
        <label key={layer.id} className="flex flex-col gap-[0.35rem]">
          <span className={LABEL}>{layer.label}</span>
          <select
            className={SELECT}
            value={pick[layer.id]}
            onChange={(event) => onPick({ ...pick, [layer.id]: event.target.value })}
            aria-label={layer.label}
          >
            {layer.options.map((option) => (
              <option key={option.id} value={option.id}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      ))}
      {diagram}
      <p className="m-0 font-mono text-[0.72rem] leading-[1.6] text-ink-mute">{caption}</p>
      <div className="flex flex-col gap-[0.25rem] border-t border-hair pt-[0.8rem]">
        {price.lines.map((line) => (
          <div key={line.label} className="flex items-baseline justify-between gap-[1rem] font-mono text-[0.78rem]">
            <span className="text-ink-soft">
              {line.estimate ? "~" : ""}
              {line.label}
            </span>
            <span className="text-ink font-variant-numeric tabular-nums">{usd(line.amount)}</span>
          </div>
        ))}
      </div>
      <div className="flex items-baseline justify-between gap-[1rem] border-t border-hair pt-[0.8rem]">
        <span className={LABEL}>setup / monthly</span>
        <span className={TOTAL}>
          {usd(price.setup)} / {usd(price.monthly)}
        </span>
      </div>
    </div>
  );
}

export function StackConfigurator() {
  const [providerPick, setProviderPick] = useState<StackPick>(DEFAULT_PROVIDER_PICK);
  const [digiPick, setDigiPick] = useState<StackPick>(DEFAULT_DIGI_PICK);
  return (
    <section aria-label="Study E — build your stack" className="line-b">
      <div className="mx-auto flex max-w-[var(--frame-w)] flex-col gap-[0.5rem] px-[var(--page-pad)] pt-[2.5rem]">
        <span className={LABEL}>study E · build your stack</span>
        <p className="m-0 max-w-[var(--measure-prose)] text-[0.9rem] leading-[1.7] text-ink-soft">
          Pick a provider per layer on the left, a digithings option per layer on the
          right. Same 1GB agent, same thousand answers a day — the drawings and the
          invoices move with every pick.
        </p>
      </div>
      <div className="mx-auto grid max-w-[var(--frame-w)] gap-[1.5rem] px-[var(--page-pad)] py-[2rem] min-[960px]:grid-cols-2">
        <Column
          title="their stack · your picks"
          layers={PROVIDER_LAYERS}
          pick={providerPick}
          onPick={setProviderPick}
          diagram={<ArchitectureDiagram spec={providerSpec(providerPick)} />}
          caption="Every pick is a vendor with a meter. Mix freely — the boundary counts them."
        />
        <Column
          title="digithings · your picks"
          layers={DIGI_LAYERS}
          pick={digiPick}
          onPick={setDigiPick}
          diagram={<ArchitectureDiagram spec={digiSpec(digiPick)} />}
          caption="Every pick is a module with an option. Self-hosted rows bill $0 on your hardware."
        />
      </div>
      <p className="mx-auto max-w-[var(--frame-w)] px-[var(--page-pad)] pb-[2.5rem] m-0 font-mono text-[0.72rem] leading-[1.7] text-ink-mute">
        List prices researched {RAG_PRICING.researchedAt}; ~ marks single-source estimates.
        Planning figures, not quotes. Digithings extras ride along unpriced: web-search
        tooling, graph API, telemetry and the chat UI are in every digithings pick.
      </p>
    </section>
  );
}
