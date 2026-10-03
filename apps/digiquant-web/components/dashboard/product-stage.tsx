"use client";

import { useEffect, useRef, useState, type CSSProperties, type KeyboardEvent as ReactKeyboardEvent, type PointerEvent as ReactPointerEvent, type SyntheticEvent } from "react";
import { Button } from "@digithings/ui/ui";
import { deskHref } from "@/components/desk/paths";
import { publicCatalogPages } from "@/components/desk/public-surface";
import {
  OPEN_BUDGET_MS,
  bindYieldListeners,
  embedLooksDown,
  probeEmbed,
  shouldYieldToUser,
} from "./desk-walk";
import { TerminalScreen } from "./terminal-screen";
import {
  HOSTED_COPY,
  HOSTED_TITLE,
  IDLE_RESUME_MS,
  PAGE_FADE_MS,
  SELF_HOSTED_COPY,
  SELF_HOSTED_TITLE,
  SPLIT_MAX,
  SPLIT_MIN,
  TOUR_DWELL_MS,
  WEB_EMPTY_COPY,
  clampSplit,
  deskShellLoaded,
  nextTerminalPath,
  paneLayers,
  prevTerminalPath,
  splitFromPointer,
  widerSide,
  type StagePhase,
} from "./surface-tour";

const PAGES = publicCatalogPages();
const HOME = PAGES[0]?.path ?? "/brief";
const LAYER = "absolute inset-0";
const PANE_MOTION = `
@keyframes dq-desk-in { from { opacity: 0; transform: translateX(1rem); } to { opacity: 1; transform: none; } }
@keyframes dq-desk-out { from { opacity: 1; transform: none; } to { opacity: 0; transform: translateX(-1rem); } }
@media (prefers-reduced-motion: reduce) {
  @keyframes dq-desk-in { from, to { opacity: 1; transform: none; } }
  @keyframes dq-desk-out { from, to { opacity: 0; transform: none; } }
}
`;

function frameSrc(path: string): string {
  return path === "/brief" ? "/app" : deskHref(path);
}

function layerStyle(item: string, shown: string, leaving: string | null): CSSProperties | undefined {
  if (item === leaving) return { animation: `dq-desk-out ${PAGE_FADE_MS}ms ease-out forwards` };
  if (item === shown && leaving) return { animation: `dq-desk-in ${PAGE_FADE_MS}ms ease-out both` };
  if (item === shown) return undefined;
  return { opacity: 0 };
}

/** Iframes keep a 300×150 user-agent size unless height and width are set. */
function frameBox(item: string, shown: string, leaving: string | null): CSSProperties {
  return { width: "100%", height: "100%", ...layerStyle(item, shown, leaving) };
}

/** Self-hosted terminal and the hosted web desk, side by side.
 *  Both stay visible and tour the same page. The gap changes the width.
 *  A pointer, wheel, or key inside a frame pauses the tour. */
