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
 * Client component (tab + pick + popover state). Live in the `#why` band
 * (via `WhyStack`); mirrored on `/variants/why-copy` for testing.
 */

"use client";

import { useEffect, useState } from "react";
import { ArchitectureTour, type TourVariant } from "@digithings/ui";

import { APP_PRESETS } from "@/lib/appPresets";
import {
  DIGI_LAYERS,
  PROVIDER_LAYERS,
  morphSpec,
  pricePick,
  providerSpec,
  type Layer,
  type LayerId,
  type PricedLine,
  type StackPick,
} from "@/lib/stackCatalog";

const HEADLINE = "m-0 font-mono text-[clamp(1.3rem,2.4vw,1.85rem)] font-medium leading-[1.2] tracking-[-0.02em] text-ink";
const LEDE = "m-0 max-w-[var(--measure-prose)] text-[0.9rem] leading-[1.7] text-ink-soft";
const LABEL = "font-mono text-[0.68rem] uppercase tracking-[0.08em] text-ink-mute";
const TAB = "border border-hair bg-surface px-[1rem] py-[0.6rem] font-mono text-[0.82rem] text-ink-soft";
const TAB_ON = "border border-hair bg-surface px-[1rem] py-[0.6rem] font-mono text-[0.82rem] text-ink shadow-[inset_0_0_0_1px_var(--accent)]";

/** Drawn box id -> its layer on the provider topology. The morph drawing
    reuses provider box ids, so one map covers both diagrams; boxes without
    a layer (product, sources, review, terms, delivery) are not clickable. */
const PROVIDER_LAYER_BY_BOX: Record<string, LayerId | undefined> = {
  api: "models",
  model: "models",
  embed: "embeddings",
  memory: "vector",
  record: "hosting",
  telemetry: "telemetry",
  machines: "hosting",
  launcher: "hosting",
};

const LAYERS_BY_SIDE: Record<"provider" | "digi", Layer[]> = {
  provider: PROVIDER_LAYERS,
  digi: DIGI_LAYERS,
};

