/**
 * The `#why` band (Refs #4429).
 *
 * Scroll flow is version A of the why-copy review: one rented walk, then
 * that side slides left and the digithings side slides in, camera on the
 * second side. The three apps stay in the pinned view, inside the page
 * column, so the walk sits between the section rules. Click a priced box
 * to reconfigure that layer.
 */

"use client";

import { useEffect, useRef, useState, type MouseEvent } from "react";
import { ArchitectureTour } from "@digithings/ui";

import { APP_PRESETS } from "@/lib/appPresets";
import {
  DIGI_LAYERS,
  PROVIDER_LAYERS,
  morphSpec,
  providerSpec,
  type Layer,
  type LayerId,
  type StackPick,
} from "@/lib/stackCatalog";
import { emailSwapped, revealedLayers, swappedBoxes } from "@/lib/whyStory";

import { WhyPriceTable } from "./WhyPriceTable";

const HEADLINE =
  "m-0 font-mono text-[length:var(--type-section-stand)] font-medium leading-[1.2] tracking-[-0.025em] text-ink";
const LEDE =
  "m-0 max-w-[var(--measure-prose)] text-[length:var(--type-body)] leading-[var(--leading-prose)] text-ink-soft";
const LABEL = "font-mono text-[0.68rem] uppercase tracking-[0.08em] text-ink-mute";
const TAB_BASE =
  "-ms-px flex w-full min-w-0 items-baseline gap-[0.6rem] border border-hair px-[0.95rem] py-[0.7rem] text-start font-mono text-[0.8rem] leading-[1.35] transition-[color,background-color,box-shadow] duration-200 first:ms-0 max-[640px]:px-[0.6rem] max-[640px]:text-[0.74rem]";
const TAB = `${TAB_BASE} bg-bg text-ink-soft hover:bg-surface hover:text-ink`;
const TAB_ON = `${TAB_BASE} relative z-10 border-b-transparent bg-surface text-ink shadow-[inset_0_2px_0_var(--accent)]`;
/** How long the graph's build entrance runs before the class is dropped. */
const BUILD_MS = 2600;
/** The outgoing app's fade before the new one mounts (matches globals.css). */
const LEAVE_MS = 200;

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

interface Popover {
  side: "provider" | "digi";
  layer: LayerId;
  x: number;
  y: number;
}

