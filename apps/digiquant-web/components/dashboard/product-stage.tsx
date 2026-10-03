"use client";

import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type SyntheticEvent } from "react";
import { Button, Slider } from "@digithings/ui/ui";
import { deskHref } from "@/components/desk/paths";
import { PAGES } from "../../../../clients/digiquant-tui/src/catalog";
import {
  OPEN_BUDGET_MS,
  activateNavLink,
  bindYieldListeners,
  embedLooksDown,
  probeEmbed,
  shouldYieldToUser,
} from "./desk-walk";
import { TerminalScreen } from "./terminal-screen";
import {
  HOSTED_AT,
  HOSTED_COPY,
  HOSTED_TITLE,
  IDLE_RESUME_MS,
  SELF_HOSTED_COPY,
  SELF_HOSTED_TITLE,
  SLIDER_MAX,
  SLIDER_MIN,
  TERMINAL_AT,
  TOUR_CAPTION,
  TOUR_DWELL_MS,
  WEB_EMPTY_COPY,
  deskShellLoaded,
  nextDeskAnchor,
  nextTerminalPath,
  nextWebPath,
  prevTerminalPath,
  stageStatus,
  surfaceFromSlider,
  type StagePhase,
} from "./surface-tour";

const HOME = PAGES[0]?.path ?? "/brief";

function sliderNumber(value: number | readonly number[]): number {
  return typeof value === "number" ? value : (value[0] ?? SLIDER_MIN);
}

/** Self-hosted terminal screens and the hosted web desk. Both stay mounted.
 *  The slider translates one into the frame. A tour advances the visible pages
 *  until the slider or a pointer, wheel, or key inside the view takes over. */
