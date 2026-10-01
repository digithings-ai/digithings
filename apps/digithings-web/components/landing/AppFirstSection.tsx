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

import { architectureEntrance } from "@/components/landing/architectureEntrance";
import { APP_PRESETS } from "@/lib/appPresets";
import {
  DIGI_LAYERS,
  EMAIL_OPTIONS,
  PROVIDER_LAYERS,
  embedDims,
  formatBill,
  menuRate,
  morphSpec,
  providerSpec,
  type Layer,
  type LayerId,
  type LayerOption,
  type StackPick,
} from "@/lib/stackCatalog";
import { emailSwapped, revealedLayers, swappedBoxes } from "@/lib/whyStory";

import { SectionHead } from "./SectionHead";
import { WhyPriceTable } from "./WhyPriceTable";

const HEADLINE =
  "m-0 font-display text-[length:var(--type-section-stand)] font-medium leading-[1.2] tracking-[-0.025em] text-ink";
const LEDE =
  "m-0 max-w-[var(--measure-prose)] text-[length:var(--type-body)] leading-[var(--leading-prose)] text-ink-soft";
const LABEL = "font-mono text-[0.68rem] uppercase tracking-[0.08em] text-ink-mute";
const TAB_BASE =
  "-ms-px flex w-full min-w-0 items-baseline gap-[0.6rem] border border-hair px-[0.95rem] py-[0.7rem] text-start font-mono text-[0.8rem] leading-[1.35] transition-[color,background-color,box-shadow] duration-200 first:ms-0 max-[640px]:px-[0.6rem] max-[640px]:text-[0.74rem]";
const TAB = `${TAB_BASE} bg-bg text-ink-soft hover:bg-surface hover:text-ink`;
const TAB_ON = `${TAB_BASE} relative z-10 border-b-transparent bg-surface text-ink shadow-[inset_0_2px_0_var(--accent)]`;
/** How long the graph's build entrance runs before the class is dropped. */
const BUILD_MS = 2600;
/** Hold the outgoing graph at rest before the next one fades in. */
const LEAVE_MS = 220;

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

type MenuLayer = LayerId | "email";

interface Popover {
  side: "provider" | "digi";
  layer: MenuLayer;
  boxId: string;
  left: number;
  top: number;
  above: boolean;
  maxH: number;
}

const MENU_W = 300;

