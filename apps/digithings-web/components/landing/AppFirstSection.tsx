/**
 * The single app-first variant (review-only, Refs #4429).
 *
 * One section: app tabs on top, the guided walk in the middle, the
 * accounting strip pinned at the bottom. There are no dropdown rows —
 * every configurable box opens its layer's options IN the graph: click a
 * box and a popover anchors at the click with that layer's providers;
 * picking swaps the box label, mark and price in place, and the invoice
 * follows. Box ids stay stable, so the walk, spotlight and camera never
 * break. The popover is a keyboard-operable listbox (Escape closes, first
 * option autofocuses).
 *
 * Client component (tab + pick + popover state). Lives on
 * `/variants/why-copy` until it wins, then migrates to the live band.
 */

"use client";

import { useEffect, useState } from "react";
import { ArchitectureTour } from "@digithings/ui";

import { APP_PRESETS } from "@/lib/appPresets";
import {
  DIGI_LAYERS,
  PROVIDER_LAYERS,
  digiSpec,
  pricePick,
  providerSpec,
  type Layer,
  type LayerId,
  type StackPick,
} from "@/lib/stackCatalog";
import { OWNED_TOUR_STEPS } from "@/lib/whyStack";

const HEADLINE = "m-0 font-mono text-[clamp(1.3rem,2.4vw,1.85rem)] font-medium leading-[1.2] tracking-[-0.02em] text-ink";
const LEDE = "m-0 max-w-[var(--measure-prose)] text-[0.9rem] leading-[1.7] text-ink-soft";
const LABEL = "font-mono text-[0.68rem] uppercase tracking-[0.08em] text-ink-mute";
const TAB = "border border-hair bg-surface px-[1rem] py-[0.6rem] font-mono text-[0.82rem] text-ink-soft";
const TAB_ON = "border border-hair bg-surface px-[1rem] py-[0.6rem] font-mono text-[0.82rem] text-ink shadow-[inset_0_0_0_1px_var(--accent)]";

/** Drawn box id -> its layer, per side. Boxes without a layer are not configurable. */
const LAYER_BY_BOX: Record<"provider" | "digi", Record<string, LayerId | undefined>> = {
  provider: {
    api: "models",
    model: "models",
    embed: "embeddings",
    memory: "vector",
    record: "hosting",
    telemetry: "telemetry",
    machines: "hosting",
  },
  digi: { models: "models", memory: "vector", traces: "telemetry", claw: "hosting" },
};

const LAYERS_BY_SIDE: Record<"provider" | "digi", Layer[]> = {
  provider: PROVIDER_LAYERS,
  digi: DIGI_LAYERS,
};