export function ProductStage() {
  const frameRef = useRef<HTMLIFrameElement>(null);
  const sliderRef = useRef(HOSTED_AT);
  const pathRef = useRef(HOME);
  const holdRef = useRef<() => void>(() => {});
  const [slider, setSlider] = useState(HOSTED_AT);
  const [path, setPath] = useState(HOME);
  const [phase, setPhase] = useState<StagePhase>("opening");
  const phaseRef = useRef<StagePhase>("opening");
  const surface = surfaceFromSlider(slider);
  const page = PAGES.find((item) => item.path === path) ?? PAGES[0];

  useEffect(() => {
    const frame = frameRef.current;
    let stopped = false;
    let held = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let idle: ReturnType<typeof setTimeout> | null = null;
    let probeTimer: ReturnType<typeof setTimeout> | null = null;
    let detach: (() => void) | null = null;
    let cancelClick: (() => void) | null = null;
    let bound: Document | null = null;
    const started = Date.now();

    const clearTimer = () => {
      if (timer != null) clearTimeout(timer);
      timer = null;
    };
    const clearIdle = () => {
      if (idle != null) clearTimeout(idle);
      idle = null;
    };

    const publish = (next: StagePhase) => {
      if (phaseRef.current === next) return;
      phaseRef.current = next;
      setPhase(next);
    };

    const arm = (doc: Document) => {
      if (bound === doc) return;
      detach?.();
      bound = doc;
      detach = bindYieldListeners(doc, () => holdRef.current());
    };

    const webPhase = (): StagePhase | null => {
      if (!frame) return "opening";
      const probe = probeEmbed(frame);
      if (probe.kind === "cross-origin") return "live";
      if (probe.kind === "closed") return Date.now() - started > OPEN_BUDGET_MS ? "empty" : "opening";
      const doc = frame.contentDocument;
      if (!doc) return "opening";
      try {
        arm(doc);
      } catch {
        return "live";
      }
      if (deskShellLoaded(doc)) return null;
      if (embedLooksDown(doc)) return "empty";
      return Date.now() - started > OPEN_BUDGET_MS ? "empty" : "opening";
    };

    const publishSurface = () => {
      const showing = surfaceFromSlider(sliderRef.current);
      const blocked = showing === "web" ? webPhase() : null;
      if (blocked === "empty" || blocked === "live") {
        publish(blocked);
        return;
      }
      if (held) {
        publish("yours");
        return;
      }
      if (blocked) {
        publish(blocked);
        return;
      }
      publish("touring");
    };

    const advance = () => {
      if (stopped || held) return;
      const showing = surfaceFromSlider(sliderRef.current);
      if (showing === "terminal") {
        const next = nextTerminalPath(pathRef.current);
        pathRef.current = next;
        setPath(next);
        publish("touring");
        return;
      }
      const blocked = webPhase();
      if (blocked) {
        publish(blocked);
        return;
      }
      const doc = frame?.contentDocument;
      if (!doc) return;
      publish("touring");
      const link = nextDeskAnchor(doc);
      if (link) {
        cancelClick?.();
        cancelClick = activateNavLink(link);
        return;
      }
      let pathname = "/app";
      try {
        pathname = doc.location.pathname;
      } catch {
        return;
      }
      const href = deskHref(nextWebPath(pathname));
      if (pathname.replace(/\/+$/, "") === href.replace(/\/+$/, "")) return;
      try {
        for (const hop of doc.querySelectorAll("a[data-tour-hop]")) hop.remove();
        const hop = doc.createElement("a");
        hop.href = href;
        hop.dataset.tourHop = "1";
        hop.tabIndex = -1;
        hop.setAttribute("aria-hidden", "true");
        doc.body.appendChild(hop);
        cancelClick?.();
        cancelClick = activateNavLink(hop);
      } catch {
        /* The frame already moved. */
      }
    };

    const schedule = () => {
      clearTimer();
      timer = setTimeout(() => {
        advance();
        if (stopped || held || phaseRef.current === "live") return;
        schedule();
      }, TOUR_DWELL_MS);
    };

    const resume = () => {
      if (stopped) return;
      held = false;
      publishSurface();
      schedule();
    };

    const hold = () => {
      if (stopped) return;
      held = true;
      clearTimer();
      cancelClick?.();
      cancelClick = null;
      publishSurface();
      if (phaseRef.current !== "empty" && phaseRef.current !== "live") publish("yours");
      clearIdle();
      idle = setTimeout(resume, IDLE_RESUME_MS);
    };
    holdRef.current = hold;

    const probe = () => {
      if (stopped) return;
      publishSurface();
      probeTimer = setTimeout(probe, 300);
    };

    frame?.addEventListener("load", probe);
    probe();
    schedule();
    return () => {
      stopped = true;
      clearTimer();
      clearIdle();
      if (probeTimer != null) clearTimeout(probeTimer);
      cancelClick?.();
      detach?.();
      frame?.removeEventListener("load", probe);
      holdRef.current = () => {};
    };
  }, []);

  const onSlider = (value: number | readonly number[], details?: { reason?: string }) => {
    const reason = details?.reason;
    if (reason !== "track-press" && reason !== "drag" && reason !== "keyboard") return;
    const next = sliderNumber(value);
    if (next === sliderRef.current) return;
    sliderRef.current = next;
    setSlider(next);
    holdRef.current();
  };

  const choose = (next: string) => {
    pathRef.current = next;
    setPath(next);
    holdRef.current();
  };

  const onViewEvent = (event: SyntheticEvent) => {
    if (shouldYieldToUser(event.nativeEvent)) holdRef.current();
  };

  const onListKey = (event: ReactKeyboardEvent<HTMLElement>) => {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    event.preventDefault();
    choose(event.key === "ArrowDown" ? nextTerminalPath(pathRef.current) : prevTerminalPath(pathRef.current));
  };

  const terminalHidden = slider >= HOSTED_AT;
  const webHidden = slider <= TERMINAL_AT;

  return (
    <div className="flex flex-col gap-3">
      <div className="grid gap-px border border-hair sm:grid-cols-2">
        <Story title={SELF_HOSTED_TITLE} copy={SELF_HOSTED_COPY} on={surface === "terminal"} />
        <Story title={HOSTED_TITLE} copy={HOSTED_COPY} on={surface === "web"} />
      </div>
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-3 font-mono text-[0.62rem] text-ink-mute">
          <span className={surface === "terminal" ? "text-ink" : undefined}>{SELF_HOSTED_TITLE}</span>
          <span className={surface === "web" ? "text-ink" : undefined}>{HOSTED_TITLE}</span>
        </div>
        <Slider
          value={slider}
          min={SLIDER_MIN}
          max={SLIDER_MAX}
          step={1}
          aria-label="Show the self-hosted terminal or the hosted web app"
          onValueChange={onSlider}
        />
        <p className="m-0 flex flex-wrap items-center justify-between gap-2 font-mono text-[0.62rem] text-ink-mute">
          <span>{TOUR_CAPTION}</span>
          <span aria-live="polite">{stageStatus(phase, surface)}</span>
        </p>
      </div>
      <div
        className="h-[min(40rem,calc(100svh-18rem))] min-h-[28rem] overflow-hidden border border-hair bg-surface"
        data-showing={surface}
        onPointerDown={onViewEvent}
        onWheel={onViewEvent}
        onKeyDown={onViewEvent}
      >
        <div
          className="flex h-full w-[200%]"
          style={{ transform: `translateX(-${slider / 2}%)` }}
        >
          <div
            className="h-full w-1/2 min-w-0"
            inert={terminalHidden ? true : undefined}
            aria-hidden={terminalHidden ? true : undefined}
          >
            <TerminalStage
              path={path}
              label={page?.label ?? path}
              warm={phase === "touring" && surface === "terminal"}
              onListKey={onListKey}
              onNavigate={choose}
            />
          </div>
          <div
            className="flex h-full w-1/2 min-w-0 flex-col"
            inert={webHidden ? true : undefined}
            aria-hidden={webHidden ? true : undefined}
          >
            {phase === "empty" && surface === "web" ? (
              <p className="m-0 px-3 py-6 font-mono text-[0.75rem] leading-[1.5] text-ink-mute">{WEB_EMPTY_COPY}</p>
            ) : null}
            <iframe
              ref={frameRef}
              title="Hosted digiquant"
              src="/app"
              loading="eager"
              className={`block min-h-0 w-full flex-1 border-0 bg-surface ${phase === "empty" && surface === "web" ? "hidden" : ""}`}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

function Story({ title, copy, on }: { title: string; copy: string; on: boolean }) {
  return (
    <div className={`px-3 py-3 ${on ? "bg-surface-2" : ""}`}>
      <p className={`m-0 font-mono text-[0.62rem] ${on ? "text-ink" : "text-ink-mute"}`}>{title}</p>
      <p className={`m-0 mt-1 text-[0.8125rem] leading-[1.5] ${on ? "text-ink-soft" : "text-ink-mute"}`}>{copy}</p>
    </div>
  );
}

function TerminalStage({
  path,
  label,
  warm,
  onListKey,
  onNavigate,
}: {
  path: string;
  label: string;
  warm: boolean;
  onListKey: (event: ReactKeyboardEvent<HTMLElement>) => void;
  onNavigate: (path: string) => void;
}) {
  const upcoming = nextTerminalPath(path);
  const layers = warm && upcoming !== path ? [path, upcoming] : [path];
  return (
    <div className="flex h-full min-h-0 flex-col bg-surface font-mono text-ink">
      <header className="flex h-8 shrink-0 items-center justify-between gap-3 border-b border-hair px-2 text-[0.62rem] text-ink-mute">
        <span className="truncate text-ink">
          digiquant · {label} · {path}
        </span>
        <span className="truncate">screens the terminal draws</span>
      </header>
      <div className="flex min-h-0 flex-1">
        <nav aria-label="Terminal pages" className="w-[11rem] shrink-0 overflow-auto border-e border-hair" onKeyDown={onListKey}>
          {PAGES.map((item) => {
            const nested = item.path.split("/").filter(Boolean).length > 1;
            const current = item.path === path;
            return (
              <Button
                key={item.path}
                type="button"
                variant="ghost"
                size="xs"
                aria-current={current ? "page" : undefined}
                className={`h-6 w-full justify-start rounded-none px-2 font-mono text-[0.62rem] font-normal ${nested ? "ps-5" : ""} ${current ? "text-ink" : "text-ink-mute"}`}
                onClick={() => onNavigate(item.path)}
              >
                {item.label}
              </Button>
            );
          })}
        </nav>
        <div className="relative min-h-0 min-w-0 flex-1">
          {layers.map((item) => {
            const active = item === path;
            return (
              <div
                key={item}
                inert={active ? undefined : true}
                aria-hidden={active ? undefined : true}
                className={`absolute inset-0 flex min-h-0 flex-col motion-safe:transition-opacity motion-safe:duration-700 ${active ? "opacity-100" : "pointer-events-none opacity-0"}`}
              >
                <TerminalScreen path={item} />
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