export function AppFirstSection() {
  const [appId, setAppId] = useState(APP_PRESETS[0].id);
  const preset = APP_PRESETS.find((app) => app.id === appId) ?? APP_PRESETS[0];
  const [picks, setPicks] = useState<Record<string, { provider: StackPick; digi: StackPick }>>(() =>
    Object.fromEntries(
      APP_PRESETS.map((app) => [app.id, { provider: app.providerDefaults, digi: app.digiDefaults }]),
    ),
  );
  const [pop, setPop] = useState<Popover | null>(null);
  const [tourStep, setTourStep] = useState(0);
  const [tourMode, setTourMode] = useState<string>("static");
  /* The graph draws itself the first time it scrolls into view and again on
     every app switch; `run` is bumped per build so a quick second switch
     restarts the timer. Reduced motion is handled in diagrams.css: the
     pending hide and the build keyframes are both switched off there. */
  const [build, setBuild] = useState<{ state: "pending" | "run" | "done"; run: number }>({
    state: "pending",
    run: 0,
  });
  const sectionRef = useRef<HTMLElement>(null);
  /* The app being switched to while the current one fades out: the tab and
     its description answer the click at once, the graph follows. */
  const [nextId, setNextId] = useState<string | null>(null);
  const leaveTimer = useRef<number | null>(null);
  useEffect(
    () => () => {
      if (leaveTimer.current !== null) window.clearTimeout(leaveTimer.current);
    },
    [],
  );
  const shownId = nextId ?? preset.id;

  const pick = picks[preset.id];
  const workload = preset.workload;
  const effProvider = { ...pick.provider, ...preset.fixedLayers };
  const effDigi = { ...pick.digi, ...preset.fixedLayers };
  const draw = {
    appLabel: preset.providerApp,
    sourcesLabel: preset.providerSources,
    topology: preset.topology,
  };
  const theirsSpec = providerSpec(effProvider, workload, draw);
  /* The digithings side is drawn finished from its first step: every box
     already carries its digithings label, and the walk only moves the camera. */
  const lastBeat = preset.leftSteps.length + preset.morphSteps.length - 1;
  const digiSpec = morphSpec(effProvider, effDigi, workload, {
    ...draw,
    replaced: revealedLayers(preset, lastBeat),
    boxes: swappedBoxes(preset, lastBeat),
    email: emailSwapped(preset, lastBeat),
    owned: true,
  });
  const onDigiSide = tourStep >= preset.leftSteps.length;
  /* One table per camera side (only one side shows at a time); the static
     stack would print it twice, so it stays a camera-only aside. */
  const priceAside =
    tourMode === "static" ? undefined : (
      <WhyPriceTable
        provider={effProvider}
        digi={effDigi}
        workload={workload}
        topology={preset.topology}
        replaced={revealedLayers(preset, tourStep)}
      />
    );

  useEffect(() => {
    if (!pop) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setPop(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pop]);

  useEffect(() => {
    if (build.state !== "pending") return;
    const frame = sectionRef.current?.querySelector(".arch-tour__frame, .arch-figure");
    if (!frame) return;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (!entry?.isIntersecting) return;
        io.disconnect();
        setBuild((b) => ({ state: "run", run: b.run + 1 }));
      },
      { rootMargin: "0px 0px -20% 0px" },
    );
    io.observe(frame);
    return () => io.disconnect();
    /* The tour swaps its static render for the camera one after mount, which
       replaces the frame node; re-observe so the build is never left pending. */
  }, [build.state, tourMode]);

  useEffect(() => {
    if (build.state !== "run") return;
    const t = window.setTimeout(() => setBuild((b) => ({ ...b, state: "done" })), BUILD_MS);
    return () => window.clearTimeout(t);
  }, [build.state, build.run]);

  /* A switch is a crossfade, not a rebuild: the old app fades out, the new
     one mounts (and the walk rewinds) while nothing is visible, then fades
     in whole. The box-by-box build is kept for the graph's first entrance. */
  const selectApp = (id: string) => {
    if (id === shownId) return;
    setPop(null);
    if (leaveTimer.current !== null) window.clearTimeout(leaveTimer.current);
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      swapApp(id);
      return;
    }
    setNextId(id);
    leaveTimer.current = window.setTimeout(() => {
      leaveTimer.current = null;
      swapApp(id);
    }, LEAVE_MS);
  };

  const swapApp = (id: string) => {
    const track = sectionRef.current?.querySelector<HTMLElement>(".arch-tour__track");
    const pin = track?.querySelector<HTMLElement>(".arch-tour__pin");
    setAppId(id);
    setNextId(null);
    setTourStep(0);
    setBuild((b) => ({ state: "done", run: b.run }));
    if (!track || !pin) {
      document.getElementById("why")?.scrollIntoView({ behavior: "auto", block: "start" });
      return;
    }
    /* Back to the new app's opening beat with the pin still held, rather than
       parking above the band where the graph runs off the viewport. */
    const start =
      track.getBoundingClientRect().top + window.scrollY - Number.parseFloat(getComputedStyle(pin).top);
    if (window.scrollY > start) window.scrollTo({ top: Math.round(start), behavior: "auto" });
  };

  const setPick = (side: "provider" | "digi", layer: LayerId, option: string) =>
    setPicks((prev) => ({
      ...prev,
      [preset.id]: { ...prev[preset.id], [side]: { ...prev[preset.id][side], [layer]: option } },
    }));

  const onStageClick = (event: MouseEvent<HTMLDivElement>) => {
    const node = (event.target as Element).closest?.('[id^="arch-service-"]');
    if (!node) return;
    const boxId = node.id.replace("arch-service-", "");
    const layer = PROVIDER_LAYER_BY_BOX[boxId];
    if (!layer) return;
    const side = onDigiSide ? "digi" : "provider";
    setPop({
      side,
      layer,
      x: Math.min(event.clientX, window.innerWidth - 280),
      y: Math.min(event.clientY + 12, window.innerHeight - 320),
    });
  };

  const popLayer = pop ? LAYERS_BY_SIDE[pop.side].find((layer) => layer.id === pop.layer) : undefined;
  const popPick = pop ? (pop.side === "provider" ? effProvider : effDigi) : pick.provider;

  return (
    <section
      ref={sectionRef}
      aria-label="Their stack or the digithings stack"
      className={`whyx${build.state === "pending" ? " arch-build-pending" : ""}${build.state === "run" ? " arch-build" : ""}${nextId ? " whyx--leaving" : ""}`}
      onClick={onStageClick}
    >
      <ArchitectureTour
        key={preset.id}
        variant="camera"
        cameraFill={0.55}
        cameraMaxScale={1.65}
        cameraCover
        fitFrame
        onStepChange={setTourStep}
        onModeChange={setTourMode}
        header={
          <div className="flex w-full min-w-0 flex-col gap-[0.7rem]">
            <h2 className={HEADLINE}>
              <span className="why-rent">Their AI stack,</span>{" "}
              <span className="why-own">or one you compose.</span>
            </h2>
            {tourMode === "static" ? (
              <p className={LEDE}>
                Same app, two infrastructures: theirs first, then the digithings stack.
              </p>
            ) : (
              <p className={`whyx__how ${LEDE}`}>
                Same app, two infrastructures. Scroll the walk. Their stack slides off to the
                left, and the digithings stack slides in. Click a box to change that layer.
              </p>
            )}
            <div className="whyx__apps mt-[0.8rem] flex min-w-0 flex-col">
              <div className="grid grid-cols-3 gap-0" role="tablist" aria-label="Application">
                {APP_PRESETS.map((app, i) => (
                  <button
                    key={app.id}
                    type="button"
                    role="tab"
                    aria-selected={app.id === shownId}
                    className={app.id === shownId ? TAB_ON : TAB}
                    onClick={() => selectApp(app.id)}
                  >
                    <span
                      className="text-[0.68rem] text-ink-mute max-[640px]:hidden"
                      aria-hidden="true"
                    >
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <span className="min-[641px]:truncate">{app.tab}</span>
                  </button>
                ))}
              </div>
              {/* Every app's description sits in the same cell, only the
                  selected one visible, so the strip is always as tall as the
                  longest and the graph box below never changes size. */}
              <div className="grid border-x border-hair bg-surface px-[0.95rem] pt-[0.75rem] pb-[0.6rem]">
                {APP_PRESETS.map((app) => (
                  <p
                    key={app.id}
                    aria-hidden={app.id !== shownId}
                    className={`col-start-1 row-start-1 m-0 text-[0.9rem] leading-[1.65] text-ink-soft transition-opacity duration-300 ${
                      app.id === shownId ? "opacity-100" : "invisible opacity-0"
                    }`}
                  >
                    {app.subhead}
                  </p>
                ))}
              </div>
            </div>
          </div>
        }
        sides={[
          {
            spec: theirsSpec,
            steps: preset.leftSteps,
            tag: "their stack",
            rail: "end",
            caption: preset.providerCaption,
            aside: priceAside,
          },
          {
            spec: digiSpec,
            steps: preset.morphSteps,
            tag: "digithings stack",
            caption: preset.morphCaption,
            aside: priceAside,
          },
        ]}
      />

      {pop && popLayer ? (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setPop(null)} aria-hidden="true" />
          <div
            role="listbox"
            aria-label={`${popLayer.label} options`}
            className="fixed z-50 flex w-[16rem] flex-col gap-[0.25rem] border border-hair bg-surface p-[0.7rem] shadow-[0_18px_50px_-20px_rgba(0,0,0,0.6)]"
            /* Physical on purpose: placed from the pointer's clientX/clientY. */
            style={{ left: Math.max(pop.x, 8), top: Math.max(pop.y, 8) }}
          >
            <span className={LABEL}>{popLayer.label}</span>
            {popLayer.options.map((option, i) => (
              <button
                key={option.id}
                type="button"
                role="option"
                aria-selected={popPick[pop.layer] === option.id}
                autoFocus={i === 0}
                className={`px-[0.6rem] py-[0.5rem] text-start font-mono text-[0.8rem] ${
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
    </section>
  );
}