function usd(n: number): string {
  return `$${n.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}

interface Popover {
  side: "provider" | "digi";
  layer: LayerId;
  x: number;
  y: number;
}

export function AppFirstSection() {
  const [appId, setAppId] = useState(APP_PRESETS[0].id);
  const preset = APP_PRESETS.find((a) => a.id === appId) ?? APP_PRESETS[0];
  const [picks, setPicks] = useState<Record<string, { provider: StackPick; digi: StackPick }>>(() =>
    Object.fromEntries(
      APP_PRESETS.map((a) => [a.id, { provider: a.providerDefaults, digi: a.digiDefaults }]),
    ),
  );
  const [pop, setPop] = useState<Popover | null>(null);
  const pick = picks[preset.id];

  useEffect(() => {
    if (!pop) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setPop(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pop]);

  const setPick = (side: "provider" | "digi", layer: LayerId, option: string) =>
    setPicks((prev) => ({ ...prev, [preset.id]: { ...prev[preset.id], [side]: { ...prev[preset.id][side], [layer]: option } } }));

  const workload = preset.workload;
  const providerPrice = pricePick(PROVIDER_LAYERS, pick.provider, workload);
  const digiPrice = pricePick(DIGI_LAYERS, pick.digi, workload);

  /* Click a drawn box -> open its layer's options anchored at the click.
     Side resolves through the tour's own compositional classes (leaving is
     the first side). */
  const onStageClick = (event: React.MouseEvent<HTMLDivElement>) => {
    const target = event.target as Element;
    const node = target.closest?.('[id^="arch-service-"]');
    if (!node) return;
    const boxId = node.id.replace("arch-service-", "");
    const sideEl = node.closest?.(".arch-tour__side");
    const side = sideEl?.classList.contains("arch-tour__side--leaving") ? "provider" : "digi";
    const layer = LAYER_BY_BOX[side][boxId];
    if (!layer) return;
    setPop({
      side,
      layer,
      x: Math.min(event.clientX, window.innerWidth - 280),
      y: Math.min(event.clientY + 12, window.innerHeight - 320),
    });
  };

  const popLayer = pop ? LAYERS_BY_SIDE[pop.side].find((l) => l.id === pop.layer) : undefined;
  const dimClass = preset.dimmedDigi.includes("vault") ? " arch-tour-dim-vault" : "";

  return (
    <section aria-label="App-first single variant" className="line-b">
      <div className="mx-auto flex max-w-[var(--frame-w)] flex-col gap-[0.5rem] px-[var(--page-pad)] pt-[2.5rem]">
        <span className={LABEL}>single variant · app-first · compose it yourself</span>
        <h2 className={HEADLINE}>
          <span className="why-rent">Their AI stack,</span>{" "}
          <span className="why-own">or the digithings stack you compose.</span>
        </h2>
        <p className={LEDE}>
          Pick an app, then click any box in either diagram to reconfigure its layer. The
          walk and the invoice move together.
        </p>
        <div className="flex flex-wrap gap-[0.5rem] pt-[0.5rem]" role="tablist" aria-label="Application">
          {APP_PRESETS.map((a) => (
            <button
              key={a.id}
              role="tab"
              aria-selected={a.id === preset.id}
              className={a.id === preset.id ? TAB_ON : TAB}
              onClick={() => {
                setAppId(a.id);
                setPop(null);
              }}
            >
              {a.tab}
            </button>
          ))}
        </div>
        <p className={LEDE}>{preset.subhead}</p>
      </div>

      <div className={`whyx${dimClass}`} onClick={onStageClick}>
        <div className="whyx__block">
          <div className="whyx__tours">
            <div className="whyx__tour">
              <ArchitectureTour
                sides={[
                  {
                    spec: providerSpec(pick.provider, workload, {
                      appLabel: preset.providerApp,
                      sourcesLabel: preset.providerSources,
                      review: preset.providerReview,
                    }),
                    steps: preset.leftSteps,
                    tag: "their stack",
                    rail: "end",
                    caption: "Every edge metered — per-token · per-query · per-gigabyte",
                  },
                  {
                    spec: digiSpec(pick.digi, workload, { appLabel: preset.digiApp }),
                    steps: OWNED_TOUR_STEPS,
                    tag: "digithings stack",
                    caption: "Every box a module — take one or run them all · digibase under all of them",
                  },
                ]}
                variant="camera"
              />
            </div>
          </div>
        </div>
      </div>

      {pop && popLayer ? (
        <>
          <div
            className="fixed inset-0 z-40"
            onClick={() => setPop(null)}
            aria-hidden="true"
          />
          <div
            role="listbox"
            aria-label={`${popLayer.label} options`}
            className="fixed z-50 flex w-[16rem] flex-col gap-[0.25rem] border border-hair bg-surface p-[0.7rem] shadow-[0_18px_50px_-20px_rgba(0,0,0,0.6)]"
            style={{ left: Math.max(pop.x, 8), top: Math.max(pop.y, 8) }}
          >
            <span className={LABEL}>{popLayer.label}</span>
            {popLayer.options.map((option, i) => (
              <button
                key={option.id}
                role="option"
                aria-selected={pick[pop.side][pop.layer] === option.id}
                autoFocus={i === 0}
                className={`px-[0.6rem] py-[0.5rem] text-left font-mono text-[0.8rem] ${
                  pick[pop.side][pop.layer] === option.id
                    ? "text-ink shadow-[inset_0_0_0_1px_var(--accent)]"
                    : "text-ink-soft hover:text-ink"
                }`}
                onClick={() => {
                  setPick(pop.side, pop.layer, option.id);
                  setPop(null);
                }}
              >
                {option.label}
              </button>
            ))}
          </div>
        </>
      ) : null}

      <div className="mx-auto flex max-w-[var(--frame-w)] flex-col gap-[0.6rem] px-[var(--page-pad)] pb-[1rem]">
        <button
          type="button"
          className={`${TAB} self-start`}
          onClick={() => setPicks((prev) => ({ ...prev, [preset.id]: { ...prev[preset.id], digi: preset.recommended } }))}
          title={preset.recommendedNote}
        >
          Apply recommended: {preset.recommendedNote}
        </button>
      </div>

      <div className="mx-auto grid max-w-[var(--frame-w)] gap-[1rem] px-[var(--page-pad)] pb-[2.5rem] min-[960px]:grid-cols-2">
        <div className="border border-hair bg-surface p-[1.2rem]">
          <span className={LABEL}>their invoice · monthly</span>
          <p className="m-0 font-mono text-[clamp(1.4rem,2.6vw,2rem)] font-medium text-ink font-variant-numeric tabular-nums">
            {usd(providerPrice.monthly)}
          </p>
          <p className="m-0 font-mono text-[0.78rem] text-ink-mute">setup {usd(providerPrice.setup)}</p>
        </div>
        <div className="border border-hair bg-surface p-[1.2rem]">
          <span className={LABEL}>digithings invoice · monthly</span>
          <p className="m-0 font-mono text-[clamp(1.4rem,2.6vw,2rem)] font-medium text-ink font-variant-numeric tabular-nums">
            {usd(digiPrice.monthly)}
          </p>
          <p className="m-0 font-mono text-[0.78rem] text-ink-mute">setup {usd(digiPrice.setup)}</p>
        </div>
      </div>
    </section>
  );
}