export function ProductStage() {
  const stageRef = useRef<HTMLDivElement>(null);
  const gapRef = useRef<HTMLButtonElement>(null);
  const frames = useRef(new Map<string, HTMLIFrameElement>());
  const pathRef = useRef(HOME);
  const holdRef = useRef<() => void>(() => {});
  const [path, setPath] = useState(HOME);
  const [shown, setShown] = useState(HOME);
  const [leaving, setLeaving] = useState<string | null>(null);
  const [share, setShare] = useState(0.5);
  const [phase, setPhase] = useState<StagePhase>("opening");
  const phaseRef = useRef<StagePhase>("opening");
  if (path !== shown) {
    setLeaving(shown);
    setShown(path);
  }
  const lead = widerSide(share);
  const preload = phase === "touring" && path === shown ? nextTerminalPath(path) : null;
  const layers = paneLayers(shown, path, leaving, preload);
  const pageLabel = (item: string) => PAGES.find((page) => page.path === item)?.label ?? item;

  useEffect(() => {
    if (!leaving) return;
    const timer = setTimeout(() => setLeaving(null), PAGE_FADE_MS);
    return () => clearTimeout(timer);
  }, [leaving]);

  const go = (next: string, user: boolean) => {
    if (next === pathRef.current) return;
    pathRef.current = next;
    setPath(next);
    if (user) holdRef.current();
  };

  useEffect(() => {
    let stopped = false;
    let held = false;
    let primed = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let idle: ReturnType<typeof setTimeout> | null = null;
    let probeTimer: ReturnType<typeof setTimeout> | null = null;
    let detaches: (() => void)[] = [];
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

    const activeFrame = () => {
      const node = frames.current.get(pathRef.current);
      return node && node.isConnected ? node : null;
    };

    const armAll = () => {
      for (const off of detaches) off();
      detaches = [];
      for (const frame of frames.current.values()) {
        if (!frame.isConnected) continue;
        const probe = probeEmbed(frame);
        if (probe.kind !== "scriptable") continue;
        const doc = frame.contentDocument;
        if (!doc) continue;
        try {
          detaches.push(bindYieldListeners(doc, () => holdRef.current()));
        } catch {
          /* The frame is opaque. */
        }
      }
    };

    const webBlocked = (): StagePhase | null => {
      const frame = activeFrame();
      if (!frame) return "opening";
      const probe = probeEmbed(frame);
      if (probe.kind === "cross-origin") return "live";
      if (probe.kind === "closed") return Date.now() - started > OPEN_BUDGET_MS ? "empty" : "opening";
      const doc = frame.contentDocument;
      if (!doc) return "opening";
      armAll();
      if (deskShellLoaded(doc)) return null;
      if (embedLooksDown(doc)) return "empty";
      return Date.now() - started > OPEN_BUDGET_MS ? "empty" : "opening";
    };

    const schedule = () => {
      clearTimer();
      timer = setTimeout(() => {
        advance();
        if (stopped || held) return;
        schedule();
      }, TOUR_DWELL_MS);
    };

    const prime = () => {
      if (primed || held || stopped) return;
      primed = true;
      schedule();
    };

    const publishSurface = () => {
      const blocked = webBlocked();
      if (blocked === "empty" || blocked === "live") {
        publish(blocked);
        prime();
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
      prime();
    };

    const advance = () => {
      if (stopped || held) return;
      const blocked = webBlocked();
      if (blocked === "opening") return;
      const next = nextTerminalPath(pathRef.current);
      pathRef.current = next;
      setPath(next);
      if (blocked === "empty" || blocked === "live") {
        publish(blocked);
        return;
      }
      publish("touring");
    };

    const resume = () => {
      if (stopped) return;
      held = false;
      publishSurface();
      if (primed) schedule();
    };

    const hold = () => {
      if (stopped) return;
      held = true;
      clearTimer();
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

    probe();
    return () => {
      stopped = true;
      clearTimer();
      clearIdle();
      if (probeTimer != null) clearTimeout(probeTimer);
      for (const off of detaches) off();
      holdRef.current = () => {};
    };
  }, []);

  const onViewEvent = (event: SyntheticEvent) => {
    if (shouldYieldToUser(event.nativeEvent)) holdRef.current();
  };

  const onListKey = (event: ReactKeyboardEvent<HTMLElement>) => {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    event.preventDefault();
    go(event.key === "ArrowDown" ? nextTerminalPath(pathRef.current) : prevTerminalPath(pathRef.current), true);
  };

  const resizeTo = (clientX: number) => {
    const stage = stageRef.current;
    if (!stage) return;
    const rect = stage.getBoundingClientRect();
    const gap = gapRef.current?.getBoundingClientRect().width ?? 0;
    setShare(splitFromPointer(clientX, rect.left, rect.width, gap));
  };

  const onGapDown = (event: ReactPointerEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    resizeTo(event.clientX);
  };

  const onGapMove = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (!event.currentTarget.hasPointerCapture(event.pointerId)) return;
    resizeTo(event.clientX);
  };

  const onGapKey = (event: ReactKeyboardEvent<HTMLButtonElement>) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    event.stopPropagation();
    const step = event.key === "ArrowRight" ? 0.06 : -0.06;
    setShare((value) => clampSplit(value + step));
  };

  const terminalWidth = `calc((100% - 1.5rem) * ${share})`;
  const webWidth = `calc((100% - 1.5rem) * ${1 - share})`;

  return (
    <div className="flex flex-col gap-2">
      <div className="grid gap-px border border-hair sm:grid-cols-2">
        <Story title={SELF_HOSTED_TITLE} copy={SELF_HOSTED_COPY} emphasis={lead === "terminal"} />
        <Story title={HOSTED_TITLE} copy={HOSTED_COPY} emphasis={lead === "web"} />
      </div>
      <style>{PANE_MOTION}</style>
      <div
        ref={stageRef}
        className="flex h-[min(40rem,calc(100svh-18rem))] min-h-[28rem]"
        data-wider={lead}
      >
        <div
          className="relative h-full min-w-0 overflow-hidden border border-hair bg-surface"
          style={{ width: terminalWidth }}
          data-pane="terminal"
          data-page={path}
          onPointerDown={onViewEvent}
          onWheel={onViewEvent}
          onKeyDown={onViewEvent}
        >
          {layers.map((item) => {
            const open = item === shown;
            return (
              <div
                key={item}
                inert={open ? undefined : true}
                aria-hidden={open ? undefined : true}
                className={`${LAYER} ${open ? "" : "pointer-events-none"}`}
                style={layerStyle(item, shown, leaving)}
              >
                <TerminalStage
                  path={item}
                  label={pageLabel(item)}
                  onListKey={onListKey}
                  onNavigate={(next) => go(next, true)}
                />
              </div>
            );
          })}
        </div>
        <Button
          ref={gapRef}
          type="button"
          variant="ghost"
          role="separator"
          aria-orientation="vertical"
          aria-valuemin={Math.round(SPLIT_MIN * 100)}
          aria-valuemax={Math.round(SPLIT_MAX * 100)}
          aria-valuenow={Math.round(share * 100)}
          aria-label="Give more width to the terminal or the hosted desk"
          className="h-auto w-6 shrink-0 self-stretch rounded-none border-0 bg-transparent px-0 hover:bg-transparent active:translate-y-0"
          onPointerDown={onGapDown}
          onPointerMove={onGapMove}
          onKeyDown={onGapKey}
        />
        <div
          className="relative h-full min-w-0 overflow-hidden border border-hair bg-surface"
          style={{ width: webWidth }}
          data-pane="web"
          data-page={path}
          onPointerDown={onViewEvent}
          onWheel={onViewEvent}
          onKeyDown={onViewEvent}
        >
          {phase === "empty" ? (
            <p className="relative z-10 m-0 px-3 py-6 font-mono text-[0.75rem] leading-[1.5] text-ink-mute">{WEB_EMPTY_COPY}</p>
          ) : null}
          {layers.map((item) => {
            const open = item === shown && phase !== "empty";
            return (
              <iframe
                key={item}
                ref={(node) => {
                  if (node) frames.current.set(item, node);
                  else frames.current.delete(item);
                }}
                title="Hosted digiquant"
                src={frameSrc(item)}
                loading="eager"
                data-desk-path={item}
                inert={open ? undefined : true}
                aria-hidden={open ? undefined : true}
                className={`block h-full w-full border-0 bg-surface ${LAYER} ${open ? "" : "pointer-events-none"} ${phase === "empty" ? "invisible" : ""}`}
                style={frameBox(item, shown, leaving)}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}

function Story({ title, copy, emphasis }: { title: string; copy: string; emphasis: boolean }) {
  return (
    <div className={`px-3 py-2.5 ${emphasis ? "bg-surface-2" : ""}`}>
      <p className="m-0 font-mono text-[0.6875rem] tracking-[0.04em] text-ink">{title}</p>
      <p className="m-0 mt-1 text-[0.8125rem] leading-[1.55] text-ink-soft">{copy}</p>
    </div>
  );
}

function TerminalStage({
  path,
  label,
  onListKey,
  onNavigate,
}: {
  path: string;
  label: string;
  onListKey: (event: ReactKeyboardEvent<HTMLElement>) => void;
  onNavigate: (path: string) => void;
}) {
  return (
    <div className="flex h-full min-h-0 flex-col bg-surface font-mono text-ink">
      <header className="flex h-8 shrink-0 items-center justify-between gap-3 border-b border-hair px-2.5 font-mono text-[0.6875rem] tracking-[0.04em] text-ink-mute">
        <span className="truncate text-ink">
          digiquant · {label} · {path}
        </span>
        <span className="truncate">screens the terminal draws</span>
      </header>
      <div className="flex min-h-0 flex-1">
        <nav aria-label="Terminal pages" className="w-[12rem] shrink-0 overflow-auto border-e border-hair" onKeyDown={onListKey}>
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
                className={`h-7 w-full justify-start rounded-none px-2.5 font-mono text-[0.6875rem] font-normal tracking-[0.02em] ${nested ? "ps-5" : ""} ${current ? "bg-surface-2 text-ink" : "text-ink-mute"}`}
                onClick={() => onNavigate(item.path)}
              >
                {item.label}
              </Button>
            );
          })}
        </nav>
        <div className="relative min-h-0 min-w-0 flex-1">
          <TerminalScreen path={path} />
        </div>
      </div>
    </div>
  );
}
