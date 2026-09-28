/**
 * The single app-first variant (review-only, Refs #4429).
 *
 * One section: app tabs on top, per-layer dropdowns per side, the guided
 * walk in the middle, the accounting strip pinned at the bottom. Boxes are
 * clickable — clicking a drawn box focuses its layer dropdown (resolved
 * through the stable `arch-service-<id>` handles the tour already emits,
 * so the walk, spotlight and camera never break). Dimmed boxes rest dimmed
 * unless the walk lights them (kit CSS hook, no tour logic change).
 *
 * Client component (tab + pick state). Lives on `/variants/why-copy` until
 * it wins, then migrates to the live band.
 */

"use client";

import { useState } from "react";
import { ArchitectureTour } from "@digithings/ui";

import { APP_PRESETS } from "@/lib/appPresets";
import {
  DIGI_LAYERS,
  PROVIDER_LAYERS,
  digiSpec,
  pricePick,
  providerSpec,
  type LayerId,
  type StackPick,
} from "@/lib/stackCatalog";
import { OWNED_TOUR_STEPS } from "@/lib/whyStack";

const HEADLINE = "m-0 font-mono text-[clamp(1.3rem,2.4vw,1.85rem)] font-medium leading-[1.2] tracking-[-0.02em] text-ink";
const LEDE = "m-0 max-w-[var(--measure-prose)] text-[0.9rem] leading-[1.7] text-ink-soft";
const LABEL = "font-mono text-[0.68rem] uppercase tracking-[0.08em] text-ink-mute";
const SELECT = "w-full border border-hair bg-surface px-[0.7rem] py-[0.55rem] font-mono text-[0.82rem] text-ink";
const TAB = "border border-hair bg-surface px-[1rem] py-[0.6rem] font-mono text-[0.82rem] text-ink-soft";
const TAB_ON = "border border-hair bg-surface px-[1rem] py-[0.6rem] font-mono text-[0.82rem] text-ink shadow-[inset_0_0_0_1px_var(--accent)]";

/** Drawn box id -> its layer dropdown, per side. Boxes without a layer (app, gateways as drawn) are not configurable. */
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

function usd(n: number): string {
  return `$${n.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}

export function AppFirstSection() {
  const [appId, setAppId] = useState(APP_PRESETS[0].id);
  const preset = APP_PRESETS.find((a) => a.id === appId) ?? APP_PRESETS[0];
  const [picks, setPicks] = useState<Record<string, { provider: StackPick; digi: StackPick }>>(() =>
    Object.fromEntries(
      APP_PRESETS.map((a) => [a.id, { provider: a.providerDefaults, digi: a.digiDefaults }]),
    ),
  );
  const pick = picks[preset.id];
  const setPick = (side: "provider" | "digi", layer: LayerId, option: string) =>
    setPicks((prev) => ({ ...prev, [preset.id]: { ...prev[preset.id], [side]: { ...prev[preset.id][side], [layer]: option } } }));

  const workload = preset.workload;
  const providerPrice = pricePick(PROVIDER_LAYERS, pick.provider, workload);
  const digiPrice = pricePick(DIGI_LAYERS, pick.digi, workload);

  /* Click a drawn box -> focus its layer dropdown. Side resolves through the
     tour's own compositional classes (leaving is the first side). */
  const onStageClick = (event: React.MouseEvent<HTMLDivElement>) => {
    const target = event.target as Element;
    const node = target.closest?.('[id^="arch-service-"]');
    if (!node) return;
    const boxId = node.id.replace("arch-service-", "");
    const sideEl = node.closest?.(".arch-tour__side");
    const side = sideEl?.classList.contains("arch-tour__side--leaving") ? "provider" : "digi";
    const layer = LAYER_BY_BOX[side][boxId];
    if (!layer) return;
    document.getElementById(`appfirst-${preset.id}-${side}-${layer}`)?.focus();
  };

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
          Pick an app. Configure either stack — click any box or use the dropdowns. The
          walk and the invoice move together.
        </p>
        <div className="flex flex-wrap gap-[0.5rem] pt-[0.5rem]" role="tablist" aria-label="Application">
          {APP_PRESETS.map((a) => (
            <button
              key={a.id}
              role="tab"
              aria-selected={a.id === preset.id}
              className={a.id === preset.id ? TAB_ON : TAB}
              onClick={() => setAppId(a.id)}
            >
              {a.tab}
            </button>
          ))}
        </div>
        <p className={LEDE}>{preset.subhead}</p>
      </div>

      <div className="mx-auto grid max-w-[var(--frame-w)] gap-[1rem] px-[var(--page-pad)] pt-[1.5rem] min-[960px]:grid-cols-2">
        <div className="flex flex-col gap-[0.6rem]">
          <span className={LABEL}>their stack · configure</span>
          {PROVIDER_LAYERS.map((layer) => (
            <label key={layer.id} className="flex flex-col gap-[0.3rem]">
              <span className={LABEL}>{layer.label}</span>
              <select
                id={`appfirst-${preset.id}-provider-${layer.id}`}
                className={SELECT}
                value={pick.provider[layer.id]}
                onChange={(e) => setPick("provider", layer.id, e.target.value)}
              >
                {layer.options.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
        <div className="flex flex-col gap-[0.6rem]">
          <span className={LABEL}>digithings · configure</span>
          {DIGI_LAYERS.map((layer) => (
            <label key={layer.id} className="flex flex-col gap-[0.3rem]">
              <span className={LABEL}>{layer.label}</span>
              <select
                id={`appfirst-${preset.id}-digi-${layer.id}`}
                className={SELECT}
                value={pick.digi[layer.id]}
                onChange={(e) => setPick("digi", layer.id, e.target.value)}
              >
                {layer.options.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
          ))}
          <button
            type="button"
            className={TAB}
            onClick={() => setPicks((prev) => ({ ...prev, [preset.id]: { ...prev[preset.id], digi: preset.recommended } }))}
            title={preset.recommendedNote}
          >
            Apply recommended: {preset.recommendedNote}
          </button>
        </div>
      </div>

      <div className={`whyx${dimClass}`} onClick={onStageClick}>
        <div className="whyx__block">
          <div className="whyx__tours">
            <div className="whyx__tour">
              <ArchitectureTour
                sides={[
                  {
                    spec: providerSpec(pick.provider, workload, { appLabel: preset.providerApp }),
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
