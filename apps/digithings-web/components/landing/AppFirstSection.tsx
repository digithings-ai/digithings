/**
 * The `#why` band.
 *
 * Three example apps. Each one shows its digithings flow as a terminal
 * schematic: drawn in full, with presentational motion only. Not a recorded run.
 */

"use client";

import { useState } from "react";
import { TerminalSchematic } from "@digithings/ui";

import { APP_FLOWS } from "@/lib/appFlows";
import { APP_PRESETS } from "@/lib/appPresets";
import { revealedLayers } from "@/lib/whyStory";

import { WhyPriceTable } from "./WhyPriceTable";

const HEADLINE =
  "m-0 font-display text-[length:var(--type-section-stand)] font-medium leading-[1.2] tracking-[-0.025em] text-ink";
const LEDE =
  "m-0 max-w-[var(--measure-prose)] text-[length:var(--type-body)] leading-[var(--leading-prose)] text-ink-soft";
const TAB_BASE =
  "-ms-px flex w-full min-w-0 items-baseline gap-[0.6rem] border border-hair px-[0.95rem] py-[0.7rem] text-start font-mono text-[0.8rem] leading-[1.35] transition-[color,background-color,box-shadow] duration-200 first:ms-0 max-[640px]:px-[0.6rem] max-[640px]:text-[0.74rem]";
const TAB = `${TAB_BASE} bg-bg text-ink-soft hover:bg-surface hover:text-ink`;
const TAB_ON = `${TAB_BASE} relative z-10 border-b-transparent bg-surface text-ink shadow-[inset_0_2px_0_var(--accent)]`;

export function AppFirstSection() {
  const [appId, setAppId] = useState(APP_PRESETS[0].id);
  const preset = APP_PRESETS.find((app) => app.id === appId) ?? APP_PRESETS[0];
  const flow = APP_FLOWS[preset.id] ?? APP_FLOWS.rag;
  const lastBeat = preset.leftSteps.length + preset.morphSteps.length - 1;

  return (
    <section aria-label="Three example apps on the digithings stack" className="whyx relative">
      <div className="flex w-full min-w-0 flex-col gap-[0.7rem]">
        <h2 className={HEADLINE}>
          <span className="why-rent">Anyone&apos;s AI stack,</span>{" "}
          <span className="why-own">or a digithings stack</span>
        </h2>
        <p className={LEDE}>
          The digithings flow for each example. The schematic is presentational motion, not a
          recorded run. The table is the monthly comparison for this workload.
        </p>
        <div className="whyx__apps mt-[0.8rem] flex min-w-0 flex-col">
          <div className="grid grid-cols-3 gap-0" role="tablist" aria-label="Application">
            {APP_PRESETS.map((app, i) => (
              <button
                key={app.id}
                type="button"
                role="tab"
                aria-selected={app.id === preset.id}
                className={app.id === preset.id ? TAB_ON : TAB}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => setAppId(app.id)}
              >
                <span className="text-[0.68rem] text-ink-mute max-[640px]:hidden" aria-hidden="true">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span className="min-[641px]:truncate">{app.tab}</span>
              </button>
            ))}
          </div>
          <div className="grid border-x border-hair bg-surface px-[0.95rem] pt-[0.75rem] pb-[0.6rem]">
            {APP_PRESETS.map((app) => (
              <p
                key={app.id}
                aria-hidden={app.id !== preset.id}
                className={`col-start-1 row-start-1 m-0 text-[0.9rem] leading-[1.65] text-ink-soft ${
                  app.id === preset.id ? "" : "invisible"
                }`}
              >
                {app.subhead}
              </p>
            ))}
          </div>
        </div>
        <TerminalSchematic {...flow} />
        <WhyPriceTable
          provider={preset.providerDefaults}
          digi={preset.digiDefaults}
          workload={preset.workload}
          topology={preset.topology}
          replaced={revealedLayers(preset, lastBeat)}
        />
      </div>
    </section>
  );
}