export function AppFirstSection() {
  const [appId, setAppId] = useState(APP_PRESETS[0].id);
  const preset = APP_PRESETS.find((app) => app.id === appId) ?? APP_PRESETS[0];
  const [picks, setPicks] = useState<Record<string, { provider: StackPick; digi: StackPick }>>(() =>
    Object.fromEntries(
      APP_PRESETS.map((app) => [app.id, { provider: app.providerDefaults, digi: app.digiDefaults }]),
    ),
  );
  const [pop, setPop] = useState<Popover | null>(null);
  const [emailId, setEmailId] = useState("sendgrid");
  const menuRef = useRef<HTMLDivElement>(null);
  const [tourStep, setTourStep] = useState(0);
  const [tourMode, setTourMode] = useState<string>("static");
  /* The graph draws itself the first time the reader scrolls down into the
     band. A refresh or a back navigation that lands inside or below the band
     paints the finished drawing — the pending hide would otherwise leave the
     diagram on screen blank until the first frame scrolled back in. Reduced
     motion is handled in diagrams.css. */
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
  const theirsSpec = providerSpec(effProvider, workload, { ...draw, emailId });
  /* The digithings side is drawn finished from its first step: every box
     already carries its digithings label, and the walk only moves the camera. */
  const lastBeat = preset.leftSteps.length + preset.morphSteps.length - 1;
  const digiSpec = morphSpec(effProvider, effDigi, workload, {
    ...draw,
    replaced: revealedLayers(preset, lastBeat),
    boxes: swappedBoxes(preset, lastBeat),
    email: emailSwapped(preset, lastBeat),
    emailId,
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
        emailId={emailId}
      />
    );

  useEffect(() => {
    if (!pop) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setPop(null);
    };
    /* Any scroll that moves the page or the graph dismisses the menu. A
       scroll inside the menu itself (a long model list) does not. */
    const onScroll = (event: Event) => {
      const target = event.target;
      if (target instanceof Node && menuRef.current?.contains(target)) return;
      setPop(null);
    };
    const onPointer = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (menuRef.current?.contains(target)) return;
      if (target instanceof Element && target.closest(`[id="arch-service-${pop.boxId}"]`)) return;
      setPop(null);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("scroll", onScroll, true);
    document.addEventListener("pointerdown", onPointer);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", onScroll, true);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, [pop]);

  useEffect(() => {
    if (build.state !== "pending") return;
    const section = sectionRef.current;
    if (!section) return;

    const finish = () =>
      setBuild((b) => (b.state === "pending" ? { state: "done", run: b.run } : b));
    const play = () =>
      setBuild((b) => (b.state === "pending" ? { state: "run", run: b.run + 1 } : b));

    let io: IntersectionObserver | undefined;
    let raf = 0;
    let frames = 0;

    const arm = () => {
      if (raf) cancelAnimationFrame(raf);
      raf = 0;
      io?.disconnect();
      io = undefined;
      const rect = section.getBoundingClientRect();
      const gate = architectureEntrance(rect, window.innerHeight);
      if (gate === "wait" && rect.height <= 0 && frames < 8) {
        frames += 1;
        raf = requestAnimationFrame(arm);
        return;
      }
      if (gate === "done") {
        finish();
        return;
      }
      io = new IntersectionObserver(([entry]) => {
        if (!entry?.isIntersecting) return;
        io?.disconnect();
        play();
      });
      io.observe(section);
    };

    arm();
    const onPageShow = () => arm();
    window.addEventListener("pageshow", onPageShow);
    return () => {
      if (raf) cancelAnimationFrame(raf);
      io?.disconnect();
      window.removeEventListener("pageshow", onPageShow);
    };
    /* tourMode swaps the static stack for the camera after mount. Re-arm so
       a band that is already on screen is never left hidden. */
  }, [build.state, tourMode]);

  useEffect(() => {
    if (build.state !== "run") return;
    const t = window.setTimeout(() => setBuild((b) => ({ ...b, state: "done" })), BUILD_MS);
    return () => window.clearTimeout(t);
  }, [build.state, build.run]);

  /* A switch keeps the tour mounted and the walk where it is. Remounting
     paints one static frame, and rewinding the walk slides the tab strip
     out from under the header. The grid fades out, the specs swap while it
     is invisible, then the same grid fades back in on the same beat. */
  const selectApp = (id: string) => {
    if (id === shownId) return;
    setPop(null);
    if (leaveTimer.current !== null) window.clearTimeout(leaveTimer.current);
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      setAppId(id);
      setNextId(null);
      return;
    }
    setNextId(id);
    leaveTimer.current = window.setTimeout(() => {
      leaveTimer.current = null;
      setAppId(id);
      window.requestAnimationFrame(() => setNextId(null));
    }, LEAVE_MS);
  };

  const setPick = (side: "provider" | "digi", layer: LayerId, option: string) =>
    setPicks((prev) => ({
      ...prev,
      [preset.id]: { ...prev[preset.id], [side]: { ...prev[preset.id][side], [layer]: option } },
    }));

  const openMenu = (side: "provider" | "digi", layer: MenuLayer, node: Element, boxId: string) => {
    const host = sectionRef.current;
    if (!host) return;
    const nodeRect = node.getBoundingClientRect();
    const hostRect = host.getBoundingClientRect();
    let left = nodeRect.left - hostRect.left;
    left = Math.max(8, Math.min(left, hostRect.width - MENU_W - 8));
    const spaceBelow = window.innerHeight - nodeRect.bottom - 16;
    const spaceAbove = nodeRect.top - 16;
    const above = spaceBelow < 200 && spaceAbove > spaceBelow;
    const top = above ? nodeRect.top - hostRect.top : nodeRect.bottom - hostRect.top + 6;
    const maxH = Math.max(140, Math.min(352, above ? spaceAbove - 8 : spaceBelow - 8));
    setPop({ side, layer, boxId, left, top, above, maxH });
  };

  const onStageClick = (event: MouseEvent<HTMLElement>) => {
    if (menuRef.current?.contains(event.target as Node)) return;
    const node = (event.target as Element).closest?.('[id^="arch-service-"]');
    if (!node) return;
    const boxId = node.id.replace("arch-service-", "");
    if (boxId === "email") {
      if (onDigiSide) return;
      if (pop?.boxId === "email") {
        setPop(null);
        return;
      }
      openMenu("provider", "email", node, boxId);
      return;
    }
    const layer = PROVIDER_LAYER_BY_BOX[boxId];
    if (!layer) return;
    const side = onDigiSide ? "digi" : "provider";
    if (pop?.boxId === boxId && pop.side === side) {
      setPop(null);
      return;
    }
    openMenu(side, layer, node, boxId);
  };

  const popLayer =
    pop && pop.layer !== "email"
      ? LAYERS_BY_SIDE[pop.side].find((layer) => layer.id === pop.layer)
      : undefined;
  const popOptions: LayerOption[] | undefined =
    pop?.layer === "email" ? EMAIL_OPTIONS : popLayer?.options;
  const popTitle = pop?.layer === "email" ? "Email" : popLayer?.label;
  const popSelected =
    pop?.layer === "email"
      ? emailId
      : pop
        ? (pop.side === "provider" ? effProvider : effDigi)[pop.layer]
        : "";

  return (
    <section
      ref={sectionRef}
      aria-label="Their stack or the digithings stack"
      className={`whyx relative${build.state === "pending" ? " arch-build-pending" : ""}${build.state === "run" ? " arch-build" : ""}${nextId ? " whyx--leaving" : ""}`}
      onClick={onStageClick}
    >
      <ArchitectureTour
        variant="camera"
        cameraFill={0.55}
        cameraMaxScale={1.65}
        cameraCover
        fitFrame
        onStepChange={setTourStep}
        onModeChange={setTourMode}
        header={
          <div className="flex w-full min-w-0 flex-col gap-[0.7rem]">
            <SectionHead id="why" />
            <h2 className={HEADLINE}>
              <span className="why-rent">Anyones AI stack,</span>{" "}
              <span className="why-own">or a digithings stack</span>
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
                    /* Mouse focus scrolls the sticky pin and the tab strip jumps.
                       Keyboard focus still lands here. */
                    onMouseDown={(event) => event.preventDefault()}
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

      {pop && popOptions && popTitle ? (
        <div
          ref={menuRef}
          role="listbox"
          aria-label={`${popTitle} options`}
          className="absolute z-30 flex w-[18.75rem] flex-col overflow-y-auto border border-hair bg-surface p-[0.35rem] shadow-[0_12px_32px_-20px_rgba(0,0,0,0.45)]"
          style={{
            left: pop.left,
            top: pop.top,
            maxHeight: pop.maxH,
            transform: pop.above ? "translateY(calc(-100% - 6px))" : undefined,
          }}
          onClick={(event) => event.stopPropagation()}
        >
          <div className="sticky top-0 z-10 bg-surface px-[0.7rem] pt-[0.4rem] pb-[0.45rem]">
            <span className={LABEL}>{popTitle}</span>
            <span className="mt-[0.15rem] block font-mono text-[0.62rem] leading-[1.3] tracking-normal text-ink-mute normal-case">
              per month, this workload
            </span>
          </div>
          {popOptions.map((option) => {
            const rate = menuRate(
              pop.layer,
              option.id,
              workload,
              embedDims((pop.side === "provider" ? effProvider : effDigi).embeddings),
            );
            const selected = popSelected === option.id;
            return (
              <button
                key={option.id}
                type="button"
                role="option"
                aria-selected={selected}
                className={`flex w-full items-baseline justify-between gap-[0.75rem] px-[0.7rem] py-[0.5rem] text-start font-mono text-[0.82rem] leading-[1.35] ${
                  selected
                    ? "bg-bg text-ink shadow-[inset_0_0_0_1px_var(--accent)]"
                    : "text-ink-soft hover:bg-bg hover:text-ink"
                }`}
                onClick={() => {
                  if (pop.layer === "email") setEmailId(option.id);
                  else setPick(pop.side, pop.layer, option.id);
                  setPop(null);
                }}
              >
                <span className="min-w-0 truncate">{option.label}</span>
                <span className={`shrink-0 tabular-nums ${selected ? "text-ink" : "text-ink-mute"}`}>
                  {formatBill(rate.amount, rate.estimate)}
                </span>
              </button>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}