function usd(n: number): string {
  return `$${n.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}

const TABLE_LAYERS: { id: LayerId; label: string }[] = [
  { id: "models", label: "Models" },
  { id: "embeddings", label: "Embeddings" },
  { id: "vector", label: "Vector store" },
  { id: "telemetry", label: "Telemetry" },
  { id: "hosting", label: "Hosting" },
];

/** True when the app prices any line on the layer (setup or monthly). */
function layerHas(lines: PricedLine[], layer: LayerId): boolean {
  return lines.some((l) => l.layer === layer);
}

/** Monthly meters for one layer; 0 when the layer prices nothing monthly. */
function layerMonthly(lines: PricedLine[], layer: LayerId): number {
  return lines.filter((l) => l.layer === layer && l.recurring).reduce((n, l) => n + l.amount, 0);
}

/** Setup or monthly total across a set of layers. */
function sumFor(lines: PricedLine[], layers: Set<LayerId>, recurring: boolean): number {
  return lines
    .filter((l) => layers.has(l.layer) && l.recurring === recurring)
    .reduce((n, l) => n + l.amount, 0);
}

function layerEst(lines: PricedLine[], layer: LayerId): boolean {
  return lines.some((l) => l.layer === layer && l.estimate);
}

function cell(n: number, est: boolean): string {
  return `${est ? "~" : ""}${usd(n)}`;
}

const ALL_LAYERS: Set<LayerId> = new Set(["models", "embeddings", "vector", "telemetry", "hosting"]);

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
  /* Controlled walk position: the invoice's digi column cuts one row per
     morph beat off this. Tab switches keep it (every app walks 5 + 4). */
  const [tourStep, setTourStep] = useState(0);
  const [tourMode, setTourMode] = useState<TourVariant>("camera");
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
  const effProvider = { ...pick.provider, ...preset.fixedLayers };
  const effDigi = { ...pick.digi, ...preset.fixedLayers };
  const providerPrice = pricePick(PROVIDER_LAYERS, effProvider, workload, preset.topology);
  const digiPrice = pricePick(DIGI_LAYERS, effDigi, workload, preset.topology);

  /* Morph frames: cumulative swaps through each beat. Frame 0 is the
     provider copy (it waits, dimmed, while their stack is walked). */
  const swapAt = preset.leftSteps.length;
  const morphIdx = tourStep - swapAt;
  const morphSpecs = preset.morphSteps.map((_, i) => {
    const done = preset.morphSteps.slice(0, i + 1);
    return morphSpec(effProvider, effDigi, workload, {
      appLabel: preset.providerApp,
      sourcesLabel: preset.providerSources,
      topology: preset.topology,
      replaced: [...new Set(done.flatMap((b) => b.layers))],
      boxes: [...new Set(done.flatMap((b) => b.boxes))],
      email: done.some((b) => b.email),
    });
  });

  /* Invoice rows the digi column has cut so far. Static fallback (no scroll
     drive) reads the end state, matching its fully-morphed diagram. */
  const revealed: Set<LayerId> =
    tourMode === "static"
      ? ALL_LAYERS
      : new Set(
          (morphIdx < 0 ? [] : preset.morphSteps.slice(0, morphIdx + 1)).flatMap((b) => b.layers),
        );

  /* Walk position for the text rail: one flat timeline across the provider
     walk and the morph beats. The rail shows the current step's copy while
     the diagrams light the matching boxes. */
  const allSteps = [...preset.leftSteps, ...preset.morphSteps];
  /* Overlap-safe static check (no "static" literal: the resolved TourVariant
     union varies between src and the workspace types). */
  const isStatic = tourMode !== "camera" && tourMode !== "highlight";
  const inMorph = morphIdx >= 0 && !isStatic;
  const curStep = allSteps[Math.min(Math.max(tourStep, 0), allSteps.length - 1)];
  const stepNo = morphIdx < 0 ? tourStep + 1 : morphIdx + 1;
  const stepTotal = morphIdx < 0 ? preset.leftSteps.length : preset.morphSteps.length;
  /* Invoice digi-column emphasis: plain until the scroll reaches the morph,
     then one accent frame so the eye moves from their total to digi's. */
  const digiHi =
    inMorph && !isStatic ? " shadow-[inset_0_0_0_1px_var(--accent)]" : "";

  /* Boxes already flipped at the current walk position (for click routing:
     a flipped box reconfigures the digi pick, an unflipped one the provider
     pick). Static reads the end state. Box-granular: finance flips the
     runner a beat before the archive even though both cut hosting. */
  const swappedNow = (): Set<string> => {
    if (tourMode === "static")
      return new Set(preset.morphSteps.flatMap((b) => b.boxes));
    if (morphIdx < 0) return new Set();
    return new Set(preset.morphSteps.slice(0, morphIdx + 1).flatMap((b) => b.boxes));
  };

  /* Click a drawn box -> open its layer's options anchored at the click.
     The provider diagram always reconfigures the provider pick. On the
     morph diagram an unswapped box does the same; a swapped one
     reconfigures the digi pick, so either end stays interchangeable. */
  const onStageClick = (event: React.MouseEvent<HTMLDivElement>) => {
    const target = event.target as Element;
    const node = target.closest?.('[id^="arch-service-"]');
    if (!node) return;
    const boxId = node.id.replace("arch-service-", "");
    const sideEl = node.closest?.(".arch-tour__side");
    if (!sideEl?.classList.contains("arch-tour__side--leaving")) {
      const layer = PROVIDER_LAYER_BY_BOX[boxId];
      if (!layer) return;
      const side = swappedNow().has(boxId) ? "digi" : "provider";
      setPop({
        side,
        layer,
        x: Math.min(event.clientX, window.innerWidth - 280),
        y: Math.min(event.clientY + 12, window.innerHeight - 320),
      });
      return;
    }
    const layer = PROVIDER_LAYER_BY_BOX[boxId];
    if (!layer) return;
    setPop({
      side: "provider",
      layer,
      x: Math.min(event.clientX, window.innerWidth - 280),
      y: Math.min(event.clientY + 12, window.innerHeight - 320),
    });
  };

  const popLayer = pop ? LAYERS_BY_SIDE[pop.side].find((l) => l.id === pop.layer) : undefined;
  const popPick = pop ? (pop.side === "provider" ? effProvider : effDigi) : pick.provider;

  return (
    <section aria-label="App-first single variant" className="flex min-h-screen flex-col">
      <div className="mx-auto flex w-full max-w-[var(--frame-w)] flex-col gap-[0.5rem] px-[var(--page-pad)] pt-[1.25rem]">
        <span className={LABEL}>single variant · app-first · compose it yourself</span>
        <h2 className={HEADLINE}>
          <span className="why-rent transition-opacity" style={{ opacity: inMorph ? 0.4 : 1 }}>
            Their AI stack,
          </span>{" "}
          <span className="why-own transition-opacity" style={{ opacity: inMorph ? 1 : 0.4 }}>
            or the digithings stack you compose.
          </span>
        </h2>
        <p className={LEDE}>
          Pick an app and walk their stack — then watch it swap to digithings box by
          box while the invoice cuts live. Click any box to reconfigure its layer.
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

      <div className="whyx flex-1" onClick={onStageClick}>
        <div className="whyx__block">
          <div className="mx-auto grid w-full max-w-[var(--frame-w)] gap-[1rem] px-[var(--page-pad)] lg:grid-cols-[minmax(15rem,20rem)_minmax(0,1fr)]">
            {/* Text rail: the walk-through copy, one step at a time, evolving
                with the scroll-driven tour on every graph. Desktop only; the
                static/mobile fallback reads the tour's own full step list. */}
            <aside
              aria-live="polite"
              className="hidden self-start border border-hair bg-surface p-[1rem] lg:sticky lg:top-[1rem] lg:block"
            >
              <span className={LABEL}>
                {morphIdx < 0 ? "their stack" : "digithings stack"} · {stepNo} of {stepTotal}
              </span>
              <div key={curStep.id} className="why-rail-step">
                <h3 className="m-0 pt-[0.5rem] font-mono text-[1.05rem] font-medium leading-[1.35] text-ink">
                  {curStep.label}
                </h3>
                <p className="m-0 pt-[0.5rem] text-[0.85rem] leading-[1.7] text-ink-soft">{curStep.line}</p>
              </div>
            </aside>
            <div className="whyx__tours">
              <div className="whyx__tour">
                <ArchitectureTour
                sides={[
                  {
                    spec: providerSpec(effProvider, workload, {
                      appLabel: preset.providerApp,
                      sourcesLabel: preset.providerSources,
                      topology: preset.topology,
                    }),
                    steps: preset.leftSteps,
                    tag: "their stack",
                    caption: preset.providerCaption,
                  },
                  {
                    spec: morphSpecs[morphSpecs.length - 1],
                    specs: morphSpecs,
                    steps: preset.morphSteps,
                    tag: "digithings stack",
                    caption: preset.morphCaption,
                  },
                ]}
                variant="camera"
                className="arch-tour-morph"
                step={tourStep}
                onStepChange={setTourStep}
                onModeChange={setTourMode}
              />
              </div>
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
                aria-selected={popPick[pop.layer] === option.id}
                autoFocus={i === 0}
                className={`px-[0.6rem] py-[0.5rem] text-left font-mono text-[0.8rem] ${
                  popPick[pop.layer] === option.id
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

      {/* Sticky within the section: the invoice stays pinned to the viewport
          bottom while the walk scrolls, and swaps live with the app and
          every pick. Opaque card so scrolled content slides underneath. */}
      <div className="sticky bottom-0 z-30 mx-auto max-w-[var(--frame-w)] px-[var(--page-pad)] pb-[1rem]">
        <div className="border border-hair bg-surface p-[1.2rem] shadow-[0_-18px_50px_-20px_rgba(0,0,0,0.6)]">
          <span className={LABEL}>invoice · always live · digi column cuts as boxes swap</span>
          <table className="mt-[0.6rem] w-full border-collapse font-mono text-[0.8rem]">
            <thead>
              <tr className="text-left text-ink-mute">
                <th className="py-[0.3rem] pr-[0.6rem] font-normal">Layer</th>
                <th className="py-[0.3rem] pr-[0.6rem] text-right font-normal">Their $/mo</th>
                <th className={`py-[0.3rem] text-right font-normal${digiHi}`}>digi $/mo</th>
              </tr>
            </thead>
            <tbody className="font-variant-numeric tabular-nums">
              {TABLE_LAYERS.map((row) => {
                const theirOn = layerHas(providerPrice.lines, row.id);
                const digiOn = layerHas(digiPrice.lines, row.id);
                const cut = revealed.has(row.id);
                const digiCell = !digiOn ? (
                  <span>$0 — not in this app</span>
                ) : !cut ? (
                  <span>—</span>
                ) : (
                  <span>{cell(layerMonthly(digiPrice.lines, row.id), layerEst(digiPrice.lines, row.id))}</span>
                );
                return (
                  <tr key={row.id} className="border-t border-hair">
                    <td className="py-[0.3rem] pr-[0.6rem] text-ink-soft">{row.label}</td>
                    <td className={`py-[0.3rem] pr-[0.6rem] text-right ${theirOn ? "text-ink" : "text-ink-mute"}`}>
                      {theirOn
                        ? cell(layerMonthly(providerPrice.lines, row.id), layerEst(providerPrice.lines, row.id))
                        : "$0 — not in this app"}
                    </td>
                    <td className={`py-[0.3rem] text-right ${digiOn && cut ? "text-ink" : "text-ink-mute"}`}>
                      {digiCell}
                    </td>
                  </tr>
                );
              })}
              <tr className="border-t border-hair">
                <td className="py-[0.3rem] pr-[0.6rem] text-ink-soft">Setup · one-time</td>
                <td className="py-[0.3rem] pr-[0.6rem] text-right text-ink">{usd(providerPrice.setup)}</td>
                <td className="py-[0.3rem] text-right text-ink">{usd(sumFor(digiPrice.lines, revealed, false))}</td>
              </tr>
              <tr className="border-t border-hair">
                <td className="py-[0.3rem] pr-[0.6rem] text-ink">Monthly total</td>
                <td className="py-[0.3rem] pr-[0.6rem] text-right text-ink">{usd(providerPrice.monthly)}</td>
                <td className={`py-[0.3rem] text-right text-ink${digiHi}`}>{usd(sumFor(digiPrice.lines, revealed, true))}</td>
              </tr>
            </tbody>
          </table>
          <p className="m-0 mt-[0.6rem] font-mono text-[0.72rem] text-ink-mute">
            ~ marks an estimate; the rest are researched list prices at this app&apos;s preset workload.
            The digi column cuts one row per swap as you scroll.
          </p>
        </div>
      </div>
    </section>
  );
}
